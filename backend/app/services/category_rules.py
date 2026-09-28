from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.services.deduplication import normalize_description


class RuleField(StrEnum):
    DESCRIPTION = "description"
    MERCHANT = "merchant"
    EXTERNAL_ID = "external_id"


@dataclass(frozen=True, slots=True)
class CategoryRuleCandidate:
    id: UUID
    category_id: UUID
    pattern: str
    priority: int
    match_field: RuleField = RuleField.DESCRIPTION
    account_id: UUID | None = None
    active: bool = True


def select_category_rule(
    *,
    description: str,
    account_id: UUID,
    rules: list[CategoryRuleCandidate],
    merchant_name: str | None = None,
    external_id: str | None = None,
) -> CategoryRuleCandidate | None:
    values = {
        RuleField.DESCRIPTION: normalize_description(description),
        RuleField.MERCHANT: normalize_description(merchant_name or ""),
        RuleField.EXTERNAL_ID: (external_id or "").casefold().strip(),
    }
    matching: list[CategoryRuleCandidate] = []
    for rule in rules:
        if not rule.active or rule.account_id not in {None, account_id}:
            continue
        candidate = values[rule.match_field]
        pattern = (
            rule.pattern.casefold().strip()
            if rule.match_field == RuleField.EXTERNAL_ID
            else normalize_description(rule.pattern)
        )
        matches = (
            candidate == pattern
            if rule.match_field == RuleField.EXTERNAL_ID
            else pattern in candidate
        )
        if pattern and matches:
            matching.append(rule)
    if not matching:
        return None
    return min(
        matching,
        key=lambda rule: (
            -rule.priority,
            -(rule.account_id == account_id),
            str(rule.id),
        ),
    )
