from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings
from app.ids import COURSE_A300, COURSE_B100, SUBJECT_A1, SUBJECT_A2, TENANT_A, TENANT_B
from app.main import app
from app.worker import process_once

client = TestClient(app)


def auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}", "x-request-id": uuid4().hex}


def test_student_views_only_own_history_through_api() -> None:
    first = client.get("/v1/me/course-history", headers=auth("student-a1"))
    second = client.get("/v1/me/course-history", headers=auth("student-a2"))
    other_tenant = client.get("/v1/me/course-history", headers=auth("student-b1"))
    assert first.status_code == second.status_code == other_tenant.status_code == 200
    assert [item["state"] for item in first.json()["attempts"]] == ["completed"]
    assert [item["state"] for item in second.json()["attempts"]] == ["in_progress"]
    assert [item["state"] for item in other_tenant.json()["attempts"]] == ["completed"]
    assert first.json()["attempts"][0]["course_id"] != other_tenant.json()["attempts"][0]["course_id"]


def test_rls_blocks_same_tenant_other_subject_and_cross_tenant() -> None:
    engine = create_engine(settings.app_database_url)
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text("SELECT set_config('app.tenant_id', :value, true)"),
                {"value": str(TENANT_A)},
            )
            connection.execute(
                text("SELECT set_config('app.subject_id', :value, true)"),
                {"value": str(SUBJECT_A1)},
            )
            visible = connection.execute(
                text("SELECT subject_id, tenant_id FROM course_attempts")
            ).all()
            assert visible == [(SUBJECT_A1, TENANT_A)]
            assert connection.execute(
                text("SELECT count(*) FROM course_attempts WHERE subject_id = :subject"),
                {"subject": SUBJECT_A2},
            ).scalar_one() == 0
            assert connection.execute(
                text("SELECT count(*) FROM course_attempts WHERE tenant_id = :tenant"),
                {"tenant": TENANT_B},
            ).scalar_one() == 0
        # SET LOCAL values have been cleared before this pooled connection is reused.
        with connection.begin():
            assert connection.execute(text("SELECT count(*) FROM course_attempts")).scalar_one() == 0


def test_cross_tenant_course_is_indistinguishable_from_missing() -> None:
    response = client.post(
        "/v1/assessments",
        headers=auth("student-a1"),
        json={"course_id": str(COURSE_B100)},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "COURSE_OR_RULE_NOT_FOUND"


def test_unsupported_rule_returns_unknown_and_trace_reaches_worker() -> None:
    trace_id = uuid4().hex
    response = client.post(
        "/v1/assessments",
        headers={"authorization": "Bearer student-a1", "x-request-id": trace_id},
        json={"course_id": str(COURSE_A300)},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == trace_id
    body = response.json()
    assert body["assessment"] == "UNKNOWN"
    assert body["registration"] == "NOT_EVALUATED"
    assert any(item["code"] == "UNSUPPORTED_RULE" for item in body["findings"])

    assert process_once() >= 1
    owner_engine = create_engine(settings.migration_database_url)
    with owner_engine.connect() as connection:
        evaluation_trace = connection.execute(
            text("SELECT trace_id FROM evaluations WHERE id = :id"),
            {"id": body["evaluation_id"]},
        ).scalar_one()
        outbox = connection.execute(
            text(
                """SELECT trace_id, processed_at, attempts FROM outbox_events
                WHERE aggregate_id = :id"""
            ),
            {"id": body["evaluation_id"]},
        ).one()
    assert evaluation_trace == trace_id
    assert outbox.trace_id == trace_id
    assert outbox.processed_at is not None
    assert outbox.attempts == 1


def test_privileged_action_requires_admin_and_is_durable() -> None:
    denied = client.post(
        "/v1/admin/synthetic-review-evidence",
        headers=auth("student-a1"),
        json={"reason_code": "synthetic_review_complete"},
    )
    assert denied.status_code == 403
    accepted = client.post(
        "/v1/admin/synthetic-review-evidence",
        headers=auth("admin-a"),
        json={"reason_code": "synthetic_review_complete"},
    )
    assert accepted.status_code == 200
    owner_engine = create_engine(settings.migration_database_url)
    with owner_engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM audit_events WHERE id = :id"),
            {"id": accepted.json()["audit_event_id"]},
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT count(*) FROM outbox_events WHERE id = :id"),
            {"id": accepted.json()["outbox_event_id"]},
        ).scalar_one() == 1

