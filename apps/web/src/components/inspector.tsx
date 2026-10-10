"use client";

import { useState } from "react";
import { Check, CheckCheck, ChevronRight, FileSearch, RotateCcw, X } from "lucide-react";
import type { Decision, Entry, Family } from "@/lib/contracts";
import { amount, date, display, humanize, sourceName, SIGNALS } from "@/lib/format";

export function Inspector({
  entry,
  families,
  decision,
  onDecide,
  onUndo,
  onClose,
  hasNext,
}: {
  entry: Entry | null;
  families: Family[];
  decision?: Decision;
  onDecide: (label: string) => void;
  onUndo: () => void;
  onClose: () => void;
  hasNext: boolean;
}) {
  if (!entry)
    return (
      <aside className="inspector inspector-empty">
        <FileSearch size={32} strokeWidth={1.25} />
        <h2>The reasoning, right here.</h2>
        <p>
          Select a transaction to inspect its source fields, classification and supporting evidence.
        </p>
      </aside>
    );
  return (
    <InspectorContent
      key={`${entry.row.row_id}-${decision?.label || ""}`}
      {...{ entry, families, decision, onDecide, onUndo, onClose, hasNext }}
    />
  );
}

function InspectorContent({
  entry: { row, prediction },
  families,
  decision,
  onDecide,
  onUndo,
  onClose,
  hasNext,
}: {
  entry: Entry;
  families: Family[];
  decision?: Decision;
  onDecide: (label: string) => void;
  onUndo: () => void;
  onClose: () => void;
  hasNext: boolean;
}) {
  const [label, setLabel] = useState(decision?.label ?? prediction.voucher_type);
  const [tab, setTab] = useState<"reasoning" | "fields">("reasoning");
  const changed = label !== prediction.voucher_type;
  return (
    <aside
      className="inspector"
      id="transaction-inspector"
      tabIndex={-1}
      aria-label={`Transaction ${row.number ?? row.row_id + 1} details`}
    >
      <div className="inspector-heading">
        <span>Transaction details</span>
        <button className="icon-button" aria-label="Close transaction details" onClick={onClose}>
          <X size={16} />
        </button>
      </div>
      <div className="transaction-identity">
        <span className="document-number">
          {display(row.number ?? prediction.invoice_number ?? `Row ${row.row_id + 1}`)}
        </span>
        <h2>{display(row.party || row.item || "Transaction")}</h2>
        <div>
          <span>{date(row.date)}</span>
          <strong>{amount(row)}</strong>
        </div>
      </div>
      <div className="classification">
        <span className="field-caption">Suggested voucher</span>
        <h3>{prediction.voucher_type}</h3>
        <div className="confidence-label">
          <span>Model confidence</span>
          <strong>{Math.round(prediction.confidence * 100)}%</strong>
        </div>
        <div className="confidence-track">
          <span style={{ width: `${prediction.confidence * 100}%` }} />
        </div>
      </div>
      <div className="detail-tabs" role="group" aria-label="Transaction information">
        <button
          aria-pressed={tab === "reasoning"}
          className={tab === "reasoning" ? "active" : ""}
          onClick={() => setTab("reasoning")}
        >
          Reasoning
        </button>
        <button
          aria-pressed={tab === "fields"}
          className={tab === "fields" ? "active" : ""}
          onClick={() => setTab("fields")}
        >
          Source fields <span>{row.fields.length}</span>
        </button>
      </div>
      <div className="inspector-body">
        {tab === "reasoning" ? (
          <>
            <p className="explanation">
              {prediction.explanation || "No explanation was returned for this transaction."}
            </p>
            {prediction.evidence.length > 0 && (
              <>
                <h4>Supporting evidence</h4>
                <ul className="evidence-list">
                  {prediction.evidence.map((evidence, index) => (
                    <li key={`${evidence.signal}-${index}`}>
                      <Check size={13} />
                      <div>
                        <span>
                          {SIGNALS[evidence.signal] ??
                            humanize(evidence.signal.replace(/^kw_/, ""))}
                        </span>
                        {evidence.fields.length > 0 && (
                          <small>
                            {evidence.fields
                              .map(
                                (field) =>
                                  row.fields.find((source) => source.field === field)?.header ??
                                  humanize(field),
                              )
                              .join(", ")}
                          </small>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {prediction.alternatives.length > 0 && (
              <div className="alternatives">
                <h4>Also considered</h4>
                {prediction.alternatives.map((alternative) => (
                  <div key={alternative.voucher_type}>
                    <span>{alternative.voucher_type}</span>
                    <span>{Math.round(alternative.probability * 100)}%</span>
                  </div>
                ))}
              </div>
            )}
            <details className="audit-details">
              <summary>Decision trace</summary>
              <dl>
                <dt>Decision sources</dt>
                <dd>
                  {prediction.decided_by.split("+").map(sourceName).join(", ") || "Not reported"}
                </dd>
                <dt>Model version</dt>
                <dd>{prediction.model_version}</dd>
                <dt>Policy</dt>
                <dd>{prediction.policy_version}</dd>
                <dt>Candidate set</dt>
                <dd>{prediction.prediction_set.join(", ") || prediction.voucher_type}</dd>
              </dl>
            </details>
          </>
        ) : (
          <dl className="source-fields">
            {row.fields.map((field, index) => (
              <div key={`${field.field}-${index}`}>
                <dt>{field.header}</dt>
                <dd>{display(field.value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      <form
        className="review-form"
        onSubmit={(event) => {
          event.preventDefault();
          onDecide(label);
        }}
      >
        {decision && (
          <div className="review-saved">
            <CheckCheck size={15} />
            <span>
              {decision.label === prediction.voucher_type ? "Reviewed" : "Correction saved"} in this
              workspace
            </span>
            <button className="icon-button" type="button" onClick={onUndo} aria-label="Undo review">
              <RotateCcw size={14} />
            </button>
          </div>
        )}
        <label htmlFor="review-voucher">Final voucher type</label>
        <select
          id="review-voucher"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
        >
          {families.map((family) => (
            <optgroup key={family.name} label={family.name}>
              {family.labels.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <button className="button primary" type="submit">
          <Check size={16} />
          {changed ? "Save correction" : "Confirm classification"}
          {hasNext && <ChevronRight size={16} />}
        </button>
        <p>
          {hasNext ? "Continues to the next entry needing review. " : ""}Included in your export;
          not sent as model feedback.
        </p>
      </form>
    </aside>
  );
}
