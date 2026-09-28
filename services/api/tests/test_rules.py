from app.ids import COURSE_A100
from app.rules import Assessment, evaluate


def test_supported_completion_is_satisfied() -> None:
    result = evaluate(
        {"type": "course_completed", "course_id": str(COURSE_A100)},
        {str(COURSE_A100)},
    )
    assert result.assessment == Assessment.SATISFIED


def test_unsupported_clause_is_unknown() -> None:
    result = evaluate({"type": "not_implemented"}, set())
    assert result.assessment == Assessment.UNKNOWN
    assert result.findings[0].code == "UNSUPPORTED_RULE"


def test_and_preserves_unknown_when_other_child_is_true() -> None:
    result = evaluate(
        {
            "type": "all_of",
            "children": [
                {"type": "course_completed", "course_id": str(COURSE_A100)},
                {"type": "synthetic_advisor_permission"},
            ],
        },
        {str(COURSE_A100)},
    )
    assert result.assessment == Assessment.UNKNOWN


def test_and_known_false_dominates_unknown() -> None:
    result = evaluate(
        {
            "type": "all_of",
            "children": [
                {"type": "course_completed", "course_id": str(COURSE_A100)},
                {"type": "unsupported"},
            ],
        },
        set(),
    )
    assert result.assessment == Assessment.NOT_SATISFIED

