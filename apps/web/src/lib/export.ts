import { labelOf, statusOf, type Decisions, type Entry } from "./contracts";

function csvCell(value: unknown): string {
  // Neutralise spreadsheet formulas in user-controlled strings; preserve numeric negatives.
  let text = value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  if (typeof value === "string" && /^[\s]*[=+@\-\t\r\n]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export type ExportFormat = "csv" | "json" | "audit" | "tally";

// TallyPrime's predefined voucher types. Labels without a Tally equivalent import as their
// nearest base type; the Viveka label travels in the narration for the accountant to see.
const TALLY_TYPES: Record<string, string> = {
  "Purchase Return / Debit Note": "Debit Note",
  "Sales Return / Credit Note": "Credit Note",
  "Salary / Payroll": "Payroll",
  "Rejection In": "Rejections In",
  "Rejection Out": "Rejections Out",
  Import: "Purchase",
  Export: "Sales",
  Expense: "Journal",
  "Advance / Prepayment": "Payment",
  "Other / Miscellaneous": "Journal",
};

function xml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function tallyType(label: string) {
  return TALLY_TYPES[label] ?? label;
}

function tallyXml(entries: Entry[], decisions: Decisions, company: string | null) {
  const vouchers = entries.map(({ row, prediction }) => {
    const label = labelOf(prediction, decisions);
    const type = tallyType(label);
    const day = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(row.date ?? ""));
    const narration = [
      `Viveka: ${label} (${Math.round(prediction.confidence * 100)}%, ${statusOf(prediction, decisions)})`,
      row.amount != null ? `Amount ${row.currency || "INR"} ${row.amount}` : "",
      row.narration ?? "",
    ]
      .filter(Boolean)
      .join(" | ");
    return [
      `    <TALLYMESSAGE xmlns:UDF="TallyUDF">`,
      `      <VOUCHER VCHTYPE="${xml(type)}" ACTION="Create">`,
      day ? `        <DATE>${day[1]}${day[2]}${day[3]}</DATE>` : "",
      `        <VOUCHERTYPENAME>${xml(type)}</VOUCHERTYPENAME>`,
      row.number != null ? `        <VOUCHERNUMBER>${xml(row.number)}</VOUCHERNUMBER>` : "",
      row.party ? `        <PARTYLEDGERNAME>${xml(row.party)}</PARTYLEDGERNAME>` : "",
      `        <NARRATION>${xml(narration)}</NARRATION>`,
      `      </VOUCHER>`,
      `    </TALLYMESSAGE>`,
    ]
      .filter(Boolean)
      .join("\n");
  });
  return [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<!-- Viveka voucher headers for TallyPrime. Review ledger allocations before posting. -->`,
    `<ENVELOPE>`,
    `  <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>`,
    `  <BODY><IMPORTDATA>`,
    `  <REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME>`,
    company
      ? `  <STATICVARIABLES><SVCURRENTCOMPANY>${xml(company)}</SVCURRENTCOMPANY></STATICVARIABLES>`
      : "",
    `  </REQUESTDESC>`,
    `  <REQUESTDATA>`,
    ...vouchers,
    `  </REQUESTDATA>`,
    `  </IMPORTDATA></BODY>`,
    `</ENVELOPE>`,
  ]
    .filter(Boolean)
    .join("\n");
}

export function exportContent(
  entries: Entry[],
  decisions: Decisions,
  format: ExportFormat,
  company: string | null = null,
) {
  if (format === "tally") return tallyXml(entries, decisions, company);
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
  format: ExportFormat,
  company: string | null = null,
) {
  const extension = format === "csv" ? "csv" : format === "tally" ? "xml" : "json";
  const name = source.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_");
  const url = URL.createObjectURL(
    new Blob([exportContent(entries, decisions, format, company)], {
      type:
        format === "csv"
          ? "text/csv;charset=utf-8"
          : format === "tally"
            ? "application/xml"
            : "application/json",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name}-${format === "audit" ? "audit" : format === "tally" ? "tally" : "classified"}.${extension}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
