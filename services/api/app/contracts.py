from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.rules import Assessment, RuleFinding


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: UUID


class AssessmentResponse(BaseModel):
    evaluation_id: UUID
    assessment: Assessment
    registration: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
    profile_version: int
    snapshot_bundle: str
    engine_version: str
    policy_version: str
    findings: list[RuleFinding]
    evidence: list[dict[str, str]]
    limitations: list[str]


class CourseAttemptResponse(BaseModel):
    course_id: UUID
    synthetic_code: str
    state: str
    evidence_origin: Literal["synthetic"]


class HistoryResponse(BaseModel):
    profile_version: int
    attempts: list[CourseAttemptResponse]


class AdminEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason_code: Literal["synthetic_review_complete"]


class AdminEvidenceResponse(BaseModel):
    audit_event_id: UUID
    outbox_event_id: UUID
    status: Literal["recorded"] = "recorded"


class SourceImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_key: Literal["synthetic_catalog_v1"]
    idempotency_key: str = Field(
        min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
    payload: Any


class SourceImportResponse(BaseModel):
    import_id: UUID
    snapshot_id: UUID | None
    state: Literal["normalized", "quarantined"]
    valid_records: int
    quarantined_records: int
    error_codes: list[str]
    content_hash: str
    replayed: bool


class PublicationActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason_code: Literal["synthetic_review_complete"]


class PublicationResponse(BaseModel):
    publication_id: UUID
    snapshot_id: UUID
    bundle_version: str
    state: Literal["approved", "published", "superseded"]
    active: bool
    generation: int | None
