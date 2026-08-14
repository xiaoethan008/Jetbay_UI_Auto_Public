from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_FULL_VARIABLE = re.compile(r"^\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}$")
_VARIABLE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def extract_path(value: Any, path: str) -> Any:
    """Extract a dotted path from dictionaries/lists."""
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Path '{path}' is missing segment '{part}'.")
            current = current[part]
        else:
            raise KeyError(f"Path '{path}' cannot traverse segment '{part}'.")
    return current


@dataclass
class ChainContext:
    sensitive_variables: set[str] = field(default_factory=set)
    values: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def set(self, name: str, value: Any, source: str = "") -> Any:
        self.values[name] = value
        self.events.append(
            {
                "event": "set",
                "variable": name,
                "source": source,
                "value": self._safe_value(name, value),
            }
        )
        return value

    def get(self, name: str) -> Any:
        if name not in self.values:
            raise KeyError(f"Chain variable '{name}' has not been set.")
        return self.values[name]

    def render(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self.render(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item) for item in value]
        if not isinstance(value, str):
            return value

        full_match = _FULL_VARIABLE.match(value)
        if full_match:
            return self.get(full_match.group(1))

        return _VARIABLE.sub(lambda match: str(self.get(match.group(1))), value)

    def record_step(self, step: str, status: str, **details: Any) -> None:
        self.events.append(
            {
                "event": "step",
                "step": step,
                "status": status,
                "details": self._sanitize(details),
            }
        )

    def public_snapshot(self) -> dict[str, Any]:
        return {
            name: self._safe_value(name, value)
            for name, value in self.values.items()
        }

    def write_report(self, path: str | Path, summary: dict[str, Any]) -> Path:
        report_path = Path(path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": self._sanitize(summary),
            "variables": self.public_snapshot(),
            "events": self.events,
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return report_path

    def _safe_value(self, name: str, value: Any) -> Any:
        lowered = name.lower()
        if name in self.sensitive_variables or any(
            marker in lowered for marker in ("password", "token", "authorization")
        ):
            return "<redacted>"
        if (
            isinstance(value, str)
            and (lowered == "email" or lowered.endswith("_email") or lowered.endswith("email_address"))
        ):
            local, separator, domain = value.partition("@")
            if not separator:
                return "<redacted-email>"
            visible = local[:2] if local else ""
            return f"{visible}***@{domain}"
        return self._sanitize(value)

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._safe_value(str(key), item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, tuple):
            return [self._sanitize(item) for item in value]
        return value
