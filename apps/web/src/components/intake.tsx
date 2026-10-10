"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUpRight, FileSpreadsheet, Upload, LockKeyhole } from "lucide-react";
import { ACCEPTED_FILES, validateFile } from "@/lib/api";
import { selectedResult, type Evaluation } from "@/lib/evaluation";
import { Coin } from "./coin";
import { CountUp, Reveal, prefersReducedMotion } from "./motion";

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

const CHAPTERS = [
  { id: "chapter-intro", label: "Introducing" },
  { id: "chapter-problem", label: "The problem" },
  { id: "chapter-method", label: "The method" },
  { id: "chapter-proof", label: "The proof" },
  { id: "chapter-start", label: "Begin" },
] as const;

// Where the coin sits in each chapter: offset from centre (fraction of stage width / height),
// scale and tilt. Scroll position interpolates between neighbouring chapters.
const COIN_PATH = [
  { x: 0.2, y: 0.02, s: 1, tilt: 14 },
  { x: -0.2, y: 0, s: 0.92, tilt: 8 },
  { x: 0.22, y: 0.02, s: 0.86, tilt: 18 },
  { x: -0.2, y: -0.02, s: 1.02, tilt: 6 },
  { x: -0.06, y: 0.06, s: 0.72, tilt: 22 },
];
// Half a turn per chapter: each chapter rests on a face (front, back, front...), never edge-on.
const TURN_PER_CHAPTER = 180;

const smooth = (t: number) => t * t * (3 - 2 * t);

export function Welcome({
  onLoad,
  evaluation,
}: {
  onLoad: (source: File | "sample") => void;
  evaluation: Evaluation | null;
}) {
  const story = useRef<HTMLDivElement>(null);
  const [chapter, setChapter] = useState(0);
  const best = selectedResult(evaluation);

  useEffect(() => {
    const node = story.current;
    if (!node) return;
    const reduced = prefersReducedMotion();
    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = node.getBoundingClientRect();
      const travel = Math.max(1, rect.height - window.innerHeight);
      const progress = Math.min(1, Math.max(0, -rect.top / travel));
      const position = progress * (COIN_PATH.length - 1);
      const index = Math.min(COIN_PATH.length - 2, Math.floor(position));
      const t = smooth(position - index);
      const from = COIN_PATH[index];
      const to = COIN_PATH[index + 1];
      const mix = (a: number, b: number) => a + (b - a) * t;
      const narrow = window.innerWidth < 960;
      const stage = node.querySelector<HTMLElement>(".story-stage");
      if (stage) {
        const x = narrow ? 0 : mix(from.x, to.x) * stage.clientWidth;
        stage.style.setProperty("--coin-x", `${x}px`);
        stage.style.setProperty("--coin-y", `${mix(from.y, to.y) * stage.clientHeight}px`);
        stage.style.setProperty("--coin-s", String(mix(from.s, to.s)));
        stage.style.setProperty("--coin-tilt", `${mix(from.tilt, to.tilt)}deg`);
        const turn = reduced ? 0 : position * TURN_PER_CHAPTER;
        stage.style.setProperty("--coin-turn", `${turn}deg`);
        stage.style.setProperty("--coin-sheen", `${((turn % 360) / 360) * 100}%`);
      }
      setChapter(Math.round(position));
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      cancelAnimationFrame(frame);
    };
  }, []);

  const go = (id: string) =>
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });

  return (
    <div className="story" ref={story}>
      <div className="story-stage" aria-hidden="true">
        <div className="coin-mover">
          <Coin />
        </div>
      </div>
      <nav className="story-rail" aria-label="Story chapters">
        {CHAPTERS.map(({ id, label }, index) => (
          <button
            key={id}
            className={chapter === index ? "active" : ""}
            aria-current={chapter === index ? "step" : undefined}
            onClick={() => go(id)}
          >
            <span className="rail-index">{String(index + 1).padStart(2, "0")}</span>
            <span className="rail-label">{label}</span>
          </button>
        ))}
      </nav>

      <section
        className="chapter chapter-left chapter-intro"
        id="chapter-intro"
        aria-labelledby="intro-title"
      >
        <div className="chapter-copy">
          <Reveal>
            <span className="eyebrow">Introducing Viveka</span>
          </Reveal>
          <Reveal delay={90}>
            <h1 id="intro-title">
              Every entry.
              <br />
              In its right place.
            </h1>
          </Reveal>
          <Reveal delay={180}>
            <p className="chapter-lede">
              Your books tell a story. Viveka reads every transaction, books it as the right
              voucher, and shows you why.
            </p>
          </Reveal>
          <Reveal delay={270} className="chapter-actions">
            <button className="button primary shine" onClick={() => go("chapter-start")}>
              Classify a ledger
              <ArrowDown size={16} />
            </button>
            <button className="button ghost" onClick={() => onLoad("sample")}>
              Try the sample
              <ArrowUpRight size={16} />
            </button>
          </Reveal>
          <Reveal delay={360} className="hero-signature">
            <span className="signature-mark" aria-hidden="true">
              व
            </span>
            <div>
              <strong>विवेक / Viveka</strong>
              <span>The art of discernment. Built into your books.</span>
            </div>
          </Reveal>
        </div>
        <button className="scroll-cue" onClick={() => go("chapter-problem")}>
          <span className="scroll-cue-line" aria-hidden="true" />
          Scroll to explore
        </button>
      </section>

      <section
        className="chapter chapter-right"
        id="chapter-problem"
        aria-labelledby="problem-title"
      >
        <div className="chapter-copy">
          <Reveal>
            <span className="eyebrow">The problem</span>
          </Reveal>
          <Reveal delay={90}>
            <p className="chapter-figure">
              <CountUp value={27} duration={900} />.
            </p>
          </Reveal>
          <Reveal delay={180}>
            <h2 id="problem-title">Voucher types. One invoice can be any of them.</h2>
          </Reveal>
          <Reveal delay={270}>
            <p className="chapter-lede">
              A credit note is a Sales Return in the seller&apos;s books and a Purchase Return in
              the buyer&apos;s. A bank transfer is a Contra only when both accounts are yours.
              Keywords cannot tell them apart. Structure can.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="chapter chapter-left" id="chapter-method" aria-labelledby="method-title">
        <div className="chapter-copy">
          <Reveal>
            <span className="eyebrow">The method</span>
          </Reveal>
          <Reveal delay={90}>
            <h2 id="method-title">Three opinions. One decision you can inspect.</h2>
          </Reveal>
          <ol className="opinion-list">
            {[
              ["Rules", "Accounting logic: whose books, which money legs are yours, what moved."],
              ["Sentinel", "A fast classifier that has read thousands of ledger rows."],
              [
                "Fine-tuned Qwen3-1.7B",
                "An open-weight language model that scores all 27 voucher types.",
              ],
            ].map(([name, text], index) => (
              <Reveal as="li" key={name} delay={180 + index * 90}>
                <span className="opinion-index">{String(index + 1).padStart(2, "0")}</span>
                <span>
                  <strong>{name}</strong>
                  <small>{text}</small>
                </span>
              </Reveal>
            ))}
          </ol>
          <Reveal delay={470}>
            <p className="chapter-lede">
              Hard accounting guardrails check the result. Anything uncertain comes to you, with the
              evidence.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="chapter chapter-right" id="chapter-proof" aria-labelledby="proof-title">
        <div className="chapter-copy">
          <Reveal>
            <span className="eyebrow">The proof</span>
          </Reveal>
          {best && evaluation ? (
            <>
              <Reveal delay={90}>
                <p className="chapter-figure">
                  <CountUp value={best.accuracy * 100} format={(n) => `${n.toFixed(1)}%`} />
                </p>
              </Reveal>
              <Reveal delay={180}>
                <h2 id="proof-title">Accurate on companies it has never seen.</h2>
              </Reveal>
              <Reveal delay={270} className="proof-stats">
                {best.auto_accept_coverage != null && (
                  <div>
                    <strong>
                      <CountUp
                        value={best.auto_accept_coverage * 100}
                        format={(n) => `${n.toFixed(1)}%`}
                      />
                    </strong>
                    <span>booked with no review</span>
                  </div>
                )}
                {best.auto_accept_precision != null && (
                  <div>
                    <strong>
                      <CountUp
                        value={best.auto_accept_precision * 100}
                        format={(n) => `${n.toFixed(1)}%`}
                      />
                    </strong>
                    <span>of those booked correctly</span>
                  </div>
                )}
                <div>
                  <strong>
                    <CountUp value={evaluation.rows} />
                  </strong>
                  <span>held-out transactions</span>
                </div>
              </Reveal>
              <Reveal delay={360}>
                <p className="chapter-note">
                  Published by your Viveka service from its held-out test split.
                </p>
              </Reveal>
            </>
          ) : (
            <>
              <Reveal delay={90}>
                <h2 id="proof-title">Every decision comes with its evidence.</h2>
              </Reveal>
              <Reveal delay={180}>
                <p className="chapter-lede">
                  Open any entry to see the signals behind it, the alternatives it considered and
                  the models that took part.
                </p>
              </Reveal>
            </>
          )}
        </div>
      </section>

      <section className="chapter chapter-start" id="chapter-start" aria-labelledby="start-title">
        <div className="chapter-copy">
          <Reveal>
            <span className="eyebrow">Begin</span>
          </Reveal>
          <Reveal delay={90}>
            <h2 id="start-title">
              Drop your ledger.
              <br />
              Keep your evening.
            </h2>
          </Reveal>
          <Reveal delay={180}>
            <p className="chapter-lede">
              Excel, CSV or JSON, in whatever columns your software exports. Review what needs you,
              then take your vouchers to TallyPrime.
            </p>
          </Reveal>
        </div>
        <Reveal delay={150} className="hero-intake">
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
        </Reveal>
      </section>
    </div>
  );
}
