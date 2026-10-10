"use client";

import { useRef, useState } from "react";
import {
  ArrowUpRight,
  FileSpreadsheet,
  Upload,
  ScanLine,
  ListChecks,
  Download,
  LockKeyhole,
} from "lucide-react";
import { ACCEPTED_FILES, validateFile } from "@/lib/api";

export function FileIntake({
  onLoad,
  compact = false,
}: {
  onLoad: (source: File | "sample") => void;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function choose(file?: File) {
    if (!file) return;
    const issue = validateFile(file);
    setError(issue);
    if (!issue) onLoad(file);
  }
  return (
    <div className={compact ? "intake compact" : "intake"}>
      <div
        className={`dropzone ${dragging ? "is-dragging" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (event.dataTransfer.files.length > 1) setError("Upload one ledger at a time.");
          else choose(event.dataTransfer.files[0]);
        }}
      >
        <div className="file-emblem" aria-hidden="true">
          <FileSpreadsheet size={30} strokeWidth={1.25} />
          <span>
            <Upload size={13} />
          </span>
        </div>
        <h2>Start with your ledger.</h2>
        <p>Drop your transaction file here, or choose it from your computer.</p>
        <button className="button primary" onClick={() => input.current?.click()}>
          <Upload size={16} />
          Choose a ledger
        </button>
        <input
          ref={input}
          className="sr-only"
          type="file"
          accept={ACCEPTED_FILES}
          tabIndex={-1}
          aria-label="Ledger file"
          onChange={(event) => {
            choose(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        <span className="file-types">
          Excel, CSV, JSON or JSONL <span aria-hidden="true">·</span> Up to 20 MB
        </span>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <button className="sample-option" onClick={() => onLoad("sample")}>
        <span className="sample-icon">
          <FileSpreadsheet size={19} />
        </span>
        <span>
          <strong>Take a look with a sample ledger</strong>
          <small>18 transactions. Real classifications. No setup.</small>
        </span>
        <ArrowUpRight size={20} />
      </button>
    </div>
  );
}

export function Welcome({ onLoad }: { onLoad: (source: File | "sample") => void }) {
  return (
    <>
      <section className="welcome-hero" aria-label="Import your ledger">
        <div className="welcome-heading">
          <div className="product-tag">
            <span className="tiny-diamond" />
            Introducing Viveka
          </div>
          <h1>
            Every entry.
            <br />
            In its right place.
          </h1>
          <p>
            Your books tell a story. Make every transaction count. <br className="desktop-break" />
            Classify your ledger, understand the reasoning, and put the final decision in your
            hands.
          </p>
          <div className="hero-signature">
            <span className="signature-mark" aria-hidden="true">
              व
            </span>
            <div>
              <strong>विवेक / Viveka</strong>
              <span>The art of discernment. Built into your books.</span>
            </div>
          </div>
        </div>
        <div className="hero-intake">
          <div className="intake-heading">
            <span>Your next clear decision starts here</span>
            <span className="tiny-diamond" />
          </div>
          <FileIntake onLoad={onLoad} />
          <div className="privacy-note">
            <LockKeyhole size={13} />
            <p>
              Processed by your Viveka service. Files and reviews stay in this tab until you leave.
            </p>
          </div>
        </div>
      </section>
      <section className="workflow-guide">
        <div className="workflow-heading">
          <div className="guide-title">
            <span className="small-rule" />
            From transactions to understanding
          </div>
          <h2>Intelligence with a paper trail.</h2>
          <p>27 voucher types. Every decision open to inspection.</p>
        </div>
        <ol>
          <li>
            <div className="step-icon">
              <ScanLine size={22} />
              <span>01</span>
            </div>
            <div>
              <h3>A ledger, understood.</h3>
              <p>
                Bring your Excel, CSV or JSON. Viveka maps the columns and classifies each
                transaction in your company&apos;s books.
              </p>
            </div>
          </li>
          <li>
            <div className="step-icon">
              <ListChecks size={22} />
              <span>02</span>
            </div>
            <div>
              <h3>The evidence, visible.</h3>
              <p>
                See why an entry is a Purchase, a Contra or something else. Review uncertain
                decisions and make the final call.
              </p>
            </div>
          </li>
          <li>
            <div className="step-icon">
              <Download size={22} />
              <span>03</span>
            </div>
            <div>
              <h3>Your work, ready to go.</h3>
              <p>
                Export your classifications with their decision trail. Your corrections travel with
                them, exactly as you reviewed them.
              </p>
            </div>
          </li>
        </ol>
      </section>
    </>
  );
}
