const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "UTC",
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Campo_Grande",
  dateStyle: "short",
  timeStyle: "short",
});

export function formatMoney(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return currencyFormatter.format(Number(value));
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return dateFormatter.format(new Date(`${value}T12:00:00Z`));
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return dateTimeFormatter.format(new Date(value));
}

export function normalizeMoneyInput(value: string): string {
  const clean = value.trim().replace(/\s/g, "").replace("R$", "");
  if (clean.includes(",")) return clean.replace(/\./g, "").replace(",", ".");
  return clean;
}
