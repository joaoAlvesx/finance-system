import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.services.deduplication import normalize_description
from app.services.money import money, positive_money

REQUIRED_COLUMNS = {
    "data lancamento": "date",
    "historico": "historical_label",
    "descricao": "description",
    "valor": "amount",
    "saldo": "balance",
}


class CSVImportError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ParsedCSVRow:
    row_number: int
    transaction_date: date | None
    historical_label: str | None
    description_raw: str | None
    description_normalized: str | None
    signed_amount: Decimal | None
    amount: Decimal | None
    direction: str | None
    balance_after: Decimal | None
    raw_fingerprint: str
    error_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedCSV:
    encoding: str
    delimiter: str
    header_row_number: int
    column_mapping: dict[str, str]
    rows: tuple[ParsedCSVRow, ...]


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _decode(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise CSVImportError("unsupported_encoding")


def _parse_decimal_br(value: str) -> Decimal:
    normalized = value.strip().replace("R$", "").replace(" ", "")
    normalized = normalized.replace(".", "").replace(",", ".")
    if not normalized:
        raise InvalidOperation
    parsed = Decimal(normalized)
    if not parsed.is_finite():
        raise InvalidOperation
    return money(parsed)


def _find_layout(text: str) -> tuple[str, list[list[str]], int, dict[str, int]]:
    for delimiter in (";", ",", "\t"):
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        for index, row in enumerate(rows[:20]):
            normalized = [normalize_description(cell.strip()) for cell in row]
            if not REQUIRED_COLUMNS.keys() <= set(normalized):
                continue
            positions = {
                target: normalized.index(source) for source, target in REQUIRED_COLUMNS.items()
            }
            return delimiter, rows, index, positions
    raise CSVImportError("required_columns_not_found")


def parse_inter_csv(content: bytes) -> ParsedCSV:
    if not content:
        raise CSVImportError("empty_file")
    text, encoding = _decode(content)
    delimiter, raw_rows, header_index, positions = _find_layout(text)
    header = raw_rows[header_index]
    column_mapping = {target: header[position].strip() for target, position in positions.items()}
    parsed_rows: list[ParsedCSVRow] = []

    for physical_index, raw_row in enumerate(raw_rows[header_index + 1 :], start=header_index + 2):
        if not any(cell.strip() for cell in raw_row):
            continue
        fingerprint = hashlib.sha256("\x1f".join(raw_row).encode("utf-8")).hexdigest()
        errors: list[str] = []
        expected_width = len(header)
        if len(raw_row) != expected_width:
            parsed_rows.append(
                ParsedCSVRow(
                    row_number=physical_index,
                    transaction_date=None,
                    historical_label=None,
                    description_raw=None,
                    description_normalized=None,
                    signed_amount=None,
                    amount=None,
                    direction=None,
                    balance_after=None,
                    raw_fingerprint=fingerprint,
                    error_codes=("invalid_column_count",),
                )
            )
            continue

        cells = {name: raw_row[position].strip() for name, position in positions.items()}

        try:
            transaction_date = datetime.strptime(cells["date"], "%d/%m/%Y").date()
        except ValueError:
            transaction_date = None
            errors.append("invalid_date")

        historical_label = cells["historical_label"] or None
        detail = cells["description"]
        description_raw = " — ".join(part for part in (historical_label, detail) if part)
        if not description_raw:
            errors.append("missing_description")
            normalized_description = None
        else:
            description_raw = description_raw[:1000]
            normalized_description = normalize_description(description_raw)

        try:
            signed_amount = _parse_decimal_br(cells["amount"])
            if signed_amount == 0:
                raise ValueError
            amount = positive_money(abs(signed_amount))
            direction = "debit" if signed_amount < 0 else "credit"
        except (InvalidOperation, ValueError):
            signed_amount = None
            amount = None
            direction = None
            errors.append("invalid_amount")

        try:
            balance_after = _parse_decimal_br(cells["balance"])
        except InvalidOperation:
            balance_after = None
            errors.append("invalid_balance")

        parsed_rows.append(
            ParsedCSVRow(
                row_number=physical_index,
                transaction_date=transaction_date,
                historical_label=historical_label,
                description_raw=description_raw or None,
                description_normalized=normalized_description,
                signed_amount=signed_amount,
                amount=amount,
                direction=direction,
                balance_after=balance_after,
                raw_fingerprint=fingerprint,
                error_codes=tuple(errors),
            )
        )

    if not parsed_rows:
        raise CSVImportError("no_transaction_rows")
    return ParsedCSV(
        encoding=encoding,
        delimiter=delimiter,
        header_row_number=header_index + 1,
        column_mapping=column_mapping,
        rows=tuple(parsed_rows),
    )
