from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.contracts import PublicationResponse
from app.db import authorized_session
from app.repository import write_audit


class PublicationConflictError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


def _response(session: Session, publication_id: UUID) -> PublicationResponse:
    row = session.execute(
        text(
            """SELECT p.id AS publication_id, p.snapshot_id, p.bundle_version, p.state,
                      (a.publication_id = p.id) AS active,
                      CASE WHEN a.publication_id = p.id THEN a.generation END AS generation
               FROM catalog_publications p
               LEFT JOIN active_catalog_publications a ON a.tenant_id = p.tenant_id
               WHERE p.id = :publication_id"""
        ),
        {"publication_id": publication_id},
    ).mappings().one()
    return PublicationResponse(**row)


def _emit(
    session: Session,
    principal: Principal,
    publication_id: UUID,
    event_type: str,
    action: str,
    trace_id: str,
) -> None:
    write_audit(session, principal, action, "catalog_publication", trace_id)
    session.execute(
        text(
            """INSERT INTO outbox_events
               (id, tenant_id, event_type, aggregate_type, aggregate_id, trace_id)
               VALUES (:id, :tenant, :event_type, 'catalog_publication',
                       :publication_id, :trace_id)"""
        ),
        {
            "id": uuid4(),
            "tenant": principal.tenant_id,
            "event_type": event_type,
            "publication_id": publication_id,
            "trace_id": trace_id,
        },
    )


def approve_snapshot(
    principal: Principal, snapshot_id: UUID, reason_code: str, trace_id: str
) -> PublicationResponse | None:
    with authorized_session(principal) as session:
        existing = session.execute(
            text(
                """SELECT id FROM catalog_publications
                   WHERE tenant_id = :tenant AND snapshot_id = :snapshot"""
            ),
            {"tenant": principal.tenant_id, "snapshot": snapshot_id},
        ).scalar_one_or_none()
        if existing is not None:
            return _response(session, existing)

        candidate = session.execute(
            text(
                """SELECT s.bundle_version, s.import_id,
                          s.validation_status, i.state AS import_state,
                          count(sc.id)::int AS total_records,
                          count(sc.id) FILTER (WHERE sc.validation_status = 'valid')::int
                            AS valid_records
                   FROM source_snapshots s
                   JOIN source_imports i
                     ON i.tenant_id = s.tenant_id AND i.id = s.import_id
                   LEFT JOIN staging_courses sc
                     ON sc.tenant_id = s.tenant_id AND sc.snapshot_id = s.id
                   WHERE s.tenant_id = :tenant AND s.id = :snapshot
                   GROUP BY s.id, s.bundle_version, s.import_id,
                            s.validation_status, i.state"""
            ),
            {"tenant": principal.tenant_id, "snapshot": snapshot_id},
        ).mappings().one_or_none()
        if candidate is None:
            return None
        if (
            candidate["validation_status"] != "normalized"
            or candidate["import_state"] != "normalized"
            or candidate["total_records"] == 0
            or candidate["valid_records"] != candidate["total_records"]
        ):
            raise PublicationConflictError("SNAPSHOT_NOT_PROMOTABLE")

        publication_id = uuid4()
        session.execute(
            text(
                """INSERT INTO catalog_publications
                   (id, tenant_id, snapshot_id, source_import_id, bundle_version, state,
                    approved_by_hash, reason_code, trace_id)
                   VALUES (:id, :tenant, :snapshot, :import_id, :bundle, 'approved',
                           :actor, :reason, :trace)"""
            ),
            {
                "id": publication_id,
                "tenant": principal.tenant_id,
                "snapshot": snapshot_id,
                "import_id": candidate["import_id"],
                "bundle": candidate["bundle_version"],
                "actor": principal.actor_ref_hash,
                "reason": reason_code,
                "trace": trace_id,
            },
        )
        _emit(
            session,
            principal,
            publication_id,
            "catalog.publication.approved",
            "catalog_publication.approve",
            trace_id,
        )
        return _response(session, publication_id)


def _validated_staged_records(session: Session, publication_id: UUID) -> tuple[Any, list[Any]]:
    publication = session.execute(
        text(
            """SELECT p.id, p.snapshot_id, p.source_import_id, p.state,
                      s.validation_status, i.state AS import_state
               FROM catalog_publications p
               JOIN source_snapshots s
                 ON s.tenant_id = p.tenant_id AND s.id = p.snapshot_id
               JOIN source_imports i
                 ON i.tenant_id = p.tenant_id AND i.id = p.source_import_id
               WHERE p.id = :publication_id
               FOR UPDATE OF p, s, i"""
        ),
        {"publication_id": publication_id},
    ).mappings().one_or_none()
    if publication is None:
        return None, []
    records = list(
        session.execute(
            text(
                """SELECT normalized_record
                   FROM staging_courses
                   WHERE import_id = :import_id
                   ORDER BY ordinal
                   FOR UPDATE"""
            ),
            {"import_id": publication["source_import_id"]},
        ).mappings()
    )
    invalid_count = session.execute(
        text(
            """SELECT count(*) FROM staging_courses
               WHERE import_id = :import_id
                 AND (validation_status <> 'valid' OR normalized_record IS NULL)"""
        ),
        {"import_id": publication["source_import_id"]},
    ).scalar_one()
    if (
        publication["state"] != "approved"
        or publication["validation_status"] != "normalized"
        or publication["import_state"] != "normalized"
        or not records
        or invalid_count
    ):
        raise PublicationConflictError("PUBLICATION_NOT_PROMOTABLE")
    return publication, records


def publish(
    principal: Principal, publication_id: UUID, trace_id: str
) -> PublicationResponse | None:
    with authorized_session(principal) as session:
        # Serialize pointer changes for one tenant while retaining a single DB transaction.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 0))"),
            {"tenant": str(principal.tenant_id)},
        )
        publication, records = _validated_staged_records(session, publication_id)
        if publication is None:
            return None

        for item in records:
            normalized = item["normalized_record"]
            course_id = session.execute(
                text(
                    """INSERT INTO courses (id, tenant_id, synthetic_code)
                       VALUES (:id, :tenant, :code)
                       ON CONFLICT (tenant_id, synthetic_code)
                       DO UPDATE SET synthetic_code = EXCLUDED.synthetic_code
                       RETURNING id"""
                ),
                {
                    "id": uuid4(),
                    "tenant": principal.tenant_id,
                    "code": normalized["code"],
                },
            ).scalar_one()
            session.execute(
                text(
                    """INSERT INTO course_versions
                       (id, tenant_id, course_id, snapshot_id, publication_id,
                        title, units, valid_from, valid_to)
                       VALUES (:id, :tenant, :course, :snapshot, :publication,
                               :title, :units, :valid_from, :valid_to)"""
                ),
                {
                    "id": uuid4(),
                    "tenant": principal.tenant_id,
                    "course": course_id,
                    "snapshot": publication["snapshot_id"],
                    "publication": publication_id,
                    "title": normalized["title"],
                    "units": normalized["units"],
                    "valid_from": normalized["valid_from"],
                    "valid_to": normalized["valid_to"],
                },
            )

        previous = session.execute(
            text(
                """SELECT publication_id, generation
                   FROM active_catalog_publications
                   WHERE tenant_id = :tenant FOR UPDATE"""
            ),
            {"tenant": principal.tenant_id},
        ).mappings().one_or_none()
        generation = (previous["generation"] if previous else 0) + 1
        if previous and previous["publication_id"] != publication_id:
            session.execute(
                text(
                    """UPDATE catalog_publications
                       SET state = 'superseded', superseded_at = now()
                       WHERE id = :previous"""
                ),
                {"previous": previous["publication_id"]},
            )
        session.execute(
            text(
                """UPDATE catalog_publications
                   SET state = 'published', published_at = now(), superseded_at = NULL
                   WHERE id = :publication"""
            ),
            {"publication": publication_id},
        )
        session.execute(
            text(
                """INSERT INTO active_catalog_publications
                     (tenant_id, publication_id, generation)
                   VALUES (:tenant, :publication, :generation)
                   ON CONFLICT (tenant_id) DO UPDATE
                   SET publication_id = EXCLUDED.publication_id,
                       generation = EXCLUDED.generation, updated_at = now()"""
            ),
            {
                "tenant": principal.tenant_id,
                "publication": publication_id,
                "generation": generation,
            },
        )
        session.execute(
            text(
                """UPDATE source_snapshots SET validation_status = 'published'
                   WHERE id = :snapshot"""
            ),
            {"snapshot": publication["snapshot_id"]},
        )
        _emit(
            session,
            principal,
            publication_id,
            "catalog.publication.published",
            "catalog_publication.publish",
            trace_id,
        )
        return _response(session, publication_id)


def rollback(
    principal: Principal, publication_id: UUID, trace_id: str
) -> PublicationResponse | None:
    with authorized_session(principal) as session:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 0))"),
            {"tenant": str(principal.tenant_id)},
        )
        target = session.execute(
            text(
                """SELECT p.id, p.state FROM catalog_publications p
                   WHERE p.id = :publication FOR UPDATE"""
            ),
            {"publication": publication_id},
        ).mappings().one_or_none()
        if target is None:
            return None
        active = session.execute(
            text(
                """SELECT publication_id, generation FROM active_catalog_publications
                   WHERE tenant_id = :tenant FOR UPDATE"""
            ),
            {"tenant": principal.tenant_id},
        ).mappings().one_or_none()
        if active and active["publication_id"] == publication_id:
            return _response(session, publication_id)
        version_count = session.execute(
            text("SELECT count(*) FROM course_versions WHERE publication_id = :publication"),
            {"publication": publication_id},
        ).scalar_one()
        if target["state"] != "superseded" or version_count == 0 or active is None:
            raise PublicationConflictError("PUBLICATION_NOT_ROLLBACK_TARGET")

        session.execute(
            text(
                """UPDATE catalog_publications
                   SET state = 'superseded', superseded_at = now()
                   WHERE id = :current"""
            ),
            {"current": active["publication_id"]},
        )
        session.execute(
            text(
                """UPDATE catalog_publications
                   SET state = 'published', superseded_at = NULL
                   WHERE id = :target"""
            ),
            {"target": publication_id},
        )
        session.execute(
            text(
                """UPDATE active_catalog_publications
                   SET publication_id = :target, generation = :generation, updated_at = now()
                   WHERE tenant_id = :tenant"""
            ),
            {
                "target": publication_id,
                "generation": active["generation"] + 1,
                "tenant": principal.tenant_id,
            },
        )
        _emit(
            session,
            principal,
            publication_id,
            "catalog.publication.rolled_back",
            "catalog_publication.rollback",
            trace_id,
        )
        return _response(session, publication_id)


def get_active_publication(principal: Principal) -> PublicationResponse | None:
    with authorized_session(principal) as session:
        publication_id = session.execute(
            text(
                """SELECT publication_id FROM active_catalog_publications
                   WHERE tenant_id = :tenant"""
            ),
            {"tenant": principal.tenant_id},
        ).scalar_one_or_none()
        return _response(session, publication_id) if publication_id else None
