"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { z } from "zod";
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Building2,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Columns3,
  FileSpreadsheet,
  HelpCircle,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Upload,
  X,
} from "lucide-react";
import { request, loadLedger } from "@/lib/api";
import {
  entriesOf,
  familySchema,
  labelOf,
  modelSchema,
  statusOf,
  type Decisions,
  type Family,
  type ModelCard,
  type WorkbenchData,
} from "@/lib/contracts";
import { amount, date, display } from "@/lib/format";
import { Brand, Dialog, StatusBadge } from "./ui";
import { Welcome, FileIntake } from "./intake";
import { Inspector } from "./inspector";
import { ColumnMapping, ServiceInfo, VoucherGuide } from "./reference-views";
import { ExportDialog } from "./export-dialog";

type View = "ledger" | "review" | "mapping" | "guide" | "service";
type Modal = "import" | "export" | "company" | "help" | null;
const PAGE_SIZE = 12;
const navigation = [
  { id: "ledger", name: "Workspace", Icon: LayoutDashboard },
  { id: "review", name: "Review queue", Icon: ListChecks },
  { id: "mapping", name: "Column mapping", Icon: Columns3 },
  { id: "guide", name: "Voucher guide", Icon: BookOpen },
] as const;

export default function Workbench() {
  const [view, setView] = useState<View>("ledger");
  const [data, setData] = useState<WorkbenchData | null>(null);
  const [source, setSource] = useState<File | "sample" | null>(null);
  const [families, setFamilies] = useState<Family[]>([]);
  const [model, setModel] = useState<ModelCard | null>(null);
  const [checking, setChecking] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);
  const [decisions, setDecisions] = useState<Decisions>({});
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState<Modal>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingSource, setPendingSource] = useState<File | "sample" | null>(null);
  const [gstin, setGstin] = useState("");
  const [gstinDraft, setGstinDraft] = useState("");
  const controller = useRef<AbortController | null>(null);
  const connectionController = useRef<AbortController | null>(null);

  const checkConnection = useCallback(() => {
    connectionController.current?.abort();
    const connection = new AbortController();
    connectionController.current = connection;
    const options = { signal: connection.signal };
    return Promise.allSettled([
      request("model-card", modelSchema, options),
      request("labels", z.array(familySchema), options),
    ]).then(([modelResult, labelsResult]) => {
      if (connection.signal.aborted) return;
      setModel(modelResult.status === "fulfilled" ? modelResult.value : null);
      if (labelsResult.status === "fulfilled") setFamilies(labelsResult.value);
      setChecking(false);
    });
  }, []);

  useEffect(() => {
    void checkConnection();
    return () => {
      connectionController.current?.abort();
      controller.current?.abort();
    };
  }, [checkConnection]);
  useEffect(() => {
    if (!Object.keys(decisions).length) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [decisions]);

  const entries = useMemo(() => (data ? entriesOf(data) : []), [data]);
  const needsReview = entries.filter(
    ({ prediction }) => statusOf(prediction, decisions) === "review",
  ).length;
  const reviewed = Object.keys(decisions).length;
  const ready = entries.length - needsReview;
  const filtered = useMemo(
    () =>
      entries.filter(({ row, prediction }) => {
        const status = statusOf(prediction, decisions);
        if (view === "review" && status !== "review") return false;
        if (view !== "review" && filter === "review" && status !== "review") return false;
        if (view !== "review" && filter === "reviewed" && !decisions[row.row_id]) return false;
        if (view !== "review" && filter === "ready" && status === "review") return false;
        if (type && labelOf(prediction, decisions) !== type) return false;
        return [row.number, row.party, row.item, row.narration, labelOf(prediction, decisions)]
          .join(" ")
          .toLowerCase()
          .includes(query.trim().toLowerCase());
      }),
    [entries, decisions, view, filter, type, query],
  );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const selectedEntry = entries.find(({ row }) => row.row_id === selected) ?? null;
  const nextReview = entries.find(
    ({ row, prediction }) =>
      row.row_id !== selected && statusOf(prediction, decisions) === "review",
  );

  async function load(nextSource: File | "sample", perspective = "") {
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    setBusy(true);
    setError(null);
    setNotice(null);
    setModal(null);
    setPendingSource(null);
    try {
      const result = await loadLedger(nextSource, perspective, active.signal);
      if (active.signal.aborted) return;
      setData(result);
      setSource(nextSource);
      setGstin(perspective);
      setFamilies(result.families);
      setDecisions({});
      setQuery("");
      setType("");
      setFilter("all");
      setPage(1);
      setView("ledger");
      setSelected(
        result.predictions.find((prediction) => prediction.needs_review)?.row_id ??
          result.rows[0].row_id,
      );
      setNotice(
        `${result.rows.length} transactions classified. ${result.predictions.filter((prediction) => prediction.needs_review).length} need your review.`,
      );
      setChecking(true);
      void checkConnection();
    } catch (cause) {
      if (!active.signal.aborted)
        setError(
          cause instanceof Error ? cause.message : "The ledger could not be classified. Try again.",
        );
    } finally {
      if (controller.current === active) {
        setBusy(false);
        controller.current = null;
      }
    }
  }
  function requestLoad(nextSource: File | "sample") {
    if (reviewed) {
      setModal(null);
      setPendingSource(nextSource);
    } else void load(nextSource);
  }
  function navigate(nextView: View) {
    setView(nextView);
    setQuery("");
    setType("");
    setFilter("all");
    setPage(1);
  }
  function inspect(id: number) {
    setSelected(id);
    if (window.matchMedia("(max-width: 960px)").matches) {
      requestAnimationFrame(() => {
        const panel = document.getElementById("transaction-inspector");
        panel?.scrollIntoView({ block: "start" });
        panel?.focus({ preventScroll: true });
      });
    }
  }
  function decide(label: string) {
    if (selected == null || !selectedEntry) return;
    setDecisions((current) => ({
      ...current,
      [selected]: { label, reviewed_at: new Date().toISOString() },
    }));
    setNotice(
      `${display(selectedEntry.row.number ?? `Row ${selected + 1}`)} ${label === selectedEntry.prediction.voucher_type ? "confirmed" : `changed to ${label}`}. Included in your next export.`,
    );
    if (nextReview) setSelected(nextReview.row.row_id);
  }
  function undo() {
    if (selected == null) return;
    setDecisions((current) => {
      const copy = { ...current };
      delete copy[selected];
      return copy;
    });
    setNotice("Review undone. The original classification has been restored.");
  }

  return (
    <div className={`app-shell ${data ? "has-ledger" : ""}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="masthead">
        <div className="masthead-inner">
          <button
            className="brand-button"
            aria-label="Viveka workspace"
            onClick={() => navigate("ledger")}
          >
            <Brand />
          </button>
          <div className="masthead-tools">
            <button
              className="help-button"
              aria-label="How it works"
              onClick={() => setModal("help")}
            >
              <HelpCircle size={16} />
              <span>How it works</span>
            </button>
            <button className="connection-button" onClick={() => navigate("service")}>
              <span
                className={`connection-dot ${model ? "online" : checking ? "checking" : "offline"}`}
              />
              {checking ? "Connecting" : model ? "Service connected" : "Service unavailable"}
            </button>
          </div>
        </div>
      </header>
      <div className="navigation-bar">
        <nav aria-label="Main navigation">
          {navigation.map(({ id, name, Icon }) => (
            <button
              key={id}
              className={`nav-item ${view === id ? "active" : ""}`}
              aria-current={view === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              <Icon size={16} strokeWidth={1.5} />
              <span>{name}</span>
              {id === "review" && needsReview > 0 && (
                <span className="nav-count">{needsReview}</span>
              )}
            </button>
          ))}
        </nav>
        <span className="navigation-caption">Open-source voucher intelligence</span>
      </div>
      <div className="app-body">
        <main
          id="main-content"
          tabIndex={-1}
          className={`main-content ${!data && view === "ledger" ? "welcome-main" : ""}`}
        >
          {busy && (
            <div className="loading-banner" role="status">
              <LoaderCircle className="spin" size={21} />
              <div>
                <strong>Reading and classifying your ledger…</strong>
                <p>Larger files and local models can take a few minutes.</p>
              </div>
              <button
                className="button secondary small"
                onClick={() => {
                  controller.current?.abort();
                  setBusy(false);
                  setNotice("Classification cancelled. Your previous workspace is unchanged.");
                }}
              >
                Cancel
              </button>
            </div>
          )}
          {error && (
            <div className="error-banner" role="alert">
              <AlertCircle size={19} />
              <div>
                <strong>We couldn&apos;t complete that request.</strong>
                <p>{error}</p>
              </div>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError(null)}
              >
                <X size={17} />
              </button>
            </div>
          )}
          <div aria-busy={busy} className={busy ? "workspace-busy" : ""} inert={busy}>
            {view === "guide" ? (
              <VoucherGuide families={families} />
            ) : view === "mapping" ? (
              <ColumnMapping data={data} />
            ) : view === "service" ? (
              <ServiceInfo
                model={model}
                data={data}
                retry={() => {
                  setChecking(true);
                  void checkConnection();
                }}
                checking={checking}
              />
            ) : !data ? (
              <Welcome onLoad={requestLoad} />
            ) : (
              <>
                <div className="page-heading">
                  <div>
                    <span className="page-context">
                      {view === "review"
                        ? "A little attention goes a long way"
                        : "Your voucher workspace"}
                    </span>
                    <h1>
                      {view === "review" ? "Make the final call." : "Your ledger, understood."}
                    </h1>
                    <p>
                      {view === "review"
                        ? "Inspect the evidence and confirm the entries that need you."
                        : "Every classification, with its reasoning close at hand."}
                    </p>
                  </div>
                  <div className="page-actions">
                    <button className="button secondary" onClick={() => setModal("import")}>
                      <Plus size={16} />
                      New ledger
                    </button>
                    <button className="button primary" onClick={() => setModal("export")}>
                      <ArrowDownToLine size={16} />
                      Export results
                    </button>
                  </div>
                </div>
                <section className="company-bar" aria-label="Company perspective">
                  <span className="company-symbol">
                    <Building2 size={20} strokeWidth={1.5} />
                  </span>
                  <div className="company-text">
                    <span>Whose books are these?</span>
                    <strong>
                      {data.company.name || data.company.gstin || "Company not identified"}
                    </strong>
                    <small>
                      {data.company.gstin || "No GSTIN identified"}
                      <span className="company-method">
                        {data.company.how === "profile"
                          ? "Provided by you"
                          : data.company.name || data.company.gstin
                            ? "Inferred from ledger"
                            : "Add your GSTIN for perspective"}
                      </span>
                    </small>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => {
                      setGstinDraft(gstin || data.company.gstin || "");
                      setModal("company");
                    }}
                  >
                    Change perspective
                    <ChevronRight size={15} />
                  </button>
                </section>
                <div className="metrics" aria-label="Ledger summary">
                  <button
                    onClick={() => {
                      navigate("ledger");
                    }}
                  >
                    <span>
                      <FileSpreadsheet size={16} />
                      Transactions
                    </span>
                    <strong>{entries.length.toLocaleString("en-IN")}</strong>
                    <small>In this ledger</small>
                  </button>
                  <button className="metric-review" onClick={() => navigate("review")}>
                    <span>
                      <AlertCircle size={16} />
                      Need your review
                    </span>
                    <strong>{needsReview.toLocaleString("en-IN")}</strong>
                    <small>
                      {needsReview
                        ? "Your judgement makes the difference"
                        : "All uncertain entries reviewed"}
                    </small>
                  </button>
                  <button
                    onClick={() => {
                      navigate("ledger");
                      setFilter("ready");
                    }}
                  >
                    <span>
                      <CheckCheck size={16} />
                      Ready to export
                    </span>
                    <strong>{ready.toLocaleString("en-IN")}</strong>
                    <small>{reviewed} reviewed by you</small>
                  </button>
                </div>
                <div className="ledger-heading">
                  <div>
                    <h2>{view === "review" ? "Review queue" : "Transactions"}</h2>
                    <span className="ledger-count">
                      {view === "review" ? needsReview : entries.length}
                    </span>
                  </div>
                  <div className="source-name">
                    <FileSpreadsheet size={14} />
                    <span title={data.source}>{data.source}</span>
                    {source === "sample" && <span className="sample-tag">Sample</span>}
                  </div>
                </div>
                <div className="ledger-layout">
                  <section className="ledger-panel" aria-label="Transactions">
                    <div className="table-toolbar">
                      <label className="search-field">
                        <Search size={16} />
                        <input
                          placeholder="Search transactions…"
                          aria-label="Search transactions"
                          value={query}
                          onChange={(event) => {
                            setQuery(event.target.value);
                            setPage(1);
                          }}
                        />
                        {query && (
                          <button
                            className="icon-button"
                            aria-label="Clear search"
                            onClick={() => {
                              setQuery("");
                              setPage(1);
                            }}
                          >
                            <X size={14} />
                          </button>
                        )}
                      </label>
                      <select
                        aria-label="Filter by voucher type"
                        value={type}
                        onChange={(event) => {
                          setType(event.target.value);
                          setPage(1);
                        }}
                      >
                        <option value="">All voucher types</option>
                        {families.map((family) => (
                          <optgroup key={family.name} label={family.name}>
                            {family.labels.map((label) => (
                              <option key={label}>{label}</option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    </div>
                    {view !== "review" && (
                      <div
                        className="filter-tabs"
                        role="group"
                        aria-label="Filter by review status"
                      >
                        {[
                          { id: "all", label: "All entries" },
                          { id: "review", label: "Needs review" },
                          { id: "reviewed", label: "Reviewed" },
                          { id: "ready", label: "Ready" },
                        ].map((item) => (
                          <button
                            key={item.id}
                            className={filter === item.id ? "active" : ""}
                            aria-pressed={filter === item.id}
                            onClick={() => {
                              setFilter(item.id);
                              setPage(1);
                            }}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    )}
                    {visible.length ? (
                      <div className="table-scroll">
                        <table className="transactions-table">
                          <thead>
                            <tr>
                              <th>Transaction</th>
                              <th>Voucher type</th>
                              <th className="numeric">Amount</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {visible.map(({ row, prediction }) => (
                              <tr
                                key={row.row_id}
                                className={selected === row.row_id ? "selected-row" : ""}
                                onClick={() => inspect(row.row_id)}
                              >
                                <td>
                                  <button
                                    className="transaction-button"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      inspect(row.row_id);
                                    }}
                                    aria-label={`Inspect ${row.number ?? `row ${row.row_id + 1}`}`}
                                    aria-pressed={selected === row.row_id}
                                  >
                                    {display(row.number ?? `Row ${row.row_id + 1}`)}
                                  </button>
                                  <span
                                    className="table-party"
                                    title={display(row.party || row.item)}
                                  >
                                    {display(row.party || row.item || "No counterparty")}
                                  </span>
                                  <small>{date(row.date)}</small>
                                </td>
                                <td>
                                  <span className="voucher-label">
                                    {labelOf(prediction, decisions)}
                                  </span>
                                  <span className="table-confidence">
                                    <span className="mini-confidence">
                                      <span style={{ width: `${prediction.confidence * 100}%` }} />
                                    </span>
                                    {Math.round(prediction.confidence * 100)}% confidence
                                  </span>
                                </td>
                                <td className="numeric table-amount">{amount(row)}</td>
                                <td>
                                  <StatusBadge status={statusOf(prediction, decisions)} />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="empty-state">
                        {view === "review" && !needsReview ? (
                          <>
                            <CheckCheck size={30} />
                            <h2>You&apos;re all caught up.</h2>
                            <p>
                              Every uncertain entry has been reviewed. Your ledger is ready to
                              export.
                            </p>
                            <button className="button secondary" onClick={() => setModal("export")}>
                              <ArrowDownToLine size={16} />
                              Export results
                            </button>
                          </>
                        ) : (
                          <>
                            <Search size={27} />
                            <h2>No matching transactions</h2>
                            <p>Try another search or clear the filters.</p>
                            <button
                              className="button secondary small"
                              onClick={() => {
                                setQuery("");
                                setType("");
                                setFilter("all");
                                setPage(1);
                              }}
                            >
                              Clear filters
                            </button>
                          </>
                        )}
                      </div>
                    )}
                    <div className="pagination">
                      <span>
                        {filtered.length
                          ? `${(currentPage - 1) * PAGE_SIZE + 1}–${Math.min(currentPage * PAGE_SIZE, filtered.length)} of ${filtered.length} entries`
                          : "0 entries"}
                      </span>
                      <div>
                        <button
                          className="icon-button"
                          aria-label="Previous page"
                          disabled={currentPage === 1}
                          onClick={() => setPage(currentPage - 1)}
                        >
                          <ChevronLeft size={16} />
                        </button>
                        <span>
                          {currentPage} / {pages}
                        </span>
                        <button
                          className="icon-button"
                          aria-label="Next page"
                          disabled={currentPage === pages}
                          onClick={() => setPage(currentPage + 1)}
                        >
                          <ChevronRight size={16} />
                        </button>
                      </div>
                    </div>
                  </section>
                  <Inspector
                    entry={selectedEntry}
                    families={families}
                    decision={selected != null ? decisions[selected] : undefined}
                    onDecide={decide}
                    onUndo={undo}
                    onClose={() => setSelected(null)}
                    hasNext={Boolean(nextReview)}
                  />
                </div>
                <p className="workspace-footnote">
                  Classifications are suggestions for your review. Nothing is posted to your books
                  automatically.
                </p>
              </>
            )}
          </div>
        </main>
        <footer className="main-footer">
          <span>
            Viveka <span className="footer-plus">×</span> VYOM+
          </span>
          <span>Thoughtful decisions. Traceable books.</span>
        </footer>
      </div>
      {notice && (
        <div className="toast" role="status">
          <Check size={17} />
          <span>{notice}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setNotice(null)}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {modal === "import" && (
        <Dialog title="Import a ledger" onClose={() => setModal(null)}>
          <p className="dialog-intro">
            Each upload starts a new workspace. Export your current ledger first if you need to keep
            it.
          </p>
          <FileIntake compact onLoad={requestLoad} />
        </Dialog>
      )}
      {pendingSource && (
        <Dialog title="Replace this ledger?" onClose={() => setPendingSource(null)}>
          <p className="dialog-intro">
            You have {reviewed} reviewed {reviewed === 1 ? "entry" : "entries"} in this tab.
            Importing another ledger clears these decisions. Export them first if you need a copy.
          </p>
          <div className="dialog-actions">
            <button
              className="button secondary"
              onClick={() => {
                setPendingSource(null);
                setModal("export");
              }}
            >
              Export current ledger
            </button>
            <button className="button primary" onClick={() => void load(pendingSource)}>
              <Upload size={16} />
              Replace ledger
            </button>
          </div>
        </Dialog>
      )}
      {modal === "company" && data && (
        <Dialog title="Set the company perspective" onClose={() => setModal(null)}>
          <p className="dialog-intro">
            The same invoice can be a sale for one business and a purchase for another. Enter the
            GSTIN of the company whose books you are preparing.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (source) void load(source, gstinDraft.trim().toUpperCase());
            }}
          >
            <label className="form-label" htmlFor="company-gstin">
              Company GSTIN <span>(optional)</span>
            </label>
            <input
              className="text-input gstin-input"
              id="company-gstin"
              placeholder="e.g. 27AAACK1234M1ZL"
              value={gstinDraft}
              maxLength={15}
              pattern="[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]"
              title="Enter a 15-character GSTIN, or leave blank for automatic detection."
              onChange={(event) => setGstinDraft(event.target.value.toUpperCase())}
            />
            <p className="field-help">Leave blank to infer the company from the ledger.</p>
            {reviewed > 0 && (
              <div className="export-warning">
                <AlertCircle size={17} />
                <p>
                  Reclassifying clears {reviewed} local review decisions. Export them first if you
                  need to keep them.
                </p>
              </div>
            )}
            <div className="dialog-actions">
              <button className="button secondary" type="button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button className="button primary" type="submit">
                <RefreshCw size={15} />
                Reclassify ledger
              </button>
            </div>
          </form>
        </Dialog>
      )}
      {modal === "export" && data && (
        <ExportDialog
          source={data.source}
          entries={entries}
          filtered={filtered}
          decisions={decisions}
          onClose={() => setModal(null)}
          onExport={(count) =>
            setNotice(`${count} entries exported with your current classifications.`)
          }
        />
      )}
      {modal === "help" && (
        <Dialog title="From ledger to clear decisions" onClose={() => setModal(null)}>
          <ol className="help-steps">
            <li>
              <Upload size={20} />
              <div>
                <h3>Import your transactions</h3>
                <p>
                  Use an Excel workbook, CSV, JSON array or JSONL file. Excel sheets are read
                  together. A header row helps Viveka recognise the fields.
                </p>
              </div>
            </li>
            <li>
              <Building2 size={20} />
              <div>
                <h3>Check whose books they are</h3>
                <p>
                  Confirm the company identified from the ledger. Change its GSTIN to reclassify
                  from another company&apos;s perspective.
                </p>
              </div>
            </li>
            <li>
              <ListChecks size={20} />
              <div>
                <h3>Review with the evidence</h3>
                <p>
                  Open an entry to see its reasoning and source fields. Confirm the suggested
                  voucher or choose a different type.
                </p>
              </div>
            </li>
            <li>
              <ArrowDownToLine size={20} />
              <div>
                <h3>Export before you leave</h3>
                <p>
                  Download a CSV, classification JSON or full audit trail. Reviews live in this tab;
                  they are not saved to the backend.
                </p>
              </div>
            </li>
          </ol>
          <button className="button primary full-width" onClick={() => setModal(null)}>
            Back to workspace
            <ArrowRight size={16} />
          </button>
        </Dialog>
      )}
    </div>
  );
}
