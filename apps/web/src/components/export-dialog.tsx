"use client";

import { useState } from "react";
import {
  AlertCircle,
  Download,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  ScrollText,
} from "lucide-react";
import { Dialog } from "./ui";
import { statusOf, type Decisions, type Entry } from "@/lib/contracts";
import { downloadResults, type ExportFormat } from "@/lib/export";

export function ExportDialog({
  source,
  entries,
  filtered,
  decisions,
  company,
  onClose,
  onExport,
}: {
  source: string;
  company: string | null;
  entries: Entry[];
  filtered: Entry[];
  decisions: Decisions;
  onClose: () => void;
  onExport: (count: number) => void;
}) {
  const [format, setFormat] = useState<ExportFormat>("csv");
  const [scope, setScope] = useState("all");
  const chosen =
    scope === "filtered"
      ? filtered
      : scope === "ready"
        ? entries.filter(({ prediction }) => statusOf(prediction, decisions) !== "review")
        : entries;
  const pending = chosen.filter(
    ({ prediction }) => statusOf(prediction, decisions) === "review",
  ).length;
  return (
    <Dialog title="Export your classifications" onClose={onClose}>
      <p className="dialog-intro">
        Your final voucher types, with the original decisions kept intact.
      </p>
      <fieldset className="export-formats">
        <legend>File format</legend>
        {(
          [
            {
              id: "csv",
              name: "Spreadsheet",
              description: "CSV with classifications, confidence and review status",
              Icon: FileSpreadsheet,
            },
            {
              id: "json",
              name: "Classification JSON",
              description: "Invoice number and final voucher type only",
              Icon: FileJson,
            },
            {
              id: "audit",
              name: "Full decision trail",
              description: "JSON with source fields, evidence and your reviews",
              Icon: ScrollText,
            },
            {
              id: "tally",
              name: "TallyPrime XML",
              description: "Voucher headers ready to import and post in TallyPrime",
              Icon: FileCode2,
            },
          ] as const
        ).map(({ id, name, description, Icon }) => (
          <label className={format === id ? "selected" : ""} key={id}>
            <input
              type="radio"
              name="format"
              value={id}
              checked={format === id}
              onChange={() => setFormat(id)}
            />
            <Icon size={21} />
            <span>
              <strong>{name}</strong>
              <small>{description}</small>
            </span>
          </label>
        ))}
      </fieldset>
      <label className="form-label" htmlFor="export-scope">
        Transactions to include
      </label>
      <select id="export-scope" value={scope} onChange={(event) => setScope(event.target.value)}>
        <option value="all">All transactions ({entries.length})</option>
        <option value="filtered">Current filtered view ({filtered.length})</option>
        <option value="ready">
          Ready and reviewed only (
          {entries.filter(({ prediction }) => statusOf(prediction, decisions) !== "review").length})
        </option>
      </select>
      {pending > 0 && (
        <div className="export-warning">
          <AlertCircle size={17} />
          <p>
            {pending} {pending === 1 ? "entry still needs" : "entries still need"} review.{" "}
            {format === "json"
              ? "Classification JSON does not include review status."
              : "They will keep their review status in this export."}
          </p>
        </div>
      )}
      <div className="dialog-actions">
        <button className="button secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          className="button primary"
          disabled={!chosen.length}
          onClick={() => {
            downloadResults(source, chosen, decisions, format, company);
            onExport(chosen.length);
            onClose();
          }}
        >
          <Download size={16} />
          Export {chosen.length} {chosen.length === 1 ? "entry" : "entries"}
        </button>
      </div>
    </Dialog>
  );
}
