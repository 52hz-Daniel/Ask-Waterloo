import hashlib
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from app.config import settings
from app.ids import SUBJECT_A1, SUBJECT_A2, SUBJECT_B1, SUBJECT_B2, TENANT_A, TENANT_B


@dataclass(frozen=True)
class Principal:
    tenant_id: UUID
    subject_id: UUID | None
    role: str
    actor_ref_hash: str


def _principal(token: str, tenant: UUID, subject: UUID | None, role: str) -> Principal:
    digest = hashlib.sha256(("synthetic-actor-v1:" + token).encode()).hexdigest()
    return Principal(tenant, subject, role, digest)


SYNTHETIC_PRINCIPALS = {
    "student-a1": _principal("student-a1", TENANT_A, SUBJECT_A1, "student"),
    "student-a2": _principal("student-a2", TENANT_A, SUBJECT_A2, "student"),
    "student-b1": _principal("student-b1", TENANT_B, SUBJECT_B1, "student"),
    "student-b2": _principal("student-b2", TENANT_B, SUBJECT_B2, "student"),
    "admin-a": _principal("admin-a", TENANT_A, None, "admin"),
    "admin-b": _principal("admin-b", TENANT_B, None, "admin"),
}


def require_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    if settings.auth_mode != "synthetic":
        raise HTTPException(503, detail={"code": "IDENTITY_NOT_CONFIGURED"})
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail={"code": "AUTHENTICATION_REQUIRED"})
    principal = SYNTHETIC_PRINCIPALS.get(authorization.removeprefix("Bearer "))
    if principal is None:
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIAL"})
    return principal


CurrentPrincipal = Annotated[Principal, Depends(require_principal)]


def require_student(principal: CurrentPrincipal) -> Principal:
    if principal.role != "student" or principal.subject_id is None:
        raise HTTPException(403, detail={"code": "STUDENT_SCOPE_REQUIRED"})
    return principal


def require_admin(principal: CurrentPrincipal) -> Principal:
    if principal.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_SCOPE_REQUIRED"})
    return principal
