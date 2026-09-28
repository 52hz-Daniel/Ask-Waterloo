import logging
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from app.auth import Principal, require_admin, require_student
from app.contracts import (
    AdminEvidenceRequest,
    AdminEvidenceResponse,
    AssessmentRequest,
    AssessmentResponse,
    HistoryResponse,
    PublicationActionRequest,
    PublicationResponse,
    SourceImportRequest,
    SourceImportResponse,
)
from app.importer import (
    ImportConflictError,
    PayloadTooLargeError,
    get_source_import,
    ingest_snapshot,
)
from app.repository import create_assessment, get_history, record_admin_evidence
from app.publications import (
    PublicationConflictError,
    approve_snapshot,
    get_active_publication,
    publish,
    rollback,
)
from app.telemetry import emit_event, new_trace_id, trace_id_var

logging.basicConfig(level=logging.INFO, format="%(message)s")
app = FastAPI(title="Academic Navigator API", version="0.1.0")


@app.middleware("http")
async def safe_request_telemetry(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    trace_id = new_trace_id(request.headers.get("x-request-id"))
    token = trace_id_var.set(trace_id)
    started = time.perf_counter()
    route_template = getattr(request.scope.get("route"), "path", "unmatched")
    try:
        response = await call_next(request)
    except Exception:
        emit_event(
            "http.request",
            route=route_template,
            method=request.method,
            status_code=500,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            result_class="server_error",
        )
        raise
    else:
        response.headers["x-request-id"] = trace_id
        emit_event(
            "http.request",
            route=getattr(request.scope.get("route"), "path", route_template),
            method=request.method,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            result_class="success" if response.status_code < 400 else "rejected",
        )
        return response
    finally:
        trace_id_var.reset(token)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/me/course-history", response_model=HistoryResponse)
def history(principal: Principal = Depends(require_student)) -> HistoryResponse:
    return get_history(principal, trace_id_var.get())


@app.post("/v1/assessments", response_model=AssessmentResponse)
def assess(
    request: AssessmentRequest, principal: Principal = Depends(require_student)
) -> AssessmentResponse:
    result = create_assessment(principal, request.course_id, trace_id_var.get())
    if result is None:
        # The same safe response is used for a nonexistent and another-tenant course.
        raise HTTPException(404, detail={"code": "COURSE_OR_RULE_NOT_FOUND"})
    return result


@app.post("/v1/admin/synthetic-review-evidence", response_model=AdminEvidenceResponse)
def admin_evidence(
    request: AdminEvidenceRequest, principal: Principal = Depends(require_admin)
) -> AdminEvidenceResponse:
    del request  # schema validation is the evidence reason allowlist
    return record_admin_evidence(principal, trace_id_var.get())


@app.post("/v1/admin/source-imports", response_model=SourceImportResponse)
def source_import(
    request: SourceImportRequest, principal: Principal = Depends(require_admin)
) -> SourceImportResponse:
    try:
        return ingest_snapshot(principal, request, trace_id_var.get())
    except ImportConflictError as error:
        raise HTTPException(
            409, detail={"code": "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_CONTENT"}
        ) from error
    except PayloadTooLargeError as error:
        raise HTTPException(413, detail={"code": "SOURCE_PAYLOAD_TOO_LARGE"}) from error


@app.get("/v1/admin/source-imports/{import_id}", response_model=SourceImportResponse)
def source_import_status(
    import_id: UUID, principal: Principal = Depends(require_admin)
) -> SourceImportResponse:
    result = get_source_import(principal, import_id)
    if result is None:
        raise HTTPException(404, detail={"code": "SOURCE_IMPORT_NOT_FOUND"})
    return result


@app.post(
    "/v1/admin/publications/snapshots/{snapshot_id}/approve",
    response_model=PublicationResponse,
)
def publication_approve(
    snapshot_id: UUID,
    request: PublicationActionRequest,
    principal: Principal = Depends(require_admin),
) -> PublicationResponse:
    try:
        result = approve_snapshot(
            principal, snapshot_id, request.reason_code, trace_id_var.get()
        )
    except PublicationConflictError as error:
        raise HTTPException(409, detail={"code": error.code}) from error
    if result is None:
        raise HTTPException(404, detail={"code": "SOURCE_SNAPSHOT_NOT_FOUND"})
    return result


@app.post(
    "/v1/admin/publications/{publication_id}/publish",
    response_model=PublicationResponse,
)
def publication_publish(
    publication_id: UUID, principal: Principal = Depends(require_admin)
) -> PublicationResponse:
    try:
        result = publish(principal, publication_id, trace_id_var.get())
    except PublicationConflictError as error:
        raise HTTPException(409, detail={"code": error.code}) from error
    if result is None:
        raise HTTPException(404, detail={"code": "PUBLICATION_NOT_FOUND"})
    return result


@app.post(
    "/v1/admin/publications/{publication_id}/rollback",
    response_model=PublicationResponse,
)
def publication_rollback(
    publication_id: UUID, principal: Principal = Depends(require_admin)
) -> PublicationResponse:
    try:
        result = rollback(principal, publication_id, trace_id_var.get())
    except PublicationConflictError as error:
        raise HTTPException(409, detail={"code": error.code}) from error
    if result is None:
        raise HTTPException(404, detail={"code": "PUBLICATION_NOT_FOUND"})
    return result


@app.get("/v1/admin/publications/active", response_model=PublicationResponse)
def publication_active(
    principal: Principal = Depends(require_admin),
) -> PublicationResponse:
    result = get_active_publication(principal)
    if result is None:
        raise HTTPException(404, detail={"code": "ACTIVE_PUBLICATION_NOT_FOUND"})
    return result
