import json
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Iterable


class NetworkFailureCategory(str, Enum):
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    TIMEOUT = "timeout"
    CONNECTION_RESET = "connection_reset"
    CONNECTION_REFUSED = "connection_refused"
    DNS = "dns"
    TLS = "tls"
    CONTENT_TYPE = "content_type"
    NETWORK = "network"


@dataclass(frozen=True)
class NetworkCheckResult:
    url: str
    accessible: bool
    attempts: int
    status: int | None = None
    category: NetworkFailureCategory | None = None
    error: str | None = None
    recovered: bool = False
    content_type: str | None = None

    def to_issue(self) -> dict:
        """保持原有 href/status 字段，并补充稳定失败的分类和尝试次数。"""
        return {
            "href": self.url,
            "status": self.status if self.status is not None else self.error,
            "category": self.category.value if self.category else None,
            "attempts": self.attempts,
        }


def classify_network_exception(exc: Exception) -> NetworkFailureCategory:
    message = str(exc).lower()

    if any(
        marker in message
        for marker in ("etimedout", "timeout", "timed out", "deadline exceeded")
    ):
        return NetworkFailureCategory.TIMEOUT
    if any(
        marker in message
        for marker in ("econnreset", "connection reset", "socket hang up")
    ):
        return NetworkFailureCategory.CONNECTION_RESET
    if any(
        marker in message
        for marker in ("econnrefused", "connection refused", "actively refused")
    ):
        return NetworkFailureCategory.CONNECTION_REFUSED
    if any(
        marker in message
        for marker in (
            "enotfound",
            "name not resolved",
            "name or service not known",
            "getaddrinfo",
            "dns",
        )
    ):
        return NetworkFailureCategory.DNS
    if any(
        marker in message
        for marker in (
            "ssl",
            "tls",
            "certificate",
            "wrong version number",
            "handshake",
        )
    ):
        return NetworkFailureCategory.TLS
    return NetworkFailureCategory.NETWORK


def _status_category(status: int) -> NetworkFailureCategory:
    if 400 <= status < 500:
        return NetworkFailureCategory.HTTP_4XX
    return NetworkFailureCategory.HTTP_5XX


def _should_retry_status(status: int) -> bool:
    return status == 429 or status >= 500


def _record_recovered_fluctuation(result: NetworkCheckResult):
    payload = {
        "classification": "transient_environment_fluctuation",
        **asdict(result),
    }
    if result.category is not None:
        payload["category"] = result.category.value

    print(
        "[network-check] transient environment fluctuation recovered: "
        f"url={result.url}, attempts={result.attempts}, "
        f"first_failure={payload.get('error') or payload.get('status')}"
    )
    try:
        import allure

        allure.attach(
            json.dumps(payload, ensure_ascii=False, indent=2),
            name="Transient network fluctuation",
            attachment_type=allure.attachment_type.JSON,
        )
    except Exception:
        # Allure 不可用或当前不在用例生命周期时，只保留控制台记录。
        return


def check_url(
    request_context,
    url: str,
    *,
    timeout: int = 30_000,
    max_attempts: int = 2,
    retry_delay_seconds: float = 0.25,
    expected_content_type_prefix: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> NetworkCheckResult:
    """检查单个URL；瞬时网络异常和5xx最多重试一次。"""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    first_failure_category = None
    first_failure_error = None
    first_failure_status = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = request_context.get(
                url,
                timeout=timeout,
                fail_on_status_code=False,
            )
            status = response.status
            content_type = (response.headers.get("content-type") or "").lower()

            if status < 400:
                if (
                    expected_content_type_prefix
                    and not content_type.startswith(expected_content_type_prefix.lower())
                ):
                    return NetworkCheckResult(
                        url=url,
                        accessible=False,
                        attempts=attempt,
                        status=status,
                        category=NetworkFailureCategory.CONTENT_TYPE,
                        error=(
                            f"Unexpected content-type: {content_type or '(missing)'}; "
                            f"expected prefix {expected_content_type_prefix}"
                        ),
                        content_type=content_type,
                    )

                result = NetworkCheckResult(
                    url=url,
                    accessible=True,
                    attempts=attempt,
                    status=status,
                    category=first_failure_category,
                    error=first_failure_error,
                    recovered=attempt > 1,
                    content_type=content_type,
                )
                if result.recovered:
                    _record_recovered_fluctuation(result)
                return result

            category = _status_category(status)
            if attempt == 1:
                first_failure_category = category
                first_failure_status = status
                first_failure_error = f"HTTP {status}"

            if attempt < max_attempts and _should_retry_status(status):
                if retry_delay_seconds > 0:
                    sleep(retry_delay_seconds)
                continue

            return NetworkCheckResult(
                url=url,
                accessible=False,
                attempts=attempt,
                status=status,
                category=category,
                error=f"HTTP {status}",
                content_type=content_type,
            )
        except Exception as exc:
            category = classify_network_exception(exc)
            error = str(exc)
            if attempt == 1:
                first_failure_category = category
                first_failure_error = error

            if attempt < max_attempts:
                if retry_delay_seconds > 0:
                    sleep(retry_delay_seconds)
                continue

            return NetworkCheckResult(
                url=url,
                accessible=False,
                attempts=attempt,
                status=first_failure_status,
                category=category,
                error=error,
            )

    raise AssertionError("unreachable network check state")


def check_urls(
    request_context,
    urls: Iterable[str],
    *,
    timeout: int = 30_000,
    max_attempts: int = 2,
) -> list[dict]:
    """批量检查URL，只返回连续失败后的稳定问题。"""
    issues = []
    for url in urls:
        result = check_url(
            request_context,
            url,
            timeout=timeout,
            max_attempts=max_attempts,
        )
        if not result.accessible:
            issues.append(result.to_issue())
    return issues
