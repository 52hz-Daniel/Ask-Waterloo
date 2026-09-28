from dataclasses import dataclass
from typing import Any

import httpx

OPENAPI_SCHEMA_SHA256 = "c3813b5f17cacdd8d10c8b949a0d32f974fa2b3ea535caabfd33734eab9a776d"
DEFAULT_BASE_URL = "https://openapi.data.uwaterloo.ca"


class WaterlooAccessError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Waterloo Open Data request failed with HTTP {status_code}")
        self.status_code = status_code


class WaterlooSchemaError(Exception):
    pass


@dataclass(frozen=True)
class WaterlooCourseCandidate:
    source_record_id: str
    source_url: str
    code: str
    title: str
    term_code: str
    term_name: str | None
    description: str | None
    requirements_text: str | None
    provenance_schema_sha256: str
    promotion_blockers: tuple[str, ...]


class WaterlooOpenDataClient:
    """Small v3 transport boundary; callers must supply a key outside the repository."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A Waterloo API key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def courses(self, term_code: str, subject: str, catalog_number: str) -> list[dict[str, Any]]:
        path = f"/v3/Courses/{term_code}/{subject}/{catalog_number}"
        with httpx.Client(
            base_url=self._base_url,
            headers={"x-api-key": self._api_key, "accept": "application/json"},
            timeout=15.0,
            transport=self._transport,
        ) as client:
            response = client.get(path)
        if response.status_code != 200:
            raise WaterlooAccessError(response.status_code)
        payload = response.json()
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise WaterlooSchemaError("COURSES_RESPONSE_NOT_ARRAY_OF_OBJECTS")
        return payload


def map_course(record: dict[str, Any]) -> WaterlooCourseCandidate:
    """Map only fields present in the official v3 Course schema.

    This deliberately does not infer credits, effective dates, or a prerequisite AST.
    Those omissions keep the candidate outside the publication path until sources and
    academic semantics are reviewed.
    """

    required = ("courseId", "courseOfferNumber", "termCode", "subjectCode", "catalogNumber", "title")
    missing = [field for field in required if record.get(field) in (None, "")]
    if missing:
        raise WaterlooSchemaError("MISSING_REQUIRED_COURSE_FIELDS:" + ",".join(missing))
    if not isinstance(record["courseOfferNumber"], int):
        raise WaterlooSchemaError("INVALID_COURSE_OFFER_NUMBER")
    string_fields = ("courseId", "termCode", "subjectCode", "catalogNumber", "title")
    if any(not isinstance(record[field], str) for field in string_fields):
        raise WaterlooSchemaError("INVALID_COURSE_FIELD_TYPE")

    term_code = record["termCode"].strip()
    subject = record["subjectCode"].strip().upper()
    catalog_number = record["catalogNumber"].strip().upper()
    course_id = record["courseId"].strip()
    offer_number = record["courseOfferNumber"]
    return WaterlooCourseCandidate(
        source_record_id=f"{term_code}:{course_id}:{offer_number}",
        source_url=(
            f"{DEFAULT_BASE_URL}/v3/Courses/{term_code}/{subject}/{catalog_number}"
        ),
        code=f"{subject} {catalog_number}",
        title=record["title"].strip(),
        term_code=term_code,
        term_name=_optional_string(record.get("termName")),
        description=_optional_string(record.get("description")),
        requirements_text=_optional_string(record.get("requirementsDescription")),
        provenance_schema_sha256=OPENAPI_SCHEMA_SHA256,
        promotion_blockers=(
            "CREDITS_NOT_IN_OPEN_DATA_COURSE_SCHEMA",
            "EFFECTIVE_DATES_NOT_IN_OPEN_DATA_COURSE_SCHEMA",
            "REQUIREMENTS_TEXT_NOT_ACADEMICALLY_REVIEWED",
            "SOURCE_USE_APPROVAL_PENDING",
        ),
    )


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
