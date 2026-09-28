import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings
from app.main import app

client = TestClient(app)
owner_engine = create_engine(settings.migration_database_url)


def fixture(name: str) -> Any:
    root = Path("/fixtures/source")
    if not root.exists():
        root = Path(__file__).parents[3] / "tests/fixtures/source"
    return json.loads((root / name).read_text())


def auth(token: str = "admin-a") -> dict[str, str]:
    return {"authorization": f"Bearer {token}", "x-request-id": uuid4().hex}


def unique_payload(name: str) -> Any:
    payload = copy.deepcopy(fixture(name))
    if isinstance(payload, dict) and "bundle_version" in payload:
        payload["bundle_version"] = f"{payload['bundle_version']}-{uuid4().hex}"
    return payload


def import_payload(payload: Any, key: str | None = None, token: str = "admin-a") -> Any:
    return client.post(
        "/v1/admin/source-imports",
        headers=auth(token),
        json={
            "source_key": "synthetic_catalog_v1",
            "idempotency_key": key or f"test-{uuid4().hex}",
            "payload": payload,
        },
    )


def published_fingerprint() -> list[tuple[Any, ...]]:
    with owner_engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    """SELECT c.id, c.tenant_id, c.synthetic_code, cv.id, cv.snapshot_id,
                              cv.title, cv.units, cv.valid_from, cv.valid_to
                    FROM courses c JOIN course_versions cv
                      ON cv.tenant_id = c.tenant_id AND cv.course_id = c.id
                    ORDER BY c.id, cv.id"""
                )
            ).all()
        )


def test_valid_fixture_is_normalized_with_raw_provenance() -> None:
    payload = unique_payload("valid_catalog.json")
    response = import_payload(payload)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "normalized"
    assert body["valid_records"] == 1
    assert body["quarantined_records"] == 0
    assert body["snapshot_id"] is not None

    with owner_engine.connect() as connection:
        stored = connection.execute(
            text(
                """SELECT i.raw_payload, i.content_hash, i.parser_version,
                          s.bundle_version, sc.raw_record, sc.normalized_record,
                          sc.source_record_id, sc.source_url
                FROM source_imports i
                JOIN source_snapshots s ON s.import_id = i.id AND s.tenant_id = i.tenant_id
                JOIN staging_courses sc ON sc.import_id = i.id AND sc.tenant_id = i.tenant_id
                WHERE i.id = :id"""
            ),
            {"id": body["import_id"]},
        ).mappings().one()
    assert stored["raw_payload"] == payload
    assert stored["content_hash"] == body["content_hash"]
    assert stored["parser_version"] == "synthetic-catalog-parser-v1"
    assert stored["bundle_version"] == payload["bundle_version"]
    assert stored["raw_record"] == payload["records"][0]
    assert stored["normalized_record"]["units"] == "0.50"
    assert stored["source_record_id"] == "fixture-course-101"
    assert stored["source_url"].startswith("synthetic://")
    with owner_engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM audit_events WHERE action = 'source_import.create' AND trace_id = :trace"),
            {"trace": response.headers["x-request-id"]},
        ).scalar_one() == 1
        assert connection.execute(
            text(
                """SELECT count(*) FROM outbox_events
                WHERE aggregate_id = :id AND event_type = 'source.import.normalized'"""
            ),
            {"id": body["import_id"]},
        ).scalar_one() == 1


@pytest.mark.parametrize(
    ("name", "expected_error", "quarantined_count"),
    [
        ("partial_catalog.json", "MISSING_REQUIRED_FIELD", 1),
        ("malformed_catalog.json", "INVALID_EFFECTIVE_FROM", 1),
        ("duplicate_catalog.json", "DUPLICATE_SOURCE_RECORD_ID", 2),
    ],
)
def test_bad_inputs_are_quarantined_without_changing_published_catalog(
    name: str, expected_error: str, quarantined_count: int
) -> None:
    before = published_fingerprint()
    response = import_payload(unique_payload(name))
    after = published_fingerprint()
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "quarantined"
    assert expected_error in body["error_codes"]
    assert body["quarantined_records"] == quarantined_count
    assert after == before


def test_non_object_payload_is_durably_quarantined() -> None:
    before = published_fingerprint()
    response = import_payload("not-an-object")
    assert response.status_code == 200
    assert response.json()["state"] == "quarantined"
    assert response.json()["error_codes"] == ["PAYLOAD_NOT_OBJECT"]
    assert response.json()["snapshot_id"] is None
    assert published_fingerprint() == before


def test_existing_bundle_version_is_quarantined_without_overwriting_it() -> None:
    before = published_fingerprint()
    payload = fixture("valid_catalog.json")
    payload["bundle_version"] = "synthetic-alpha-v1"
    response = import_payload(payload)
    assert response.status_code == 200
    assert response.json()["state"] == "quarantined"
    assert response.json()["snapshot_id"] is None
    assert "BUNDLE_VERSION_CONFLICT" in response.json()["error_codes"]
    assert published_fingerprint() == before


def test_duplicate_delivery_is_idempotent_and_key_reuse_conflicts() -> None:
    payload = unique_payload("valid_catalog.json")
    key = f"idempotency-{uuid4().hex}"
    first = import_payload(payload, key)
    replay = import_payload(payload, key)
    other_key = f"other-{uuid4().hex}"
    content_replay = import_payload(payload, other_key)
    changed = copy.deepcopy(payload)
    changed["records"][0]["title"] = "Different content"
    conflict = import_payload(changed, key)
    alias_conflict = import_payload(changed, other_key)

    assert first.status_code == replay.status_code == content_replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert content_replay.json()["replayed"] is True
    assert first.json()["import_id"] == replay.json()["import_id"]
    assert first.json()["import_id"] == content_replay.json()["import_id"]
    assert conflict.status_code == 409
    assert alias_conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_CONTENT"

    with owner_engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM source_imports WHERE id = :id"),
            {"id": first.json()["import_id"]},
        ).scalar_one() == 1


def test_import_status_is_tenant_isolated() -> None:
    created = import_payload(unique_payload("valid_catalog.json"), token="admin-a")
    import_id = created.json()["import_id"]
    own = client.get(f"/v1/admin/source-imports/{import_id}", headers=auth("admin-a"))
    other_tenant = client.get(
        f"/v1/admin/source-imports/{import_id}", headers=auth("admin-b")
    )
    assert own.status_code == 200
    assert other_tenant.status_code == 404
