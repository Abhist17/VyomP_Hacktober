import { labelOf, statusOf, type Decisions, type Entry } from "./contracts";

function csvCell(value: unknown): string {
  // Neutralise spreadsheet formulas in user-controlled strings; preserve numeric negatives.
  let text = value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  if (typeof value === "string" && /^[\s]*[=+@\-\t\r\n]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function exportContent(
  entries: Entry[],
  decisions: Decisions,
  format: "csv" | "json" | "audit",
) {
  if (format === "json")
    return JSON.stringify(
      entries.map(({ prediction }) => ({
        invoice_number: prediction.invoice_number,
        voucher_type: labelOf(prediction, decisions),
      })),
      null,
      2,
    );
  if (format === "audit")
    return JSON.stringify(
      entries.map(({ row, prediction }) => ({
        transaction: row,
        prediction,
        voucher_type: labelOf(prediction, decisions),
        review: decisions[row.row_id] ?? null,
        status: statusOf(prediction, decisions),
      })),
      null,
      2,
    );
  const headings = [
    "row_id",
    "invoice_number",
    "date",
    "counterparty",
    "amount",
    "currency",
    "voucher_type",
    "original_voucher_type",
    "model_confidence",
    "status",
    "explanation",
    "reviewed_at",
  ];
  const rows = entries.map(({ row, prediction }) => [
    row.row_id,
    prediction.invoice_number ?? row.number,
    row.date,
    row.party,
    row.amount,
    row.currency || "INR",
    labelOf(prediction, decisions),
    prediction.voucher_type,
    prediction.confidence,
    statusOf(prediction, decisions),
    prediction.explanation,
    decisions[row.row_id]?.reviewed_at,
  ]);
  return "\uFEFF" + [headings, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
}

export function downloadResults(
  source: string,
  entries: Entry[],
  decisions: Decisions,
  format: "csv" | "json" | "audit",
) {
  const extension = format === "csv" ? "csv" : "json";
  const name = source.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_");
  const url = URL.createObjectURL(
    new Blob([exportContent(entries, decisions, format)], {
      type: format === "csv" ? "text/csv;charset=utf-8" : "application/json",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name}-${format === "audit" ? "audit" : "classified"}.${extension}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
