import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.services.money import positive_money

WHITESPACE = re.compile(r"\s+")
DESCRIPTION_SEPARATOR = re.compile(r"\s+(?:\u2014|\u2013|-)\s+")
BUSINESS_SUFFIXES = {"eireli", "ltda", "mei", "s/a", "sa"}
MINIMUM_RECIPIENT_PREFIX_LENGTH = 8


def normalize_description(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return WHITESPACE.sub(" ", without_marks).strip()


def recipient_label(value: str) -> str:
    """Return the bank description portion that identifies the recipient."""
    normalized = normalize_description(value)
    label = DESCRIPTION_SEPARATOR.split(normalized)[-1]
    tokens = label.split()
    while tokens and tokens[-1].rstrip(".") in BUSINESS_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def descriptions_share_recipient(left: str, right: str) -> bool:
    left_label = recipient_label(left)
    right_label = recipient_label(right)
    if not left_label or not right_label:
        return False
    if left_label == right_label:
        return True
    shorter, longer = sorted((left_label, right_label), key=len)
    return len(shorter) >= MINIMUM_RECIPIENT_PREFIX_LENGTH and longer.startswith(f"{shorter} ")


def recipient_rule_pattern(source: str, matches: list[str]) -> str:
    source_normalized = normalize_description(source)
    labels = {recipient_label(value) for value in matches}
    labels.discard("")
    if len(labels) <= 1:
        return source_normalized
    shortest = min(labels, key=lambda label: (len(label), label))
    if len(shortest) < MINIMUM_RECIPIENT_PREFIX_LENGTH:
        return source_normalized
    return shortest


def transaction_deduplication_hash(
    *,
    account_id: UUID,
    transaction_date: date,
    description: str,
    amount: Decimal,
    direction: str,
) -> str:
    if direction not in {"credit", "debit"}:
        raise ValueError("direction must be credit or debit")
    canonical = "|".join(
        (
            str(account_id),
            transaction_date.isoformat(),
            normalize_description(description),
            format(positive_money(amount), ".2f"),
            direction,
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
