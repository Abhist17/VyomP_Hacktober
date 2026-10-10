import type { LedgerRow } from "./contracts";

export function amount(row: LedgerRow) {
  if (row.amount == null)
    return row.quantity != null ? `${row.quantity} ${row.unit || "units"}` : "—";
  const currency = row.currency || "INR";
  try {
    // Lakh grouping for rupees; international grouping for foreign currencies.
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(row.amount);
  } catch {
    return `${currency} ${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(row.amount)}`;
  }
}
export function date(value: LedgerRow["date"]) {
  if (!value) return "No date";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
  if (!match) return String(value);
  return new Date(`${match[1]}-${match[2]}-${match[3]}T00:00:00Z`).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
const SOURCE_NAMES: Record<string, string> = {
  slm: "Language model (SLM)",
  rules: "Rules",
  sentinel: "Sentinel classifier",
  precedents: "Precedents",
};
export function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/^./, (char) => char.toUpperCase());
}
export function sourceName(value: string) {
  return SOURCE_NAMES[value] ?? humanize(value);
}
export function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export const SIGNALS: Record<string, string> = {
  company_is_seller: "Your company is the seller",
  company_is_buyer: "Your company is the buyer",
  has_money: "A monetary amount is present",
  debit_leg_own_cash_bank: "The debit account belongs to your company",
  credit_leg_own_cash_bank: "The credit account belongs to your company",
  both_legs_own_cash_bank: "Both accounts belong to your company",
  payment_instrument: "A payment method is recorded",
  has_invoice_values: "Invoice values are present",
  references_other_document: "References an earlier document",
  negative_value: "The transaction has a negative value",
  order_without_movement: "An order with no movement recorded",
  has_gst: "GST is recorded",
  sac_service: "The SAC code identifies a service",
  quantity_without_value: "Quantity moves without a monetary value",
  has_challan: "Delivery or transport details are present",
  has_grn: "A goods receipt note is present",
  godown_transfer: "Stock moves between godowns",
  stock_count: "A physical stock count is recorded",
  job_work: "Job-work details are present",
  payroll_components: "A salary breakdown is present",
  attendance_fields: "Attendance or overtime is recorded",
  employee_present: "An employee is identified",
  import_documents: "Import documentation is present",
  export_documents: "Export documentation is present",
  foreign_currency: "The transaction uses a foreign currency",
};
