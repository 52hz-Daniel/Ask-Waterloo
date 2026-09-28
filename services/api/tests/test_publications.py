import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings
from app.main import app

client = TestClient(app)
non_raising_client = TestClient(app, raise_server_exceptions=False)
owner_engine = create_engine(settings.migration_database_url)


def fixture(name: str) -> Any:
    root = Path("/fixtures/source")
    if not root.exists():
        root = Path(__file__).parents[3] / "tests/fixtures/source"
    return json.loads((root / name).read_text())


def auth(token: str = "admin-a") -> dict[str, str]:
    return {"authorization": f"Bearer {token}", "x-request-id": uuid4().hex}


def import_fixture(name: str = "valid_catalog.json") -> dict[str, Any]:
    payload = copy.deepcopy(fixture(name))
    payload["bundle_version"] = f"{payload['bundle_version']}-{uuid4().hex}"
    response = client.post(
        "/v1/admin/source-imports",
        headers=auth(),
        json={
            "source_key": "synthetic_catalog_v1",
            "idempotency_key": f"publication-{uuid4().hex}",
            "payload": payload,
        },
    )
    assert response.status_code == 200
    return response.json()


def approve(snapshot_id: str) -> Any:
    return client.post(
        f"/v1/admin/publications/snapshots/{snapshot_id}/approve",
        headers=auth(),
        json={"reason_code": "synthetic_review_complete"},
    )


def active(token: str = "admin-a") -> dict[str, Any]:
    response = client.get("/v1/admin/publications/active", headers=auth(token))
    assert response.status_code == 200
    return response.json()


def catalog_fingerprint() -> list[tuple[Any, ...]]:
    with owner_engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    """SELECT c.id, c.tenant_id, c.synthetic_code, cv.id,
                              cv.snapshot_id, cv.publication_id, cv.title, cv.units,
                              cv.valid_from, cv.valid_to
                       FROM courses c JOIN course_versions cv
                         ON cv.tenant_id = c.tenant_id AND cv.course_id = c.id
                       ORDER BY c.id, cv.id"""
                )
            ).all()
        )


def test_atomic_promotion_version_consistency_and_rollback() -> None:
    previous = active()
    imported = import_fixture()
    approval_trace = uuid4().hex
    approved = client.post(
        f"/v1/admin/publications/snapshots/{imported['snapshot_id']}/approve",
        headers={"authorization": "Bearer admin-a", "x-request-id": approval_trace},
        json={"reason_code": "synthetic_review_complete"},
    )
    assert approved.status_code == 200
    candidate = approved.json()
    assert candidate["state"] == "approved"
    assert candidate["active"] is False

    denied = client.post(
        f"/v1/admin/publications/snapshots/{imported['snapshot_id']}/approve",
        headers=auth("admin-b"),
        json={"reason_code": "synthetic_review_complete"},
    )
    assert denied.status_code == 404
    student_denied = client.post(
        f"/v1/admin/publications/snapshots/{imported['snapshot_id']}/approve",
        headers=auth("student-a1"),
        json={"reason_code": "synthetic_review_complete"},
    )
    assert student_denied.status_code == 403

    promoted = client.post(
        f"/v1/admin/publications/{candidate['publication_id']}/publish",
        headers=auth(),
    )
    assert promoted.status_code == 200
    published = promoted.json()
    assert published["state"] == "published"
    assert published["active"] is True
    assert published["generation"] == previous["generation"] + 1

    with owner_engine.connect() as connection:
        versions = connection.execute(
            text(
                """SELECT snapshot_id, publication_id FROM course_versions
                   WHERE publication_id = :publication"""
            ),
            {"publication": UUID(candidate["publication_id"])},
        ).all()
        assert versions == [
            (UUID(imported["snapshot_id"]), UUID(candidate["publication_id"]))
        ]
        assert connection.execute(
            text(
                """SELECT count(*) FROM audit_events
                   WHERE action = 'catalog_publication.approve' AND trace_id = :trace"""
            ),
            {"trace": approval_trace},
        ).scalar_one() == 1
        assert connection.execute(
            text(
                """SELECT count(*) FROM outbox_events
                   WHERE aggregate_id = :publication
                     AND event_type = 'catalog.publication.published'"""
            ),
            {"publication": UUID(candidate["publication_id"])},
        ).scalar_one() == 1

    rolled_back = client.post(
        f"/v1/admin/publications/{previous['publication_id']}/rollback",
        headers=auth(),
    )
    assert rolled_back.status_code == 200
    recovered = rolled_back.json()
    assert recovered["publication_id"] == previous["publication_id"]
    assert recovered["active"] is True
    assert recovered["generation"] == published["generation"] + 1


def test_quarantined_snapshot_cannot_change_active_publication() -> None:
    before = active()
    imported = import_fixture("partial_catalog.json")
    assert imported["state"] == "quarantined"
    assert imported["snapshot_id"] is not None
    response = approve(imported["snapshot_id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SNAPSHOT_NOT_PROMOTABLE"
    assert active() == before


def test_failed_materialization_rolls_back_every_write() -> None:
    before_active = active()
    before_catalog = catalog_fingerprint()
    imported = import_fixture()
    approved = approve(imported["snapshot_id"])
    assert approved.status_code == 200
    publication_id = approved.json()["publication_id"]

    with owner_engine.begin() as connection:
        connection.execute(
            text(
                """UPDATE staging_courses
                   SET normalized_record = jsonb_set(
                     normalized_record, '{units}',
                     to_jsonb(CAST('not-a-number' AS text)))
                   WHERE snapshot_id = :snapshot"""
            ),
            {"snapshot": UUID(imported["snapshot_id"])},
        )
    response = non_raising_client.post(
        f"/v1/admin/publications/{publication_id}/publish", headers=auth()
    )
    assert response.status_code == 500
    assert active() == before_active
    assert catalog_fingerprint() == before_catalog


def test_publication_lookup_is_tenant_isolated() -> None:
    imported = import_fixture()
    approved = approve(imported["snapshot_id"])
    publication_id = approved.json()["publication_id"]
    response = client.post(
        f"/v1/admin/publications/{publication_id}/publish",
        headers=auth("admin-b"),
    )
    assert response.status_code == 404
