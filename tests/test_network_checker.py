from framework.network_checker import (
    NetworkFailureCategory,
    check_url,
    check_urls,
    classify_network_exception,
)


class FakeResponse:
    def __init__(self, status: int, content_type: str = "text/html"):
        self.status = status
        self.headers = {"content-type": content_type}


class FakeRequestContext:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, timeout, fail_on_status_code):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _no_sleep(_):
    return None


def test_http_404_is_stable_without_retry():
    request = FakeRequestContext([FakeResponse(404)])

    result = check_url(request, "https://example.test/missing", sleep=_no_sleep)

    assert result.accessible is False
    assert result.category == NetworkFailureCategory.HTTP_4XX
    assert result.status == 404
    assert result.attempts == 1
    assert request.calls == 1


def test_http_500_then_200_is_transient_recovery():
    request = FakeRequestContext([FakeResponse(500), FakeResponse(200)])

    result = check_url(request, "https://example.test/", sleep=_no_sleep)

    assert result.accessible is True
    assert result.recovered is True
    assert result.category == NetworkFailureCategory.HTTP_5XX
    assert result.attempts == 2


def test_timeout_then_success_is_transient_recovery():
    request = FakeRequestContext(
        [RuntimeError("connect ETIMEDOUT 8.216.134.71:443"), FakeResponse(200)]
    )

    result = check_url(request, "https://example.test/", sleep=_no_sleep)

    assert result.accessible is True
    assert result.recovered is True
    assert result.category == NetworkFailureCategory.TIMEOUT
    assert result.attempts == 2


def test_connection_reset_twice_is_stable_failure():
    request = FakeRequestContext(
        [RuntimeError("read ECONNRESET"), RuntimeError("socket hang up")]
    )

    result = check_url(request, "https://example.test/", sleep=_no_sleep)

    assert result.accessible is False
    assert result.category == NetworkFailureCategory.CONNECTION_RESET
    assert result.attempts == 2


def test_dns_and_tls_errors_are_classified():
    assert (
        classify_network_exception(RuntimeError("getaddrinfo ENOTFOUND example.test"))
        == NetworkFailureCategory.DNS
    )
    assert (
        classify_network_exception(RuntimeError("SSL certificate handshake failed"))
        == NetworkFailureCategory.TLS
    )


def test_image_content_type_must_match():
    request = FakeRequestContext([FakeResponse(200, "text/html")])

    result = check_url(
        request,
        "https://example.test/not-an-image",
        expected_content_type_prefix="image/",
        sleep=_no_sleep,
    )

    assert result.accessible is False
    assert result.category == NetworkFailureCategory.CONTENT_TYPE
    assert result.attempts == 1


def test_batch_only_returns_stable_failures():
    request = FakeRequestContext(
        [
            RuntimeError("connect ETIMEDOUT"),
            FakeResponse(200),
            FakeResponse(404),
        ]
    )

    issues = check_urls(
        request,
        ["https://example.test/recovered", "https://example.test/missing"],
        max_attempts=2,
    )

    assert len(issues) == 1
    assert issues[0]["href"] == "https://example.test/missing"
    assert issues[0]["status"] == 404
    assert issues[0]["category"] == "http_4xx"
    assert issues[0]["attempts"] == 1
