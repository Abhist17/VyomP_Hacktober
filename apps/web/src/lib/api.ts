import { z } from "zod";
import { workbenchSchema } from "./contracts";

export const MAX_FILE_SIZE = 20 * 1024 * 1024;
export const ACCEPTED_FILES = ".csv,.xlsx,.xls,.xlsm,.json,.jsonl";

export function validateFile(file: File): string | null {
  if (!/\.(csv|xlsx|xls|xlsm|json|jsonl)$/i.test(file.name))
    return "Choose an Excel, CSV, JSON or JSONL file.";
  if (file.size === 0) return "This file is empty. Choose a ledger with transaction rows.";
  if (file.size > MAX_FILE_SIZE)
    return "This file exceeds 20 MB. Split the ledger into smaller files and try again.";
  return null;
}

export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/viveka/${path}`, { ...options, cache: "no-store" });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error("The service returned an unreadable response. Try again.");
  }
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `The request failed (${response.status}). Check your file and try again.`,
    );
  }
  const result = schema.safeParse(body);
  if (!result.success)
    throw new Error(
      "The service returned an unexpected data format. Check that the frontend and backend versions match.",
    );
  return result.data;
}

export async function loadLedger(source: File | "sample", gstin: string, signal: AbortSignal) {
  const options: RequestInit = { signal };
  let path = "workbench/sample";
  if (source === "sample") {
    if (gstin) path += `?company_gstin=${encodeURIComponent(gstin)}`;
  } else {
    const error = validateFile(source);
    if (error) throw new Error(error);
    const body = new FormData();
    body.append("file", source);
    if (gstin) body.append("company_gstin", gstin);
    Object.assign(options, { method: "POST", body });
    path = "workbench";
  }
  const data = await request(path, workbenchSchema, options);
  if (!data.rows.length)
    throw new Error(
      "No transaction rows were found. Include a header row and at least one transaction.",
    );
  return data;
}
