import json
import logging
import re
from contextvars import ContextVar
from uuid import uuid4

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="unscoped")
logger = logging.getLogger("navigator.telemetry")

ALLOWED_FIELDS = {
    "event",
    "trace_id",
    "route",
    "method",
    "status_code",
    "duration_ms",
    "result_class",
    "event_type",
    "attempt",
}
SAFE_EVENT = re.compile(r"^[a-z][a-z0-9_.]{0,49}$")
SAFE_ROUTE = re.compile(r"^/[a-z0-9_./{}:-]{0,99}$")
SAFE_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
SAFE_RESULT_CLASSES = {"success", "rejected", "server_error"}


def new_trace_id(candidate: str | None = None) -> str:
    if candidate and re.fullmatch(r"[a-fA-F0-9]{32}", candidate):
        return candidate.lower()
    return uuid4().hex


def emit_event(event: str, **fields: object) -> None:
    safe: dict[str, object] = {
        "event": event if SAFE_EVENT.fullmatch(event) else "redacted.event",
        "trace_id": trace_id_var.get(),
    }
    for key, value in fields.items():
        if key not in ALLOWED_FIELDS or key in {"event", "trace_id"}:
            continue
        if isinstance(value, (int, float)):
            safe[key] = value
        elif isinstance(value, str):
            is_safe = (
                (key == "route" and SAFE_ROUTE.fullmatch(value))
                or (key == "method" and value in SAFE_METHODS)
                or (key == "result_class" and value in SAFE_RESULT_CLASSES)
                or (key == "event_type" and SAFE_EVENT.fullmatch(value))
            )
            safe[key] = value if is_safe else "REDACTED"
        else:
            safe[key] = "REDACTED"
    logger.info(json.dumps(safe, sort_keys=True, separators=(",", ":")))
