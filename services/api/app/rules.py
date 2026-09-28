from enum import Enum
from typing import Any

from pydantic import BaseModel


class Assessment(str, Enum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    UNKNOWN = "UNKNOWN"


class RuleFinding(BaseModel):
    code: str
    state: Assessment
    rule_path: str


class RuleEvaluation(BaseModel):
    assessment: Assessment
    findings: list[RuleFinding]
    limitations: list[str]


def evaluate(rule: dict[str, Any], completed_course_ids: set[str], path: str = "requirements") -> RuleEvaluation:
    kind = rule.get("type")
    if kind == "course_completed":
        course_id = str(rule.get("course_id", ""))
        state = (
            Assessment.SATISFIED
            if course_id in completed_course_ids
            else Assessment.NOT_SATISFIED
        )
        return RuleEvaluation(
            assessment=state,
            findings=[RuleFinding(code="COURSE_COMPLETED", state=state, rule_path=path)],
            limitations=[],
        )
    if kind in {"all_of", "any_of"}:
        children = [
            evaluate(child, completed_course_ids, f"{path}.{index}")
            for index, child in enumerate(rule.get("children", []))
        ]
        states = [child.assessment for child in children]
        if kind == "all_of":
            state = (
                Assessment.NOT_SATISFIED
                if Assessment.NOT_SATISFIED in states
                else Assessment.SATISFIED
                if states and all(item == Assessment.SATISFIED for item in states)
                else Assessment.UNKNOWN
            )
        else:
            state = (
                Assessment.SATISFIED
                if Assessment.SATISFIED in states
                else Assessment.NOT_SATISFIED
                if states and all(item == Assessment.NOT_SATISFIED for item in states)
                else Assessment.UNKNOWN
            )
        return RuleEvaluation(
            assessment=state,
            findings=[finding for child in children for finding in child.findings],
            limitations=[item for child in children for item in child.limitations],
        )
    return RuleEvaluation(
        assessment=Assessment.UNKNOWN,
        findings=[
            RuleFinding(code="UNSUPPORTED_RULE", state=Assessment.UNKNOWN, rule_path=path)
        ],
        limitations=["This rule type is not supported by the synthetic evaluator."],
    )

