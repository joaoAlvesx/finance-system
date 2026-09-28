from datetime import date
from decimal import Decimal

import pytest

from app.services.csv_import import CSVImportError, file_sha256, parse_inter_csv


def inter_csv(*rows: str) -> bytes:
    content = [
        "Extrato Conta Corrente;",
        "Conta;DADOS OMITIDOS",
        "Período;01/01/2026 a 31/01/2026",
        ";",
        ";",
        "Data Lançamento;Histórico;Descrição;Valor;Saldo",
        *rows,
    ]
    return ("\ufeff" + "\n".join(content)).encode()


def test_inter_parser_handles_preamble_signed_brl_and_invalid_rows() -> None:
    parsed = parse_inter_csv(
        inter_csv(
            "10/01/2026;Compra no débito;MERCADO TESTE;- 82,40;917,60",
            "09/01/2026;Pix recebido;PESSOA TESTE;1.000,00;1.000,00",
            "data ruim;Pix enviado;PESSOA TESTE;- 10,00;990,00",
        )
    )

    assert parsed.encoding == "utf-8-sig"
    assert parsed.delimiter == ";"
    assert parsed.header_row_number == 6
    assert len(parsed.rows) == 3
    debit, credit, invalid = parsed.rows
    assert debit.transaction_date == date(2026, 1, 10)
    assert debit.amount == Decimal("82.40")
    assert debit.direction == "debit"
    assert credit.amount == Decimal("1000.00")
    assert credit.direction == "credit"
    assert invalid.error_codes == ("invalid_date",)


def test_inter_parser_rejects_missing_required_columns() -> None:
    with pytest.raises(CSVImportError, match="required_columns_not_found"):
        parse_inter_csv(b"date,description,value\n2026-01-01,test,10")


def test_file_hash_is_stable() -> None:
    assert file_sha256(b"same") == file_sha256(b"same")
    assert file_sha256(b"same") != file_sha256(b"different")
