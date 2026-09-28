from datetime import date
from decimal import Decimal
from uuid import UUID

from app.services.deduplication import (
    descriptions_share_recipient,
    normalize_description,
    recipient_label,
    recipient_rule_pattern,
    transaction_deduplication_hash,
)


def test_description_normalization_is_stable() -> None:
    assert normalize_description("  CAFÉ   São João ") == "cafe sao joao"


def test_recipient_variations_are_grouped_conservatively() -> None:
    purchase = "Compra no débito — PALADARNUTRI BOA VISTA BRA"
    pix = "Pix enviado — PaladarNutri Ltda"

    assert recipient_label(pix) == "paladarnutri"
    assert descriptions_share_recipient(purchase, pix)
    assert recipient_rule_pattern(purchase, [purchase, pix]) == "paladarnutri"
    assert not descriptions_share_recipient(
        "Compra no débito — MERCADO CENTRAL",
        "Pix enviado — MERCADO NOVO",
    )


def test_equivalent_transactions_have_the_same_hash() -> None:
    account_id = UUID("a9020bec-0b11-4d70-8fc9-a584474427cb")
    first = transaction_deduplication_hash(
        account_id=account_id,
        transaction_date=date(2026, 9, 10),
        description="Mercado São João",
        amount=Decimal("10.0"),
        direction="debit",
    )
    second = transaction_deduplication_hash(
        account_id=account_id,
        transaction_date=date(2026, 9, 10),
        description=" mercado  sao joao ",
        amount=Decimal("10.00"),
        direction="debit",
    )

    assert first == second
    assert len(first) == 64
