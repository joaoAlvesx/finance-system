export type Money = string;

export interface Account {
  id: string;
  name: string;
  institution_name: string | null;
  type: string;
  currency_code: string;
  initial_balance: Money;
  is_active: boolean;
}

export interface Category {
  id: string;
  name: string;
  color: string | null;
  icon: string | null;
  kind: "expense" | "income" | "both";
}

export interface Transaction {
  id: string;
  account_id: string;
  type: "income" | "expense" | "transfer";
  direction: "credit" | "debit";
  status: "pending" | "posted" | "ignored";
  amount: Money;
  transaction_date: string;
  description_raw: string;
  category_id: string | null;
  source: string;
  classification_method: string;
  is_reviewed: boolean;
}

export interface TransactionPage {
  items: Transaction[];
  next_cursor: string | null;
}

export interface CategoryTotal {
  category_id: string | null;
  category_name: string;
  amount: Money;
}

export interface Dashboard {
  generated_at: string;
  current_balance: Money;
  available_until_next_income: Money | null;
  daily_safe_limit: Money | null;
  committed_expenses: Money;
  deficit: Money;
  minimum_reserve: Money;
  month_income: Money;
  month_expense: Money;
  review_count: number;
  uncategorized_count: number;
  next_income: {
    id: string;
    name: string;
    expected_amount: Money;
    expected_date: string;
  } | null;
  spending_by_category: CategoryTotal[];
  recent_transactions: Transaction[];
}

export interface ExpectedIncome {
  id: string;
  name: string;
  expected_amount: Money;
  expected_date: string;
  recurrence: "none" | "monthly";
  amount_is_variable: boolean;
  status: string;
}

export interface PlannedExpense {
  id: string;
  name: string;
  expected_amount: Money;
  due_date: string;
  recurrence: "none" | "monthly";
  amount_is_variable: boolean;
  category_id: string | null;
  status: string;
}

export interface BudgetSettings {
  id: string;
  minimum_reserve: Money;
  include_pending_transactions: boolean;
  telegram_notifications_enabled: boolean;
  timezone: string;
}

export interface ImportRow {
  row_number: number;
  transaction_date: string | null;
  historical_label: string | null;
  description: string | null;
  amount: Money | null;
  direction: "credit" | "debit" | null;
  status: "valid" | "possible_duplicate" | "invalid" | "imported";
  error_codes: string[];
  suggested_category_id: string | null;
}

export interface ImportPreview {
  id: string;
  account_id: string;
  filename: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  possible_duplicate_rows: number;
  invalid_rows: number;
  imported_rows: number;
  period_start: string | null;
  period_end: string | null;
  net_amount: Money | null;
  rows: ImportRow[];
  row_offset: number;
  row_limit: number;
  has_more_rows: boolean;
}

export interface PluggyAccount {
  id: string;
  local_account_id: string | null;
  external_account_id: string;
  name: string;
  account_type: string;
  subtype: string | null;
  currency_code: string;
  balance: Money | null;
  last_seen_at: string;
  is_active: boolean;
}

export interface PluggyItem {
  id: string;
  external_item_id: string;
  connector_id: number | null;
  connector_name: string | null;
  status: string;
  execution_status: string | null;
  error_code: string | null;
  requires_user_action: boolean;
  consent_expires_at: string | null;
  last_successful_sync_at: string | null;
  last_full_sync_at: string | null;
  next_sync_at: string | null;
  accounts: PluggyAccount[];
}

export interface PluggySyncRun {
  id: string;
  pluggy_item_id: string | null;
  status: "pending" | "running" | "success" | "partial" | "failed";
  trigger: "connection" | "manual" | "scheduled";
  full_reconciliation: boolean;
  started_at: string | null;
  finished_at: string | null;
  accounts_consulted: number;
  created_count: number;
  updated_count: number;
  reconciled_count: number;
  ignored_count: number;
  error_code: string | null;
}

export interface PluggyStatus {
  enabled: boolean;
  configured: boolean;
  connector_id: number;
  include_sandbox: boolean;
  polling_seconds: number;
  provider_refresh_note: string;
  items: PluggyItem[];
  latest_run: PluggySyncRun | null;
}

export type AssistantValueKind = "calculated" | "prediction" | "suggestion";

export interface AssistantInsight {
  key: string;
  title: string;
  text: string;
  value_kind: AssistantValueKind;
  severity: "neutral" | "attention";
}

export interface AssistantInsights {
  generated_at: string;
  cards: AssistantInsight[];
  suggested_questions: string[];
}

export interface AssistantAnswer {
  intent: string;
  value_kind: AssistantValueKind;
  answer: string;
  data: Record<string, unknown>;
}

export interface CategorySuggestion {
  id: string;
  transaction_id: string;
  transaction_description: string;
  transaction_amount: Money;
  suggested_category_id: string;
  suggested_category_name: string;
  confidence: string;
  rationale_code: string;
  status: "pending" | "accepted" | "rejected";
  suggested_by: string;
  created_at: string;
}
