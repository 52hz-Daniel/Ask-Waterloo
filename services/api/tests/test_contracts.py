import json
from pathlib import Path

import pytest
from jsonschema import FormatChecker, ValidationError, validate

from app.contracts import AssessmentResponse
from app.ids import COURSE_A100
from app.rules import Assessment, RuleFinding


def test_assessment_response_matches_shared_schema() -> None:
    response = AssessmentResponse(
        evaluation_id="80000000-0000-0000-0000-000000000001",
        assessment=Assessment.UNKNOWN,
        profile_version=1,
        snapshot_bundle="synthetic-v1",
        engine_version="rules-v0.1",
        policy_version="synthetic-policy-v1",
        findings=[
            RuleFinding(
                code="UNSUPPORTED_RULE", state=Assessment.UNKNOWN, rule_path="requirements"
            )
        ],
        evidence=[{"source_record_id": str(COURSE_A100), "rule_path": "requirements"}],
        limitations=["Synthetic limitation"],
    )
    schema_path = Path("/contracts/assessment-result.schema.json")
    if not schema_path.exists():
        schema_path = Path(__file__).parents[3] / "contracts/assessment-result.schema.json"
    validate(json.loads(response.model_dump_json()), json.loads(schema_path.read_text()))


def test_synthetic_catalog_contract_accepts_valid_and_rejects_partial_fixture() -> None:
    contracts = Path("/contracts")
    fixtures = Path("/fixtures/source")
    if not contracts.exists():
        root = Path(__file__).parents[3]
        contracts = root / "contracts"
        fixtures = root / "tests/fixtures/source"
    schema = json.loads((contracts / "synthetic-catalog-v1.schema.json").read_text())
    valid = json.loads((fixtures / "valid_catalog.json").read_text())
    partial = json.loads((fixtures / "partial_catalog.json").read_text())
    validate(valid, schema, format_checker=FormatChecker())
    with pytest.raises(ValidationError):
        validate(partial, schema, format_checker=FormatChecker())
