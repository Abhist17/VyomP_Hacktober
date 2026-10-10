"use client";

import { useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  Columns3,
  Search,
  Server,
  SlidersHorizontal,
} from "lucide-react";
import type { Family, ModelCard, WorkbenchData } from "@/lib/contracts";
import { display, humanize } from "@/lib/format";

const descriptions: Record<string, string> = {
  "Money movements": "Transfers, settlements and adjustments between accounts.",
  "Supply invoices": "Goods and services bought or sold, including cross-border supplies.",
  "Value corrections": "Adjustments to the value of an earlier purchase or sale.",
  Orders: "Commitments to supply or process goods before movement occurs.",
  "Inventory movements": "Receipts, dispatches, returns and internal stock changes.",
  People: "Salary, payroll and attendance records.",
  "Timing and fallback": "Payments ahead of supply and records requiring another classification.",
};

export function VoucherGuide({ families }: { families: Family[] }) {
  const [query, setQuery] = useState("");
  const groups = families
    .map((family) => ({
      ...family,
      labels: family.labels.filter((label) =>
        `${family.name} ${label}`.toLowerCase().includes(query.toLowerCase()),
      ),
    }))
    .filter((family) => family.labels.length);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="page-context">Reference</span>
          <h1>A place for every transaction.</h1>
          <p>The voucher families supported by your classification service.</p>
        </div>
        <BookOpen className="heading-icon" size={38} strokeWidth={1} />
      </div>
      <label className="search-field guide-search">
        <Search size={17} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find a voucher type…"
          aria-label="Find a voucher type"
        />
      </label>
      <div className="voucher-families">
        {groups.map((family) => (
          <section key={family.name}>
            <div className="family-heading">
              <h2>{family.name}</h2>
              <span>{family.labels.length}</span>
            </div>
            <p>{descriptions[family.name]}</p>
            <ul>
              {family.labels.map((label) => (
                <li key={label}>
                  <span className="tiny-diamond" />
                  {label}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {!groups.length && (
        <div className="empty-state">
          <BookOpen size={28} />
          <h2>
            {families.length ? "No matching voucher types" : "The voucher guide is unavailable"}
          </h2>
          <p>
            {families.length
              ? "Try a different search."
              : "Connect to the backend to load the current voucher families."}
          </p>
        </div>
      )}
    </>
  );
}

export function ColumnMapping({ data }: { data: WorkbenchData | null }) {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="page-context">Your source, understood</span>
          <h1>Column mapping</h1>
          <p>See how your ledger&apos;s headers are interpreted by Viveka.</p>
        </div>
        <Columns3 className="heading-icon" size={38} strokeWidth={1} />
      </div>
      {data ? (
        <>
          <div className="mapping-summary">
            <span>
              <Check size={16} />
              {data.mappings.filter((mapping) => mapping.field).length} of {data.mappings.length}{" "}
              columns mapped
            </span>
            <p>Unmapped columns are preserved as additional evidence. Mapping is read-only.</p>
          </div>
          <div className="table-container">
            <table className="mapping-table">
              <thead>
                <tr>
                  <th>Column in your file</th>
                  <th aria-label="Maps to" />
                  <th>Recognised field</th>
                  <th>Matched by</th>
                </tr>
              </thead>
              <tbody>
                {data.mappings.map((mapping, index) => (
                  <tr key={`${mapping.header}-${index}`}>
                    <td>{mapping.header}</td>
                    <td>
                      <ArrowRight size={14} />
                    </td>
                    <td>
                      {mapping.field ? (
                        humanize(mapping.field)
                      ) : (
                        <span className="text-muted">Preserved as extra</span>
                      )}
                    </td>
                    <td>
                      <span className={`mapping-kind ${mapping.field ? "" : "unmapped"}`}>
                        {humanize(mapping.stage)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <Columns3 size={30} />
          <h2>Start with a ledger</h2>
          <p>Import a file from the workspace to see its column mapping.</p>
        </div>
      )}
    </>
  );
}

export function ServiceInfo({
  model,
  data,
  retry,
  checking,
}: {
  model: ModelCard | null;
  data: WorkbenchData | null;
  retry: () => void;
  checking: boolean;
}) {
  const sources = data
    ? [
        ...new Set(data.predictions.flatMap((prediction) => prediction.decided_by.split("+"))),
      ].filter(Boolean)
    : [];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="page-context">Workspace information</span>
          <h1>Classification service</h1>
          <p>The configuration behind your ledger&apos;s decisions.</p>
        </div>
        <Server className="heading-icon" size={38} strokeWidth={1} />
      </div>
      <section className="service-panel">
        <div className="service-panel-heading">
          <span className={`status ${model ? "status-ready" : "status-review"}`}>
            <span className="status-dot" />
            {checking ? "Checking connection" : model ? "Backend connected" : "Backend unavailable"}
          </span>
          <button className="button secondary small" disabled={checking} onClick={retry}>
            Check connection
          </button>
        </div>
        {model ? (
          <dl className="service-facts">
            <div>
              <dt>Viveka version</dt>
              <dd>{model.viveka_version}</dd>
            </div>
            <div>
              <dt>Policy version</dt>
              <dd>{model.policy_version}</dd>
            </div>
            <div>
              <dt>Configured language model</dt>
              <dd>{display(model.slm.model)}</dd>
            </div>
            <div>
              <dt>Sources used in this ledger</dt>
              <dd>
                {sources.length
                  ? sources.map(humanize).join(", ")
                  : "Import a ledger to see the sources used."}
              </dd>
            </div>
            <div>
              <dt>Published evaluation</dt>
              <dd>
                {model.evaluation == null
                  ? "No evaluation has been published by this backend."
                  : display(model.evaluation)}
              </dd>
            </div>
          </dl>
        ) : (
          <p>
            Start the Viveka service, then check the connection again. The service address is set by
            your workspace administrator.
          </p>
        )}
      </section>
      <div className="service-note">
        <SlidersHorizontal size={20} />
        <div>
          <h2>Configuration is different from availability.</h2>
          <p>
            A configured language model may not be loaded. Each transaction&apos;s decision trace
            shows the sources that actually contributed.
          </p>
        </div>
      </div>
      <div className="service-note">
        <BookOpen size={20} />
        <div>
          <h2>Your review stays yours.</h2>
          <p>
            Corrections are kept in this tab and included in exports. They are not stored on the
            server or used to train the model. Export before refreshing or closing this workspace.
          </p>
        </div>
      </div>
    </>
  );
}
