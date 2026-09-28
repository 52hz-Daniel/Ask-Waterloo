import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from app.auth import Principal
from app.contracts import SourceImportRequest, SourceImportResponse
from app.db import authorized_session
from app.repository import write_audit

PARSER_VERSION = "synthetic-catalog-parser-v1"
MAX_PAYLOAD_BYTES = 1_000_000
MAX_RECORDS = 1_000
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
RECORD_FIELDS = {"source_record_id", "source_url", "code", "title", "units", "valid_from", "valid_to"}
REQUIRED_RECORD_FIELDS = {"source_record_id", "code", "title", "units", "valid_from"}


class ImportConflictError(Exception):
    pass


class PayloadTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class ValidatedRecord:
    ordinal: int
    raw: Any
    source_record_id: str | None
    source_url: str | None
    normalized: dict[str, Any] | None
    errors: list[str]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _bounded_string(value: Any, maximum: int) -> str | None:
    return value if isinstance(value, str) and 0 < len(value.strip()) <= maximum else None


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _validate_record(ordinal: int, raw: Any, duplicates: set[str]) -> ValidatedRecord:
    if not isinstance(raw, dict):
        return ValidatedRecord(ordinal, raw, None, None, None, ["RECORD_NOT_OBJECT"])

    errors: list[str] = []
    missing = sorted(REQUIRED_RECORD_FIELDS - raw.keys())
    if missing:
        errors.append("MISSING_REQUIRED_FIELD")
    if set(raw) - RECORD_FIELDS:
        errors.append("UNSUPPORTED_RECORD_FIELD")

    record_id = _bounded_string(raw.get("source_record_id"), 200)
    code = _bounded_string(raw.get("code"), 50)
    title = _bounded_string(raw.get("title"), 300)
    valid_from = _iso_date(raw.get("valid_from"))
    valid_to = _iso_date(raw.get("valid_to")) if raw.get("valid_to") is not None else None
    source_url = _bounded_string(raw.get("source_url"), 500) if raw.get("source_url") else None

    if raw.get("source_record_id") is not None and record_id is None:
        errors.append("INVALID_SOURCE_RECORD_ID")
    if record_id in duplicates:
        errors.append("DUPLICATE_SOURCE_RECORD_ID")
    if raw.get("code") is not None and code is None:
        errors.append("INVALID_CODE")
    if raw.get("title") is not None and title is None:
        errors.append("INVALID_TITLE")
    if raw.get("valid_from") is not None and valid_from is None:
        errors.append("INVALID_VALID_FROM")
    if raw.get("valid_to") is not None and valid_to is None:
        errors.append("INVALID_VALID_TO")
    if valid_from and valid_to and valid_to < valid_from:
        errors.append("INVALID_EFFECTIVE_RANGE")
    if source_url is not None and not source_url.startswith("synthetic://"):
        errors.append("INVALID_SOURCE_URL")

    units: Decimal | None = None
    try:
        units = Decimal(str(raw.get("units")))
        if not units.is_finite() or units <= 0 or units > 10:
            errors.append("INVALID_UNITS")
    except (InvalidOperation, TypeError):
        errors.append("INVALID_UNITS")

    normalized = None
    if not errors and record_id and code and title and valid_from and units is not None:
        normalized = {
            "source_record_id": record_id,
            "source_url": source_url,
            "code": code.strip(),
            "title": title.strip(),
            "units": format(units, "f"),
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat() if valid_to else None,
        }
    return ValidatedRecord(
        ordinal, raw, record_id, source_url, normalized, sorted(set(errors))
    )


def _response_from_row(row: Any, replayed: bool) -> SourceImportResponse:
    return SourceImportResponse(
        import_id=row["id"],
        snapshot_id=row["snapshot_id"],
        state=row["state"],
        valid_records=row["valid_records"],
        quarantined_records=row["quarantined_records"],
        error_codes=list(row["error_codes"]),
        content_hash=row["content_hash"],
        replayed=replayed,
    )


IMPORT_RESULT_SQL = """
SELECT i.id, i.state, i.error_codes, i.content_hash,
       s.id AS snapshot_id,
       count(sc.id) FILTER (WHERE sc.validation_status = 'valid')::int AS valid_records,
       count(sc.id) FILTER (WHERE sc.validation_status = 'quarantined')::int AS quarantined_records
FROM source_imports i
LEFT JOIN source_snapshots s ON s.tenant_id = i.tenant_id AND s.import_id = i.id
LEFT JOIN staging_courses sc ON sc.tenant_id = i.tenant_id AND sc.import_id = i.id
WHERE i.id = :import_id
GROUP BY i.id, s.id
"""


def ingest_snapshot(
    principal: Principal, request: SourceImportRequest, trace_id: str
) -> SourceImportResponse:
    canonical = _canonical(request.payload)
    if len(canonical.encode()) > MAX_PAYLOAD_BYTES:
        raise PayloadTooLargeError
    content_hash = hashlib.sha256(canonical.encode()).hexdigest()

    with authorized_session(principal) as session:
        key_row = session.execute(
            text(
                """SELECT id, content_hash FROM source_imports
                WHERE tenant_id = :tenant AND source_key = :source AND idempotency_key = :key
                UNION ALL
                SELECT import_id AS id, content_hash FROM source_import_keys
                WHERE tenant_id = :tenant AND source_key = :source AND idempotency_key = :key
                LIMIT 1"""
            ),
            {"tenant": principal.tenant_id, "source": request.source_key, "key": request.idempotency_key},
        ).mappings().one_or_none()
        if key_row is not None:
            if key_row["content_hash"] != content_hash:
                raise ImportConflictError
            row = session.execute(
                text(IMPORT_RESULT_SQL), {"import_id": key_row["id"]}
            ).mappings().one()
            return _response_from_row(row, True)

        hash_row = session.execute(
            text(
                """SELECT id FROM source_imports
                WHERE tenant_id = :tenant AND source_key = :source
                  AND content_hash = :content_hash"""
            ),
            {"tenant": principal.tenant_id, "source": request.source_key, "content_hash": content_hash},
        ).mappings().one_or_none()
        if hash_row is not None:
            session.execute(
                text(
                    """INSERT INTO source_import_keys
                    (tenant_id, source_key, idempotency_key, content_hash, import_id)
                    VALUES (:tenant, :source, :key, :content_hash, :import_id)"""
                ),
                {
                    "tenant": principal.tenant_id,
                    "source": request.source_key,
                    "key": request.idempotency_key,
                    "content_hash": content_hash,
                    "import_id": hash_row["id"],
                },
            )
            row = session.execute(
                text(IMPORT_RESULT_SQL), {"import_id": hash_row["id"]}
            ).mappings().one()
            return _response_from_row(row, True)

        import_id = uuid4()
        import_errors: list[str] = []
        payload = request.payload
        bundle_version: str | None = None
        effective_from: date | None = None
        raw_records: list[Any] = []
        if not isinstance(payload, dict):
            import_errors.append("PAYLOAD_NOT_OBJECT")
        else:
            if set(payload) - {"bundle_version", "effective_from", "records"}:
                import_errors.append("UNSUPPORTED_PAYLOAD_FIELD")
            version_value = payload.get("bundle_version")
            if isinstance(version_value, str) and SAFE_VERSION.fullmatch(version_value):
                bundle_version = version_value
            else:
                import_errors.append("INVALID_BUNDLE_VERSION")
            effective_from = _iso_date(payload.get("effective_from"))
            if effective_from is None:
                import_errors.append("INVALID_EFFECTIVE_FROM")
            records_value = payload.get("records")
            if not isinstance(records_value, list):
                import_errors.append("RECORDS_NOT_ARRAY")
            elif not records_value:
                import_errors.append("EMPTY_RECORDS")
            elif len(records_value) > MAX_RECORDS:
                import_errors.append("TOO_MANY_RECORDS")
            else:
                raw_records = records_value

        ids: list[str] = []
        for item in raw_records:
            if isinstance(item, dict):
                candidate_id = item.get("source_record_id")
                if isinstance(candidate_id, str):
                    ids.append(candidate_id)
        duplicates = {value for value, count in Counter(ids).items() if count > 1}
        records = [_validate_record(index, raw, duplicates) for index, raw in enumerate(raw_records)]
        record_errors = sorted({error for record in records for error in record.errors})
        all_errors = sorted(set(import_errors + record_errors))

        snapshot_id: UUID | None = None
        if bundle_version and effective_from:
            version_exists = session.execute(
                text(
                    """SELECT 1 FROM source_snapshots
                    WHERE tenant_id = :tenant AND bundle_version = :version"""
                ),
                {"tenant": principal.tenant_id, "version": bundle_version},
            ).first()
            if version_exists:
                all_errors = sorted(set(all_errors + ["BUNDLE_VERSION_CONFLICT"]))
            else:
                snapshot_id = uuid4()

        state = "quarantined" if all_errors else "normalized"
        session.execute(
            text(
                """INSERT INTO source_imports
                (id, tenant_id, source_key, idempotency_key, content_hash, raw_payload,
                 parser_version, state, error_codes, completed_at, trace_id)
                VALUES (:id, :tenant, :source, :key, :hash, CAST(:payload AS jsonb),
                        :parser, :state, :errors, now(), :trace)"""
            ),
            {
                "id": import_id, "tenant": principal.tenant_id, "source": request.source_key,
                "key": request.idempotency_key, "hash": content_hash, "payload": canonical,
                "parser": PARSER_VERSION, "state": state, "errors": all_errors, "trace": trace_id,
            },
        )
        if snapshot_id and bundle_version and effective_from:
            session.execute(
                text(
                    """INSERT INTO source_snapshots
                    (id, tenant_id, bundle_version, fetched_at, effective_from, content_hash,
                     provenance_kind, import_id, source_key, parser_version, validation_status)
                    VALUES (:id, :tenant, :version, now(), :effective, :hash, 'synthetic',
                            :import_id, :source, :parser, :status)"""
                ),
                {
                    "id": snapshot_id, "tenant": principal.tenant_id, "version": bundle_version,
                    "effective": effective_from, "hash": content_hash, "import_id": import_id,
                    "source": request.source_key, "parser": PARSER_VERSION, "status": state,
                },
            )
        for record in records:
            session.execute(
                text(
                    """INSERT INTO staging_courses
                    (id, tenant_id, import_id, snapshot_id, ordinal, source_record_id,
                     source_url, content_hash, raw_record, normalized_record,
                     validation_status, error_codes)
                    VALUES (:id, :tenant, :import_id, :snapshot_id, :ordinal, :record_id,
                            :source_url, :hash, CAST(:raw AS jsonb), CAST(:normalized AS jsonb),
                            :status, :errors)"""
                ),
                {
                    "id": uuid4(), "tenant": principal.tenant_id, "import_id": import_id,
                    "snapshot_id": snapshot_id, "ordinal": record.ordinal,
                    "record_id": record.source_record_id, "source_url": record.source_url,
                    "hash": _hash(record.raw), "raw": _canonical(record.raw),
                    "normalized": _canonical(record.normalized) if record.normalized else None,
                    "status": "quarantined" if record.errors else "valid", "errors": record.errors,
                },
            )
        write_audit(session, principal, "source_import.create", "source_import", trace_id)
        session.execute(
            text(
                """INSERT INTO outbox_events
                (id, tenant_id, event_type, aggregate_type, aggregate_id, trace_id)
                VALUES (:id, :tenant, :event_type, 'source_import', :import_id, :trace)"""
            ),
            {
                "id": uuid4(), "tenant": principal.tenant_id,
                "event_type": f"source.import.{state}", "import_id": import_id, "trace": trace_id,
            },
        )
        return SourceImportResponse(
            import_id=import_id,
            snapshot_id=snapshot_id,
            state=state,
            valid_records=sum(not record.errors for record in records),
            quarantined_records=sum(bool(record.errors) for record in records),
            error_codes=all_errors,
            content_hash=content_hash,
            replayed=False,
        )


def get_source_import(principal: Principal, import_id: UUID) -> SourceImportResponse | None:
    with authorized_session(principal) as session:
        row = session.execute(text(IMPORT_RESULT_SQL), {"import_id": import_id}).mappings().one_or_none()
        return _response_from_row(row, False) if row else None
