// Viveka workbench. Plain ES module, no build step; served by `viveka serve`.

const app = document.getElementById("app");
const rack = document.getElementById("rack");

const SIGNALS = {
  company_is_seller: "Your company is the seller",
  company_is_buyer: "Your company is the buyer",
  has_money: "Money changes hands",
  debit_leg_own_cash_bank: "The debit side is your own cash or bank account",
  credit_leg_own_cash_bank: "The credit side is your own cash or bank account",
  both_legs_own_cash_bank: "Both sides are your own cash or bank accounts",
  payment_instrument: "Settled through a payment mode such as NEFT, UPI or cheque",
  has_invoice_values: "Carries tax-invoice values",
  references_other_document: "Points back to an earlier document",
  negative_value: "Values are negative",
  order_without_movement: "An order, with nothing dispatched or received yet",
  kw_credit_note: "Narration reads like a credit note or sales return",
  kw_debit_note: "Narration reads like a debit note or purchase return",
  kw_advance: "Narration mentions an advance",
  kw_adjustment: "Narration reads like an adjustment entry",
  has_gst: "GST is charged",
  sac_service: "SAC code, so a service rather than goods",
  quantity_without_value: "Quantity moves without any value",
  has_challan: "Has challan, e-way bill or vehicle details",
  has_grn: "Has a goods receipt note number",
  kw_rejection: "Goods were rejected",
  godown_transfer: "Moves stock from one godown to another",
  stock_count: "Records a counted physical quantity",
  job_work: "Part of a job-work arrangement",
  payroll_components: "Has a pay breakdown",
  attendance_fields: "Records days present or overtime",
  employee_present: "Names an employee",
  import_documents: "Has a Bill of Entry or customs duty",
  export_documents: "Has a shipping bill, LUT or export wording",
  foreign_currency: "Billed in a foreign currency",
  kw_sez: "Mentions an SEZ or deemed export",
};

const money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const state = {
  data: null,
  file: null,          // last uploaded File, so whose-books can be re-read
  sample: false,
  selected: null,      // row_id
  view: "all",         // all | review | changed
  type: "",
  query: "",
  decisions: new Map(), // row_id -> { label }
};

// ---------- helpers ----------

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const tilt = (id) => (((id * 37) % 7) - 3) * 0.55;

function fmtDate(v) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v ?? ""));
  return m ? `${m[3]}-${m[2]}-${m[1].slice(2)}` : esc(v ?? "");
}

function fmtAmount(row) {
  if (row.amount == null) {
    return row.quantity != null ? `<span class="qty">${esc(row.quantity)} ${esc(row.unit ?? "qty")}</span>` : "";
  }
  const cur = row.currency && row.currency !== "INR" ? `<span class="cur">${esc(row.currency)}</span>` : "";
  const abs = money.format(Math.abs(row.amount));
  return cur + (row.amount < 0 ? `(${abs})` : abs);
}

function sureness(p) {
  const pct = Math.round(p * 100);
  if (p >= 0.9) return `Sure, ${pct}%`;
  if (p >= 0.7) return `Fairly sure, ${pct}%`;
  return `Unsure, ${pct}%`;
}

const pred = (id) => state.data.predictions[id];
const row = (id) => state.data.rows[id];
const allIds = () => state.data.rows.map((r) => r.row_id);

function labelOf(id) {
  return state.decisions.get(id)?.label ?? pred(id).voucher_type;
}

function status(id) {
  const d = state.decisions.get(id);
  if (d && d.label !== pred(id).voucher_type) return "changed";
  if (d) return "accepted";
  return pred(id).needs_review ? "review" : "ok";
}

function stamp(label, { p = 1, id = 0, cls = "", tag = "span", attrs = "" } = {}) {
  if (cls.includes("big") && label.length > 14) cls += " stamp--long";
  const take = cls.includes("big") ? 0.4 + 0.6 * p : 0.55 + 0.45 * p;
  return `<${tag} class="stamp ${cls}" style="--tilt:${tilt(id)}deg;--take:${take.toFixed(2)}" ${attrs}>${esc(label)}</${tag}>`;
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ---------- loading ----------

async function load(request, { file = null, sample = false } = {}) {
  renderIntake({ busy: "Reading the file and booking every row…" });
  try {
    const res = await request();
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail ?? `The server answered ${res.status}.`);
    if (!body.rows.length) {
      throw new Error("The file has no transaction rows. Check that it has a header row with data below it.");
    }
    Object.assign(state, {
      data: body, file, sample, selected: null, view: "all", type: "", query: "", decisions: new Map(),
    });
    state.selected = firstReview() ?? 0;
    renderBench();
  } catch (err) {
    renderIntake({ error: `Couldn't book this file. ${err.message}` });
  }
}

function loadFile(file, gstin = "") {
  const form = new FormData();
  form.append("file", file);
  if (gstin) form.append("company_gstin", gstin);
  return load(() => fetch("/v1/workbench", { method: "POST", body: form }), { file });
}

function loadSample(gstin = "") {
  const q = gstin ? `?company_gstin=${encodeURIComponent(gstin)}` : "";
  return load(() => fetch(`/v1/workbench/sample${q}`), { sample: true });
}

// ---------- intake ----------

function renderIntake({ busy = "", error = "" } = {}) {
  app.innerHTML = `
  <main class="intake">
    <div class="intake__body">
     <div class="intake__main">
      <h1 class="wordmark" lang="sa">विवेक<span class="wordmark__latin" lang="en">Viveka</span></h1>
      <p class="intake__lede">Drop in a day book. Every row comes back booked as one of the 27 vouchers, with the reasons written next to it.</p>

      <section class="drop" id="drop" aria-labelledby="drop-title">
        <h2 class="drop__title" id="drop-title">Drop an .xlsx, .csv or .json file here</h2>
        <p class="drop__hint">Any column names work. Every sheet in a workbook is read.</p>
        <div class="drop__actions">
          <label class="btn btn--ink" for="file-input" tabindex="0" id="choose">Choose a file</label>
          <input id="file-input" type="file" accept=".xlsx,.xlsm,.xls,.csv,.json" hidden>
          <button class="btn btn--quiet" id="sample" type="button">Try the sample day book</button>
        </div>
      </section>

      <div class="books">
        <label for="gstin">Whose books are these?</label>
        <input class="field" id="gstin" autocomplete="off" spellcheck="false" maxlength="15" placeholder="Company GSTIN">
        <p class="books__hint">Leave it blank and Viveka finds the company from the GSTIN that recurs in the file.</p>
      </div>

      ${busy ? `<p class="notice notice--busy" role="status">${esc(busy)}</p>` : ""}
      ${error ? `<p class="notice" role="alert">${esc(error)}</p>` : ""}
     </div>
      <aside class="specimen" id="specimen" aria-labelledby="specimen-title"></aside>
    </div>
  </main>`;
  renderSpecimen();

  const drop = document.getElementById("drop");
  const input = document.getElementById("file-input");
  const gstin = () => document.getElementById("gstin").value.trim().toUpperCase();

  document.getElementById("choose").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", () => input.files[0] && loadFile(input.files[0], gstin()));
  document.getElementById("sample").addEventListener("click", () => loadSample(gstin()));
  for (const ev of ["dragenter", "dragover"]) {
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("is-over"); });
  }
  for (const ev of ["dragleave", "drop"]) {
    drop.addEventListener(ev, () => drop.classList.remove("is-over"));
  }
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) loadFile(file, gstin());
  });
}

let families = null;

async function renderSpecimen() {
  try {
    families ??= await (await fetch("/v1/labels")).json();
  } catch {
    return; // The specimen is a guide, not a requirement; the intake works without it.
  }
  const el = document.getElementById("specimen");
  if (!el) return;
  el.innerHTML = `<h2 id="specimen-title">The 27 vouchers a row can be booked as</h2>${families
    .map((f, fi) => `<section class="specimen__family"><h3>${esc(f.name)}</h3><div>${f.labels
      .map((l, li) => stamp(l, { id: fi * 4 + li * 3 }))
      .join("")}</div></section>`)
    .join("")}`;
}

// ---------- workbench ----------

function visibleIds() {
  const q = state.query.toLowerCase();
  return allIds().filter((id) => {
    const s = status(id);
    if (state.view === "review" && s !== "review") return false;
    if (state.view === "changed" && s !== "changed") return false;
    if (state.type && labelOf(id) !== state.type) return false;
    if (q) {
      const r = row(id);
      const hay = `${r.number ?? ""} ${r.party ?? ""} ${r.narration ?? ""} ${r.item ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function firstReview(after = -1) {
  const ids = allIds();
  return ids.find((id) => id > after && status(id) === "review") ?? ids.find((id) => status(id) === "review");
}

function counts() {
  const ids = allIds();
  const n = (s) => ids.filter((id) => status(id) === s).length;
  return { all: ids.length, review: n("review"), changed: n("changed"), accepted: n("accepted") };
}

function renderBench() {
  const { company, source } = state.data;
  const how = { inferred: "found in the file", profile: "set by you", unknown: "" }[company.how];
  const who = company.name || company.gstin
    ? `<strong>Books of ${esc(company.name ?? company.gstin)}</strong>
       <span>${company.gstin ? `GSTIN ${esc(company.gstin)}, ${how}` : esc(how)}. Read from ${esc(source)}.</span>`
    : `<strong>Whose books? Not found in the file</strong>
       <span>Purchase and Sales can't be told apart until you set the company.</span>`;

  app.innerHTML = `
  <div class="bench">
    <header class="masthead">
      <button class="masthead__mark" id="home" lang="sa" title="Open another file" aria-label="Viveka, open another file">विवेक</button>
      <div class="masthead__books" id="books">${who}</div>
      <div class="masthead__actions">
        <button class="btn" id="set-books" type="button">Change whose books</button>
        <button class="btn" id="export-csv" type="button">Download for Excel</button>
        <button class="btn btn--ink" id="export-json" type="button">Download predictions</button>
      </div>
    </header>

    <section class="book" aria-label="Day book">
      <div class="book__tools">
        <div class="tabs" role="group" aria-label="Show rows" id="tabs"></div>
        <label class="tool">Voucher type
          <select id="type"></select>
        </label>
        <label class="tool">Find
          <input id="query" type="search" placeholder="Number, party or narration">
        </label>
      </div>
      <div class="ledger-wrap" id="wrap">
        <table class="ledger">
          <thead><tr>
            <th class="c-margin"><span class="visually-hidden">Review</span></th>
            <th class="c-date">Date</th>
            <th class="c-no">No.</th>
            <th class="c-party">Particulars</th>
            <th class="c-amt">Amount ₹</th>
            <th class="c-vch">Voucher</th>
          </tr></thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
      <footer class="book__foot" id="foot"></footer>
    </section>

    <aside class="slip-col" id="slip" aria-live="polite"></aside>
  </div>`;

  document.getElementById("home").addEventListener("click", () => { state.data = null; renderIntake(); });
  document.getElementById("set-books").addEventListener("click", editBooks);
  document.getElementById("export-json").addEventListener("click", exportJson);
  document.getElementById("export-csv").addEventListener("click", exportCsv);
  document.getElementById("query").addEventListener("input", (e) => { state.query = e.target.value; renderRows(); });
  document.getElementById("type").addEventListener("change", (e) => { state.type = e.target.value; renderRows(); });
  document.getElementById("rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (tr) select(Number(tr.dataset.id));
  });

  renderRows();
  renderSlip({ land: true });
}

function renderTabs() {
  const c = counts();
  const tabs = [["all", `All ${c.all}`], ["review", `To review ${c.review}`], ["changed", `Changed by you ${c.changed}`]];
  const box = document.getElementById("tabs");
  box.innerHTML = tabs
    .map(([v, t]) => `<button type="button" data-view="${v}" aria-pressed="${state.view === v}">${t}</button>`)
    .join("");
  box.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => { state.view = b.dataset.view; renderRows(); }));

  const present = new Map();
  for (const id of allIds()) present.set(labelOf(id), (present.get(labelOf(id)) ?? 0) + 1);
  const groups = state.data.families
    .map((f) => {
      const opts = f.labels.filter((l) => present.has(l))
        .map((l) => `<option value="${esc(l)}" ${state.type === l ? "selected" : ""}>${esc(l)} (${present.get(l)})</option>`)
        .join("");
      return opts ? `<optgroup label="${esc(f.name)}">${opts}</optgroup>` : "";
    })
    .join("");
  document.getElementById("type").innerHTML = `<option value="">Every type</option>${groups}`;
}

function rowHtml(id) {
  const r = row(id), p = pred(id), s = status(id);
  const mark = {
    review: `<span class="tick tick--review" title="Needs your review">?</span>`,
    accepted: `<span class="tick tick--ok" title="Accepted by you">✓</span>`,
    changed: `<span class="tick tick--changed" title="Changed by you">✎</span>`,
    ok: "",
  }[s];
  const sub = r.item || r.narration;
  const conf = s === "changed" || s === "accepted" ? 1 : p.confidence;
  return `<tr data-id="${id}" tabindex="${id === state.selected ? 0 : -1}" aria-selected="${id === state.selected}">
    <td class="c-margin">${mark}</td>
    <td class="c-date">${fmtDate(r.date)}</td>
    <td class="c-no">${esc(r.number ?? `Row ${id + 1}`)}</td>
    <td class="c-party">${esc(r.party ?? "")}${sub ? `<small>${esc(sub)}</small>` : ""}<span class="m-vch">${stamp(labelOf(id), { p: conf, id })}</span></td>
    <td class="c-amt">${fmtAmount(r)}</td>
    <td class="c-vch">${stamp(labelOf(id), { p: conf, id })}</td>
  </tr>`;
}

function renderRows() {
  renderTabs();
  const ids = visibleIds();
  const empty = {
    review: "Nothing left to review. Every doubtful row has been accepted or changed.",
    changed: "You haven't changed any voucher yet.",
    all: "No rows match. Clear the search or pick every type.",
  }[state.view];
  document.getElementById("rows").innerHTML = ids.length
    ? ids.map(rowHtml).join("")
    : `<tr class="empty-row"><td colspan="6">${empty}</td></tr>`;
  renderFoot();
}

function renderFoot() {
  const c = counts();
  document.getElementById("foot").innerHTML = `
    <span><b>${c.all}</b> rows booked</span>
    <span><b>${c.review}</b> to review</span>
    <span><b>${c.accepted}</b> accepted</span>
    <span><b>${c.changed}</b> changed by you</span>
    <span class="keys"><kbd>↑</kbd> <kbd>↓</kbd> move, <kbd>A</kbd> accept, <kbd>C</kbd> change</span>`;
}

function refreshRow(id) {
  const tr = document.querySelector(`tr[data-id="${id}"]`);
  if (tr) tr.outerHTML = rowHtml(id);
  renderTabs();
  renderFoot();
}

function select(id, { focus = false } = {}) {
  const prev = state.selected;
  state.selected = id;
  for (const pid of new Set([prev, id])) {
    const tr = document.querySelector(`tr[data-id="${pid}"]`);
    if (tr) {
      tr.setAttribute("aria-selected", String(pid === id));
      tr.tabIndex = pid === id ? 0 : -1;
    }
  }
  const tr = document.querySelector(`tr[data-id="${id}"]`);
  if (tr) {
    tr.scrollIntoView({ block: "nearest" });
    if (focus) tr.focus();
  }
  renderSlip({ land: prev !== id });
}

// ---------- the voucher slip ----------

function renderSlip({ land = false } = {}) {
  const el = document.getElementById("slip");
  const id = state.selected;
  if (id == null) { el.innerHTML = ""; return; }
  const r = row(id), p = pred(id), d = state.decisions.get(id);
  const label = labelOf(id);
  const changed = d && d.label !== p.voucher_type;
  const headers = Object.fromEntries(r.fields.map((f) => [f.field, f.header]));

  const evidence = p.evidence
    .map((e) => {
      const from = e.fields.map((f) => headers[f] ?? f).join(", ");
      return `<li>${esc(SIGNALS[e.signal] ?? e.signal)}${from ? `<small>From ${esc(from)}</small>` : ""}</li>`;
    })
    .join("");

  const alts = p.alternatives
    .filter((a) => a.voucher_type !== label)
    .map((a) => `<span>${stamp(a.voucher_type, {
      p: a.probability, id: id + 3, cls: "stamp--alt", tag: "button",
      attrs: `type="button" data-pick="${esc(a.voucher_type)}" title="Book as ${esc(a.voucher_type)}"`,
    })}<span class="alts__p">${Math.round(a.probability * 100)}%</span></span>`)
    .join("");

  let sure;
  if (changed) {
    sure = `<p class="slip__was">Changed by you. Viveka said <s>${esc(p.voucher_type)}</s>, ${sureness(p.confidence).toLowerCase()}.</p>`;
  } else if (d) {
    sure = `<p class="slip__sure"><strong>Accepted by you.</strong> Viveka was ${sureness(p.confidence).toLowerCase()}.</p>`;
  } else {
    sure = `<p class="slip__sure"><strong>${sureness(p.confidence)}</strong>${p.needs_review ? ". Check this one." : ""}</p>`;
  }

  const amt = fmtAmount(r);
  const rupee = r.amount != null && (!r.currency || r.currency === "INR") ? "₹ " : "";
  el.innerHTML = `
  <article class="slip" aria-label="Voucher for ${esc(r.number ?? `row ${id + 1}`)}">
    <div class="slip__head">
      <h2 class="slip__no">${esc(r.number ?? `Row ${id + 1}`)}</h2>
      <span class="slip__date">${fmtDate(r.date)}</span>
    </div>
    ${r.party ? `<p class="slip__party">${esc(r.party)}</p>` : ""}
    ${amt ? `<p class="slip__amt">${rupee}${amt}</p>` : ""}

    <div class="slip__stampzone">
      ${stamp(label, { p: d ? 1 : p.confidence, id, cls: `stamp--big${land ? " is-landing" : ""}` })}
      ${sure}
    </div>

    <div class="slip__actions">
      ${d ? "" : `<button class="btn btn--ink" id="accept" type="button">Accept ${esc(label)}</button>`}
      <button class="btn" id="change" type="button">Change voucher</button>
      ${d ? `<button class="btn btn--quiet" id="undo" type="button">Undo</button>` : ""}
    </div>

    <h3>Why</h3>
    ${evidence ? `<ul class="evidence">${evidence}</ul>` : `<p>${esc(p.explanation)}</p>`}
    ${alts ? `<h3>Could also be</h3><div class="alts">${alts}</div>` : ""}

    <details>
      <summary>As read from the file</summary>
      <dl class="read">${r.fields.map((f) => `<dt>${esc(f.header)}</dt><dd>${esc(f.value)}</dd>`).join("")}</dl>
    </details>
  </article>`;

  el.querySelector("#accept")?.addEventListener("click", () => decide(id, label));
  el.querySelector("#change").addEventListener("click", () => openRack(id));
  el.querySelector("#undo")?.addEventListener("click", () => {
    state.decisions.delete(id);
    refreshRow(id);
    renderSlip({ land: true });
  });
  el.querySelectorAll("[data-pick]").forEach((b) =>
    b.addEventListener("click", () => decide(id, b.dataset.pick, { stay: true })));
}

function decide(id, label, { stay = false } = {}) {
  state.decisions.set(id, { label });
  refreshRow(id);
  const next = stay ? null : firstReview(id);
  if (next != null && next !== id && document.querySelector(`tr[data-id="${next}"]`)) {
    select(next, { focus: document.activeElement?.tagName === "TR" });
  } else {
    renderSlip({ land: true });
  }
}

// ---------- stamp rack ----------

function openRack(id) {
  const current = labelOf(id);
  document.getElementById("rack-row").textContent = row(id).number ?? `row ${id + 1}`;
  document.getElementById("rack-body").innerHTML = state.data.families
    .map((f, fi) => `<section class="rack__family"><h3>${esc(f.name)}</h3><div>${f.labels
      .map((l, li) => stamp(l, {
        id: fi * 5 + li, tag: "button",
        attrs: `type="button" data-label="${esc(l)}" ${l === current ? 'aria-current="true"' : ""}`,
      }))
      .join("")}</div></section>`)
    .join("");
  rack.querySelectorAll("[data-label]").forEach((b) =>
    b.addEventListener("click", () => {
      rack.close();
      decide(id, b.dataset.label, { stay: true });
    }));
  rack.showModal();
  rack.querySelector('[aria-current="true"]')?.focus();
}

// ---------- whose books ----------

function editBooks() {
  const box = document.getElementById("books");
  box.innerHTML = `
    <form id="books-form" class="books" style="margin:0">
      <label for="books-gstin">Company GSTIN</label>
      <input class="field" id="books-gstin" maxlength="15" autocomplete="off" spellcheck="false" value="${esc(state.data.company.gstin ?? "")}">
    </form>`;
  const input = document.getElementById("books-gstin");
  input.focus();
  input.select();
  const button = document.getElementById("set-books");
  button.textContent = "Re-read the file";
  button.removeEventListener("click", editBooks);
  button.addEventListener("click", submit);
  document.getElementById("books-form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  function submit() {
    const g = input.value.trim().toUpperCase();
    if (state.sample) loadSample(g);
    else if (state.file) loadFile(state.file, g);
  }
}

// ---------- exports ----------

const stem = () => state.data.source.replace(/\.[^.]+$/, "");

function exportJson() {
  const out = allIds().map((id) => ({ invoice_number: pred(id).invoice_number, voucher_type: labelOf(id) }));
  download(`${stem()}.predictions.json`, JSON.stringify(out, null, 2), "application/json");
}

function exportCsv() {
  const cell = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const head = ["row", "invoice_number", "date", "party", "amount", "voucher_type", "viveka_said",
    "confidence", "needs_review", "changed_by_you", "explanation"];
  const lines = allIds().map((id) => {
    const r = row(id), p = pred(id);
    return [id + 1, p.invoice_number, r.date, r.party, r.amount, labelOf(id), p.voucher_type,
      p.confidence, status(id) === "review", status(id) === "changed", p.explanation].map(cell).join(",");
  });
  download(`${stem()}.vouchers.csv`, "﻿" + [head.join(","), ...lines].join("\n"), "text/csv");
}

// ---------- keyboard ----------

document.addEventListener("keydown", (e) => {
  if (!state.data || rack.open) return;
  if (e.target.closest("input, select, textarea, button, summary") && !["ArrowDown", "ArrowUp"].includes(e.key)) return;
  if (e.target.closest("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
  const ids = visibleIds();
  const at = ids.indexOf(state.selected);
  if (e.key === "ArrowDown" || e.key === "j") {
    e.preventDefault();
    if (ids.length) select(ids[Math.min(at + 1, ids.length - 1)], { focus: true });
  } else if (e.key === "ArrowUp" || e.key === "k") {
    e.preventDefault();
    if (ids.length) select(ids[Math.max(at - 1, 0)], { focus: true });
  } else if ((e.key === "a" || e.key === "A") && state.selected != null) {
    decide(state.selected, labelOf(state.selected));
  } else if ((e.key === "c" || e.key === "C") && state.selected != null) {
    openRack(state.selected);
  }
});

renderIntake();
