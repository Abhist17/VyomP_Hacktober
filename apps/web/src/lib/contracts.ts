import { z } from "zod";

export const familySchema = z.object({ name: z.string(), labels: z.array(z.string()) });
export const predictionSchema = z.object({
  schema_version: z.string(),
  row_id: z.number().int(),
  invoice_number: z.string().nullable(),
  voucher_type: z.string(),
  confidence: z.number().min(0).max(1),
  prediction_set: z.array(z.string()),
  alternatives: z.array(z.object({ voucher_type: z.string(), probability: z.number() })),
  needs_review: z.boolean(),
  explanation: z.string(),
  evidence: z.array(
    z.object({
      signal: z.string(),
      value: z.union([z.boolean(), z.string(), z.number(), z.null()]),
      fields: z.array(z.string()),
    }),
  ),
  decided_by: z.string(),
  model_version: z.string(),
  policy_version: z.string(),
});
const scalar = z.union([z.string(), z.number(), z.boolean(), z.null()]);
export const rowSchema = z.object({
  row_id: z.number().int(),
  date: scalar,
  number: scalar,
  party: scalar,
  amount: z.number().nullable(),
  currency: z.string().nullable(),
  quantity: scalar,
  unit: scalar,
  item: scalar,
  narration: scalar,
  fields: z.array(z.object({ field: z.string(), header: z.string(), value: z.unknown() })),
});
export const workbenchSchema = z
  .object({
    source: z.string(),
    company: z.object({
      gstin: z.string().nullable(),
      name: z.string().nullable(),
      how: z.string(),
      own_accounts: z.array(z.string()),
    }),
    mappings: z.array(
      z.object({
        header: z.string(),
        field: z.string().nullable(),
        stage: z.string(),
        score: z.number(),
      }),
    ),
    families: z.array(familySchema),
    rows: z.array(rowSchema),
    predictions: z.array(predictionSchema),
  })
  .superRefine((data, ctx) => {
    const rows = new Set(data.rows.map((row) => row.row_id));
    const predictions = new Set(data.predictions.map((prediction) => prediction.row_id));
    if (
      rows.size !== data.rows.length ||
      predictions.size !== data.predictions.length ||
      rows.size !== predictions.size ||
      [...rows].some((id) => !predictions.has(id))
    ) {
      ctx.addIssue({
        code: "custom",
        message: "Transaction and prediction identifiers do not match.",
      });
    }
  });
export const modelSchema = z.object({
  viveka_version: z.string(),
  policy_version: z.string(),
  slm: z.record(z.string(), z.unknown()),
  evaluation: z.unknown(),
});

export type Family = z.infer<typeof familySchema>;
export type Prediction = z.infer<typeof predictionSchema>;
export type LedgerRow = z.infer<typeof rowSchema>;
export type WorkbenchData = z.infer<typeof workbenchSchema>;
export type ModelCard = z.infer<typeof modelSchema>;
export type Decision = { label: string; reviewed_at: string };
export type Decisions = Record<number, Decision>;
export type Entry = { row: LedgerRow; prediction: Prediction };

export function entriesOf(data: WorkbenchData): Entry[] {
  const predictions = new Map(
    data.predictions.map((prediction) => [prediction.row_id, prediction]),
  );
  return data.rows.map((row) => ({ row, prediction: predictions.get(row.row_id)! }));
}

export function statusOf(prediction: Prediction, decisions: Decisions) {
  const decision = decisions[prediction.row_id];
  if (decision) return decision.label === prediction.voucher_type ? "reviewed" : "corrected";
  return prediction.needs_review ? "review" : "ready";
}

export function labelOf(prediction: Prediction, decisions: Decisions) {
  return decisions[prediction.row_id]?.label ?? prediction.voucher_type;
}
