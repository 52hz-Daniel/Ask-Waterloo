import json

import httpx
import pytest

from app.adapters.waterloo_open_data import (
    WaterlooAccessError,
    WaterlooOpenDataClient,
    WaterlooSchemaError,
    map_course,
)


def schema_shaped_course() -> dict[str, object]:
    # Synthetic values using field names from the official v3 OpenAPI schema.
    return {
        "courseId": "synthetic-course-id",
        "courseOfferNumber": 1,
        "termCode": "1269",
        "termName": "Synthetic Fall",
        "subjectCode": "SYN",
        "catalogNumber": "101",
        "title": "Synthetic Source Mapping",
        "description": "Non-Waterloo fixture content.",
        "requirementsDescription": "Synthetic prerequisite prose.",
    }


def test_client_uses_documented_path_and_api_key_without_logging_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/Courses/1269/SYN/101"
        assert request.headers["x-api-key"] == "test-secret"
        return httpx.Response(200, content=json.dumps([schema_shaped_course()]).encode())

    client = WaterlooOpenDataClient(
        "test-secret", base_url="https://example.invalid", transport=httpx.MockTransport(handler)
    )
    assert client.courses("1269", "SYN", "101") == [schema_shaped_course()]


def test_mapper_preserves_provenance_and_blocks_unverified_promotion() -> None:
    candidate = map_course(schema_shaped_course())
    assert candidate.source_record_id == "1269:synthetic-course-id:1"
    assert candidate.code == "SYN 101"
    assert candidate.requirements_text == "Synthetic prerequisite prose."
    assert "CREDITS_NOT_IN_OPEN_DATA_COURSE_SCHEMA" in candidate.promotion_blockers
    assert "REQUIREMENTS_TEXT_NOT_ACADEMICALLY_REVIEWED" in candidate.promotion_blockers


def test_mapper_rejects_missing_identity_fields() -> None:
    record = schema_shaped_course()
    del record["courseId"]
    with pytest.raises(WaterlooSchemaError, match="MISSING_REQUIRED_COURSE_FIELDS"):
        map_course(record)


def test_access_failures_are_status_only_and_do_not_expose_response_content() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="sensitive body"))
    client = WaterlooOpenDataClient(
        "test-secret", base_url="https://example.invalid", transport=transport
    )
    with pytest.raises(WaterlooAccessError, match="HTTP 401") as error:
        client.courses("1269", "SYN", "101")
    assert "sensitive body" not in str(error.value)
