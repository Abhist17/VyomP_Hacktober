import { describe, expect, it } from "vitest";
import {
  entriesOf,
  labelOf,
  statusOf,
  workbenchSchema,
  type Entry,
  type WorkbenchData,
} from "../src/lib/contracts";
import { exportContent, tallyType } from "../src/lib/export";
import { validateFile, MAX_FILE_SIZE } from "../src/lib/api";

const entry: Entry = {
  row: {
    row_id: 8,
    date: "2026-09-12",
    number: "CN/8",
    party: "Supplier, Ltd",
    amount: -11800,
    currency: "INR",
    quantity: null,
    unit: null,
    item: null,
    narration: null,
    fields: [],
  },
  prediction: {
    schema_version: "1",
    row_id: 8,
    invoice_number: "CN/8",
    voucher_type: "Sales Return / Credit Note",
    confidence: 0.7,
    prediction_set: ["Sales Return / Credit Note", "Sales"],
    alternatives: [{ voucher_type: "Sales", probability: 0.29 }],
    needs_review: true,
    explanation: 'A "credit note"',
    evidence: [],
    decided_by: "rules",
    model_version: "rules",
    policy_version: "test",
  },
};
const data: WorkbenchData = {
  source: "ledger.csv",
  company: { name: null, gstin: null, how: "inferred", own_accounts: [] },
  families: [],
  mappings: [],
  rows: [entry.row, { ...entry.row, row_id: 42 }],
  predictions: [{ ...entry.prediction, row_id: 42, invoice_number: "CN/42" }, entry.prediction],
};

describe("backend contract", () => {
  it("joins non-contiguous, out-of-order predictions by row_id", () => {
    const parsed = workbenchSchema.parse(data);
    expect(entriesOf(parsed).map(({ prediction }) => prediction.invoice_number)).toEqual([
      "CN/8",
      "CN/42",
    ]);
  });
  it("rejects missing and duplicate predictions before showing mismatched evidence", () => {
    expect(workbenchSchema.safeParse({ ...data, predictions: [entry.prediction] }).success).toBe(
      false,
    );
    expect(
      workbenchSchema.safeParse({ ...data, predictions: [entry.prediction, entry.prediction] })
        .success,
    ).toBe(false);
    expect(workbenchSchema.safeParse({ ...data, rows: [entry.row, entry.row] }).success).toBe(
      false,
    );
  });
  it("rejects impossible confidence values", () => {
    expect(
      workbenchSchema.safeParse({
        ...data,
        predictions: data.predictions.map((prediction) => ({ ...prediction, confidence: 105 })),
      }).success,
    ).toBe(false);
  });
});

describe("human review and export", () => {
  const decisions = {
    8: { label: "Purchase Return / Debit Note", reviewed_at: "2026-10-10T05:00:00.000Z" },
  };
  it("keeps review, correction and model-ready statuses distinct", () => {
    expect(statusOf(entry.prediction, {})).toBe("review");
    expect(statusOf({ ...entry.prediction, needs_review: false }, {})).toBe("ready");
    expect(
      statusOf(entry.prediction, { 8: { ...decisions[8], label: entry.prediction.voucher_type } }),
    ).toBe("reviewed");
    expect(statusOf(entry.prediction, decisions)).toBe("corrected");
    expect(labelOf(entry.prediction, decisions)).toBe("Purchase Return / Debit Note");
  });
  it("exports the exact minimal contract with final labels", () => {
    expect(JSON.parse(exportContent([entry], decisions, "json"))).toEqual([
      { invoice_number: "CN/8", voucher_type: "Purchase Return / Debit Note" },
    ]);
  });
  it("preserves the original prediction and uncertainty in the audit trail", () => {
    const [audit] = JSON.parse(exportContent([entry], decisions, "audit"));
    expect(audit.prediction).toEqual(entry.prediction);
    expect(audit.prediction.confidence).toBe(0.7);
    expect(audit.voucher_type).toBe(decisions[8].label);
    expect(audit.review).toEqual(decisions[8]);
    expect(audit.status).toBe("corrected");
  });
  it("escapes CSV quotes and neutralises formulas without altering negative numeric amounts", () => {
    const csv = exportContent(
      [{ ...entry, row: { ...entry.row, party: '=HYPERLINK("https://example.invalid")' } }],
      decisions,
      "csv",
    );
    expect(csv).toContain('"\'=HYPERLINK(""https://example.invalid"")"');
    expect(csv).toContain('"-11800"');
    expect(csv).toContain('"A ""credit note"""');
    expect(csv).toContain('"0.7"');
    expect(csv.startsWith("\uFEFF")).toBe(true);
  });
  it("maps final labels to TallyPrime voucher types and escapes XML", () => {
    const xml = exportContent(
      [{ ...entry, row: { ...entry.row, party: "A & B <Traders>" } }],
      decisions,
      "tally",
      "Kaveri & Co",
    );
    expect(xml).toContain('<VOUCHER VCHTYPE="Debit Note" ACTION="Create">');
    expect(xml).toContain("<DATE>20260912</DATE>");
    expect(xml).toContain("<VOUCHERNUMBER>CN/8</VOUCHERNUMBER>");
    expect(xml).toContain("<PARTYLEDGERNAME>A &amp; B &lt;Traders&gt;</PARTYLEDGERNAME>");
    expect(xml).toContain("<SVCURRENTCOMPANY>Kaveri &amp; Co</SVCURRENTCOMPANY>");
    expect(xml).toContain("Viveka: Purchase Return / Debit Note (70%, corrected)");
    expect(tallyType("Export")).toBe("Sales");
    expect(tallyType("Contra")).toBe("Contra");
  });
});

describe("ledger validation", () => {
  it("accepts backend file formats and rejects empty, unsupported and oversized inputs", () => {
    for (const name of [
      "ledger.csv",
      "ledger.XLSX",
      "ledger.xls",
      "ledger.xlsm",
      "ledger.json",
      "ledger.jsonl",
    ]) {
      expect(validateFile(new File(["content"], name))).toBeNull();
    }
    expect(validateFile(new File(["content"], "ledger.pdf"))).toMatch(/Excel/);
    expect(validateFile(new File([], "ledger.csv"))).toMatch(/empty/);
    expect(validateFile({ name: "ledger.csv", size: MAX_FILE_SIZE + 1 } as File)).toMatch(/20 MB/);
  });
});
