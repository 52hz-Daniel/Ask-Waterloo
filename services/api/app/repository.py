import json
from uuid import UUID, uuid4

from sqlalchemy import text

from app.auth import Principal
from app.contracts import (
    AdminEvidenceResponse,
    AssessmentResponse,
    CourseAttemptResponse,
    HistoryResponse,
)
from app.db import authorized_session
from app.rules import evaluate


def write_audit(
    session: object, principal: Principal, action: str, object_type: str, trace_id: str
) -> UUID:
    event_id = uuid4()
    session.execute(  # type: ignore[attr-defined]
        text(
            """INSERT INTO audit_events
            (id, tenant_id, actor_ref_hash, action, object_type, outcome, trace_id)
            VALUES (:id, :tenant, :actor, :action, :object_type, 'allowed', :trace)"""
        ),
        {
            "id": event_id,
            "tenant": principal.tenant_id,
            "actor": principal.actor_ref_hash,
            "action": action,
            "object_type": object_type,
            "trace": trace_id,
        },
    )
    return event_id


def get_history(principal: Principal, trace_id: str) -> HistoryResponse:
    assert principal.subject_id is not None
    with authorized_session(principal) as session:
        rows = session.execute(
            text(
                """SELECT a.course_id, c.synthetic_code, a.state, a.evidence_origin
                FROM course_attempts a JOIN courses c
                  ON c.tenant_id = a.tenant_id AND c.id = a.course_id
                ORDER BY c.synthetic_code"""
            )
        ).mappings()
        attempts = [CourseAttemptResponse(**row) for row in rows]
        write_audit(session, principal, "student_history.read", "course_history", trace_id)
    return HistoryResponse(profile_version=1, attempts=attempts)


def create_assessment(principal: Principal, course_id: UUID, trace_id: str) -> AssessmentResponse | None:
    assert principal.subject_id is not None
    with authorized_session(principal) as session:
        rule_row = session.execute(
            text(
                """SELECT r.ast, s.bundle_version, s.id AS snapshot_id
                FROM rule_sets r JOIN source_snapshots s ON s.id = r.snapshot_id
                WHERE r.tenant_id = :tenant AND r.course_id = :course"""
            ),
            {"tenant": principal.tenant_id, "course": course_id},
        ).mappings().one_or_none()
        if rule_row is None:
            return None
        completed = {
            str(value)
            for value in session.execute(
                text("SELECT course_id FROM course_attempts WHERE state = 'completed'")
            ).scalars()
        }
        outcome = evaluate(rule_row["ast"], completed)
        evaluation_id, outbox_id = uuid4(), uuid4()
        result = AssessmentResponse(
            evaluation_id=evaluation_id,
            assessment=outcome.assessment,
            profile_version=1,
            snapshot_bundle=rule_row["bundle_version"],
            engine_version="rules-v0.1",
            policy_version="synthetic-policy-v1",
            findings=outcome.findings,
            evidence=[{"source_record_id": str(rule_row["snapshot_id"]), "rule_path": "requirements"}],
            limitations=outcome.limitations,
        )
        session.execute(
            text(
                """INSERT INTO evaluations
                (id, tenant_id, subject_id, course_id, result, profile_version,
                 snapshot_bundle, engine_version, trace_id)
                VALUES (:id, :tenant, :subject, :course, CAST(:result AS jsonb), 1,
                        :bundle, :engine, :trace)"""
            ),
            {
                "id": evaluation_id,
                "tenant": principal.tenant_id,
                "subject": principal.subject_id,
                "course": course_id,
                "result": result.model_dump_json(),
                "bundle": result.snapshot_bundle,
                "engine": result.engine_version,
                "trace": trace_id,
            },
        )
        session.execute(
            text(
                """INSERT INTO outbox_events
                (id, tenant_id, event_type, aggregate_type, aggregate_id, trace_id, payload)
                VALUES (:id, :tenant, 'assessment.created', 'evaluation', :evaluation,
                        :trace, CAST(:payload AS jsonb))"""
            ),
            {
                "id": outbox_id,
                "tenant": principal.tenant_id,
                "evaluation": evaluation_id,
                "trace": trace_id,
                "payload": json.dumps({"subject_ref": str(principal.subject_id)}),
            },
        )
        write_audit(session, principal, "assessment.create", "evaluation", trace_id)
        return result


def record_admin_evidence(principal: Principal, trace_id: str) -> AdminEvidenceResponse:
    with authorized_session(principal) as session:
        audit_id = write_audit(
            session, principal, "synthetic_publication.review", "source_snapshot", trace_id
        )
        outbox_id = uuid4()
        session.execute(
            text(
                """INSERT INTO outbox_events
                (id, tenant_id, event_type, aggregate_type, aggregate_id, trace_id)
                VALUES (:id, :tenant, 'audit.evidence.recorded', 'audit_event', :audit,
                        :trace)"""
            ),
            {
                "id": outbox_id,
                "tenant": principal.tenant_id,
                "audit": audit_id,
                "trace": trace_id,
            },
        )
    return AdminEvidenceResponse(audit_event_id=audit_id, outbox_event_id=outbox_id)
