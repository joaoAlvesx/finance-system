"""Add idempotent CSV imports and initial categories.

Revision ID: 0002_csv_imports
Revises: 0001_foundation
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_csv_imports"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY_IDS = {
    "Mercado": "10000000-0000-0000-0000-000000000001",
    "Uber": "10000000-0000-0000-0000-000000000002",
    "Alimentação": "10000000-0000-0000-0000-000000000003",
    "Pix": "10000000-0000-0000-0000-000000000004",
    "Contas": "10000000-0000-0000-0000-000000000005",
    "Aluguel": "10000000-0000-0000-0000-000000000006",
    "Transporte": "10000000-0000-0000-0000-000000000007",
    "Saúde": "10000000-0000-0000-0000-000000000008",
    "Educação": "10000000-0000-0000-0000-000000000009",
    "Lazer": "10000000-0000-0000-0000-00000000000a",
    "Assinaturas": "10000000-0000-0000-0000-00000000000b",
    "Compras pessoais": "10000000-0000-0000-0000-00000000000c",
    "Renda": "10000000-0000-0000-0000-00000000000d",
    "Transferências": "10000000-0000-0000-0000-00000000000e",
    "Reembolsos": "10000000-0000-0000-0000-00000000000f",
    "Outros": "10000000-0000-0000-0000-000000000010",
}

PROFILE_ID = "20000000-0000-0000-0000-000000000001"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column(
            "change_data",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "import_profiles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("institution_name", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("encoding", sa.String(40), nullable=False),
        sa.Column("delimiter", sa.String(1), nullable=False),
        sa.Column("date_format", sa.String(40), nullable=False),
        sa.Column("decimal_separator", sa.String(1), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_import_profiles"),
        sa.UniqueConstraint("institution_name", "name", name="uq_import_profile_institution_name"),
    )

    op.create_table(
        "import_files",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid()),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("institution_name", sa.String(120), nullable=False),
        sa.Column("encoding", sa.String(40), nullable=False),
        sa.Column("delimiter", sa.String(1), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            _enum("import_status", "previewed", "imported", "failed", "cancelled"),
            nullable=False,
        ),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("actor_identifier", sa.String(120), nullable=False),
        sa.Column("error_code", sa.String(120)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("file_size > 0", name="file_size_positive"),
        sa.CheckConstraint("total_rows >= 0", name="total_rows_non_negative"),
        sa.CheckConstraint("valid_rows >= 0", name="valid_rows_non_negative"),
        sa.CheckConstraint("duplicate_rows >= 0", name="duplicate_rows_non_negative"),
        sa.CheckConstraint("invalid_rows >= 0", name="invalid_rows_non_negative"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_import_files_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["import_profiles.id"],
            name="fk_import_files_profile_id_import_profiles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_files"),
        sa.UniqueConstraint("account_id", "sha256", name="uq_import_file_account_hash"),
    )
    op.create_index("ix_import_files_account_id", "import_files", ["account_id"])
    op.create_index("ix_import_files_profile_id", "import_files", ["profile_id"])

    op.create_foreign_key(
        "fk_transactions_source_file_id_import_files",
        "transactions",
        "import_files",
        ["source_file_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_transactions_source_file_id", "transactions", ["source_file_id"])

    op.create_table(
        "import_rows",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("import_file_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date()),
        sa.Column("historical_label", sa.String(255)),
        sa.Column("description_raw", sa.String(1000)),
        sa.Column("description_normalized", sa.String(1000)),
        sa.Column("amount", sa.Numeric(14, 2)),
        sa.Column(
            "direction",
            _enum("import_row_direction", "credit", "debit"),
        ),
        sa.Column("balance_after", sa.Numeric(14, 2)),
        sa.Column("deduplication_hash", sa.String(64)),
        sa.Column("raw_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _enum("import_row_status", "valid", "possible_duplicate", "invalid", "imported"),
            nullable=False,
        ),
        sa.Column(
            "error_codes",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("suggested_category_id", sa.Uuid()),
        sa.Column("transaction_id", sa.Uuid()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("row_number > 0", name="row_number_positive"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="amount_positive"),
        sa.ForeignKeyConstraint(
            ["import_file_id"],
            ["import_files.id"],
            name="fk_import_rows_import_file_id_import_files",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_category_id"],
            ["categories.id"],
            name="fk_import_rows_suggested_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name="fk_import_rows_transaction_id_transactions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_rows"),
        sa.UniqueConstraint("import_file_id", "row_number", name="uq_import_row_file_number"),
        sa.UniqueConstraint("transaction_id", name="uq_import_rows_transaction_id"),
    )
    op.create_index("ix_import_rows_import_file_id", "import_rows", ["import_file_id"])
    op.create_index("ix_import_rows_deduplication_hash", "import_rows", ["deduplication_hash"])
    op.create_index(
        "ix_import_rows_suggested_category_id", "import_rows", ["suggested_category_id"]
    )

    now = datetime.now(UTC)
    categories = sa.table(
        "categories",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("color", sa.String()),
        sa.column("icon", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    category_definitions = [
        ("Mercado", "expense", "#2DD4A8", "shopping-basket"),
        ("Uber", "expense", "#38BDF8", "car"),
        ("Alimentação", "expense", "#FBBF24", "utensils"),
        ("Pix", "both", "#94A3B8", "qr-code"),
        ("Contas", "expense", "#FB7185", "receipt"),
        ("Aluguel", "expense", "#7C5CFC", "house"),
        ("Transporte", "expense", "#38BDF8", "bus"),
        ("Saúde", "expense", "#2DD4A8", "heart-pulse"),
        ("Educação", "expense", "#FBBF24", "graduation-cap"),
        ("Lazer", "expense", "#7C5CFC", "gamepad"),
        ("Assinaturas", "expense", "#FB7185", "repeat"),
        ("Compras pessoais", "expense", "#94A3B8", "shopping-bag"),
        ("Renda", "income", "#2DD4A8", "wallet"),
        ("Transferências", "both", "#38BDF8", "arrow-left-right"),
        ("Reembolsos", "income", "#FBBF24", "rotate-ccw"),
        ("Outros", "both", "#94A3B8", "circle-ellipsis"),
    ]
    op.bulk_insert(
        categories,
        [
            {
                "id": CATEGORY_IDS[name],
                "name": name,
                "kind": kind,
                "color": color,
                "icon": icon,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for name, kind, color, icon in category_definitions
        ],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO import_profiles
                (id, institution_name, name, encoding, delimiter, date_format,
                 decimal_separator, column_mapping, is_active, created_at, updated_at)
            VALUES
                ('20000000-0000-0000-0000-000000000001', 'INTER',
                 'Extrato Conta Corrente CSV', 'utf-8-sig', ';', '%d/%m/%Y', ',',
                 '{"date":"Data Lançamento","historical_label":"Histórico",
                   "description":"Descrição","amount":"Valor","balance":"Saldo"}'::jsonb,
                 true, now(), now())
            """
        )
    )

    rules = sa.table(
        "category_rules",
        sa.column("id", sa.Uuid()),
        sa.column("match_field", sa.String()),
        sa.column("pattern", sa.String()),
        sa.column("category_id", sa.Uuid()),
        sa.column("priority", sa.Integer()),
        sa.column("hit_count", sa.Integer()),
        sa.column("origin", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rule_definitions = [
        ("Uber", "uber", 250),
        ("Mercado", "supermercado", 240),
        ("Mercado", "mercado", 230),
        ("Mercado", "atacadao", 230),
        ("Mercado", "assai", 230),
        ("Alimentação", "ifood", 240),
        ("Alimentação", "restaurante", 220),
        ("Alimentação", "lanchonete", 220),
        ("Alimentação", "padaria", 210),
        ("Aluguel", "aluguel", 250),
        ("Saúde", "farmacia", 230),
        ("Saúde", "drogaria", 230),
        ("Saúde", "drogasil", 230),
        ("Assinaturas", "netflix", 230),
        ("Assinaturas", "spotify", 230),
        ("Contas", "aguas guariroba", 240),
        ("Contas", "energisa", 240),
        ("Contas", "recarga", 210),
        ("Renda", "salario", 240),
        ("Transferências", "transferencia enviada", 180),
        ("Transferências", "transferencia recebida", 180),
        ("Transferências", "aplicacao", 180),
        ("Transferências", "resgate", 180),
        ("Reembolsos", "estorno", 200),
        ("Pix", "pix enviado", 50),
        ("Pix", "pix recebido", 50),
    ]
    op.bulk_insert(
        rules,
        [
            {
                "id": f"30000000-0000-0000-0000-{index:012x}",
                "match_field": "description",
                "pattern": pattern,
                "category_id": CATEGORY_IDS[category],
                "priority": priority,
                "hit_count": 0,
                "origin": "manual",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for index, (category, pattern, priority) in enumerate(rule_definitions, start=1)
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_import_rows_suggested_category_id", table_name="import_rows")
    op.drop_index("ix_import_rows_deduplication_hash", table_name="import_rows")
    op.drop_index("ix_import_rows_import_file_id", table_name="import_rows")
    op.drop_table("import_rows")
    op.drop_index("ix_transactions_source_file_id", table_name="transactions")
    op.drop_constraint(
        "fk_transactions_source_file_id_import_files", "transactions", type_="foreignkey"
    )
    op.drop_index("ix_import_files_profile_id", table_name="import_files")
    op.drop_index("ix_import_files_account_id", table_name="import_files")
    op.drop_table("import_files")
    op.drop_table("import_profiles")
    rule_ids = [f"30000000-0000-0000-0000-{index:012x}" for index in range(1, 27)]
    rules = sa.table("category_rules", sa.column("id", sa.Uuid()))
    categories = sa.table("categories", sa.column("id", sa.Uuid()))
    op.execute(rules.delete().where(rules.c.id.in_(rule_ids)))
    op.execute(categories.delete().where(categories.c.id.in_(list(CATEGORY_IDS.values()))))
    op.drop_column("audit_events", "change_data", if_exists=True)
