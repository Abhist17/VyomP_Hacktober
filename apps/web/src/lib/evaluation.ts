import { z } from "zod";

// Held-out evaluation published by the backend on /v1/model-card (`viveka tune-fusion`).
export const evaluationSchema = z.object({
  split: z.string(),
  rows: z.number(),
  selected: z.string(),
  results: z.array(
    z.object({
      name: z.string(),
      description: z.string(),
      accuracy: z.number(),
      macro_f1: z.number(),
      auto_accept_precision: z.number().nullable(),
      auto_accept_coverage: z.number().nullable(),
    }),
  ),
});
export type Evaluation = z.infer<typeof evaluationSchema>;

export function parseEvaluation(value: unknown): Evaluation | null {
  const parsed = evaluationSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

/** The configuration the backend reports as in use, if any. */
export function selectedResult(evaluation: Evaluation | null) {
  return evaluation?.results.find((result) => result.name === evaluation.selected) ?? null;
}
