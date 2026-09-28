from uuid import UUID

from app.services.category_rules import CategoryRuleCandidate, RuleField, select_category_rule


def test_rule_priority_and_account_scope_are_deterministic() -> None:
    account_id = UUID("a9020bec-0b11-4d70-8fc9-a584474427cb")
    global_rule = CategoryRuleCandidate(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        category_id=UUID("00000000-0000-0000-0000-000000000010"),
        pattern="mercado",
        priority=100,
    )
    scoped_rule = CategoryRuleCandidate(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        category_id=UUID("00000000-0000-0000-0000-000000000020"),
        pattern="mercado",
        priority=100,
        account_id=account_id,
    )

    selected = select_category_rule(
        description="Mercado do bairro", account_id=account_id, rules=[global_rule, scoped_rule]
    )

    assert selected == scoped_rule


def test_explicit_rule_matching_does_not_guess() -> None:
    account_id = UUID("a9020bec-0b11-4d70-8fc9-a584474427cb")
    rule = CategoryRuleCandidate(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        category_id=UUID("00000000-0000-0000-0000-000000000010"),
        pattern="academia",
        priority=100,
    )
    assert (
        select_category_rule(description="Supermercado", account_id=account_id, rules=[rule])
        is None
    )


def test_external_id_rule_requires_an_exact_match() -> None:
    account_id = UUID("a9020bec-0b11-4d70-8fc9-a584474427cb")
    rule = CategoryRuleCandidate(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        category_id=UUID("00000000-0000-0000-0000-000000000010"),
        pattern="bank-123",
        priority=100,
        match_field=RuleField.EXTERNAL_ID,
    )

    assert (
        select_category_rule(
            description="ignored",
            account_id=account_id,
            external_id="BANK-123",
            rules=[rule],
        )
        == rule
    )
    assert (
        select_category_rule(
            description="ignored",
            account_id=account_id,
            external_id="bank-123-extra",
            rules=[rule],
        )
        is None
    )
