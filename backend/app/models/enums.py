from enum import StrEnum


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    OTHER = "other"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class TransactionDirection(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    IGNORED = "ignored"


class TransactionSource(StrEnum):
    MANUAL = "manual"
    CSV = "csv"
    PLUGGY = "pluggy"
    TELEGRAM = "telegram"


class ClassificationMethod(StrEnum):
    MANUAL = "manual"
    RULE = "rule"
    HISTORY = "history"
    AI = "ai"
    PLUGGY = "pluggy"


class BalanceSnapshotSource(StrEnum):
    INITIAL = "initial"
    MANUAL = "manual"
    CSV = "csv"
    PLUGGY = "pluggy"
    RECONCILIATION = "reconciliation"


class CategoryKind(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    BOTH = "both"


class Recurrence(StrEnum):
    NONE = "none"
    MONTHLY = "monthly"


class ExpectedIncomeStatus(StrEnum):
    EXPECTED = "expected"
    RECEIVED = "received"
    LATE = "late"
    CANCELLED = "cancelled"


class PlannedExpenseStatus(StrEnum):
    PLANNED = "planned"
    PAID = "paid"
    LATE = "late"
    CANCELLED = "cancelled"


class SafeSpendingMode(StrEnum):
    UNTIL_NEXT_INCOME = "until_next_income"


class RuleMatchField(StrEnum):
    DESCRIPTION = "description"
    MERCHANT = "merchant"
    EXTERNAL_ID = "external_id"


class RuleOrigin(StrEnum):
    MANUAL = "manual"
    CONFIRMED_CORRECTION = "confirmed_correction"


class AuditActorType(StrEnum):
    USER = "user"
    SERVICE = "service"
    SYSTEM = "system"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class SyncRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class SyncTrigger(StrEnum):
    CONNECTION = "connection"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class ImportStatus(StrEnum):
    PREVIEWED = "previewed"
    IMPORTED = "imported"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportRowStatus(StrEnum):
    VALID = "valid"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    INVALID = "invalid"
    IMPORTED = "imported"


class CategorySuggestionStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
