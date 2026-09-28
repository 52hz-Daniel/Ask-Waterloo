import logging

from fastapi.testclient import TestClient

from app.main import app
from app.telemetry import emit_event

client = TestClient(app)
SENTINEL = "SENSITIVE-STUDENT-FACT-9f84e1"


def test_request_body_and_token_are_absent_from_telemetry(caplog: object) -> None:
    with caplog.at_level(logging.INFO, logger="navigator.telemetry"):  # type: ignore[attr-defined]
        response = client.post(
            "/v1/assessments",
            headers={"authorization": "Bearer student-a1"},
            json={"course_id": SENTINEL, "student_fact": SENTINEL},
        )
    assert response.status_code == 422
    output = caplog.text  # type: ignore[attr-defined]
    assert SENTINEL not in output
    assert "student-a1" not in output


def test_structured_emitter_drops_unknown_fields_and_redacts_unsafe_values(caplog: object) -> None:
    with caplog.at_level(logging.INFO, logger="navigator.telemetry"):  # type: ignore[attr-defined]
        emit_event("sentinel.test", route=SENTINEL, student_fact=SENTINEL)
    output = caplog.text  # type: ignore[attr-defined]
    assert SENTINEL not in output
    assert "student_fact" not in output
    assert "REDACTED" in output

