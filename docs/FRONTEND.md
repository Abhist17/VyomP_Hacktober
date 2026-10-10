# Viveka web app

A standalone React / Next.js application in `apps/web`, connected to the existing FastAPI
classification service. The original lightweight Python-served workbench is still available
on the API's root URL; the new application runs on its own Node server.

## Run locally

Use Python 3.12+ and Node 22.12+ (22.x), 24.x or 26+. The frontend's test tooling requires
those Node versions. Node 24 was used for verification.

From the repository root, activate your Python environment and install the API extra:

```bash
python -m pip install -e ".[api]"
viveka serve --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd apps/web
npm ci
npm run dev
```

Open the URL printed by Next.js (normally http://127.0.0.1:3000). If that port is occupied,
Next.js selects another port. To choose one explicitly, use `npm run dev -- --port 3001`.

The sample ledger exercises the real classification pipeline. No fixture responses or
client-side voucher classifier are used by the app. Available model sources are selected
by the existing backend policy. For a quick rules-only preview or deterministic tests,
start the API with `VIVEKA_SLM=off viveka serve` instead.

For a production build:

```bash
cd apps/web
npm run build
npm run start
```

Both commands bind to loopback by default. Authentication and tenant isolation are not
implemented in this backend; place any externally hosted instance behind your application's
access controls before processing private ledgers.

## Configuration

Copy `apps/web/.env.example` to `apps/web/.env.local` to change these settings, then restart
Next.js. The default configuration works without creating this file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VIVEKA_API_URL` | `http://127.0.0.1:8000` | Server-only backend address; not exposed to browser code |
| `VIVEKA_API_TIMEOUT_MS` | `300000` | Classification timeout, capped at one hour |

The browser calls `/api/viveka/*` on its own origin. An allowlisted Next.js route forwards
the multipart upload or JSON response to FastAPI. No CORS changes are needed. Responses
are not cached. Uploads are limited to 20 MB, with both declared and streamed body sizes
checked by the proxy. Model requests can be cancelled from the UI; disconnecting does not
guarantee that computation already started by FastAPI will stop.

## Implemented workflows

- Upload `.xlsx`, `.xls`, `.xlsm`, `.csv`, `.json` or `.jsonl`, or open the backend's sample.
- Infer the company, inspect its GSTIN and reclassify from another company's perspective.
- Search transactions; filter by voucher type and review status; paginate the ledger.
- Inspect explanations, supporting evidence, alternatives, source fields and decision traces.
- Confirm or correct a voucher, advance to another uncertain entry, and undo a review.
- Inspect column mapping, the 27 voucher families and current backend configuration.
- Export CSV, the minimal classification JSON contract, the full JSON audit trail, or TallyPrime
  XML voucher headers. Labels without a Tally equivalent import as their nearest base type
  (Import as Purchase, Export as Sales, Expense as Journal); the Viveka label, confidence and
  review status travel in the narration. Ledger allocations are completed in TallyPrime.
- See the voucher mix of the loaded ledger and click a type to filter by it.
- In the review queue, confirm every suggestion at 90% confidence or more in one step, or
  review from the keyboard: J and K move through the list, A accepts the suggestion.
- See the held-out evaluation the backend publishes (`docs/evaluation.json`) on the service page.
- Handle unsupported / empty files, unavailable services, malformed responses and timeouts.
- Preserve the existing workspace when another import fails or is cancelled.

The UI uses `row_id` to join predictions and source rows. Runtime schemas reject duplicate,
missing or mismatched IDs before the app displays potentially incorrect evidence.

### Review and export semantics

The backend's `POST /v1/feedback` currently returns 501. Review decisions therefore live in
React state in the current tab. They are not saved to the server, browser storage or model
memory. Export before refreshing or closing the tab. Replacing a ledger or changing company
perspective clears the current reviews; the app explains this before proceeding. A browser
leave-page prompt protects local reviews where the browser supports it.

Reviewing a prediction does **not** overwrite its original confidence or explanation. The
audit export preserves the complete original prediction, chosen label, review timestamp
and final status. CSV includes original and final voucher types and neutralises formulas in
user-provided text. Minimal JSON contains only `invoice_number` and `voucher_type`, including
manual corrections. Its export dialog warns that it cannot carry review status.

"Ready" means the backend did not request review, or a person reviewed the entry. It does
not mean a voucher has been posted to an accounting system. Nothing is posted automatically.

The service panel separates the **configured** SLM from the sources **actually used** in
the loaded ledger. It does not imply the language model is available merely because a model
name exists in the policy. Evaluation data is shown only if supplied by the backend.

## Visual system

Reference: [VYOM+](https://www.vyomplus.in/), inspected in Playwright on 10 October 2026,
including the coin sequence, editorial sections and final form. This is a new app layout,
with a horizontal brand masthead, wide workspace and a two-column import screen.

| Token | Value | Use |
| --- | --- | --- |
| Ink | `#080808` | Main canvas |
| Surface | `#12110f` | Ledger and evidence panels |
| Gold | `#edb52d` | Primary actions, current selection and brand detail |
| Ivory | `#f3efe2` | Main text and serif headings |
| Muted | `#aaa396` | Supporting copy |
| Border | `#332e24` | Quiet structure |

Georgia carries the large editorial headings; locally bundled Manrope handles UI and data.
The blue brand mark echoes the VYOM+ identity, while gold connects the product to the source
site's coin imagery. The app needs no external font requests or animation assets.

The ledger and evidence panel sit side by side on wide screens, then stack on tablets and
phones. A horizontally scrollable table preserves all fields on small screens without
overflowing the page. Selecting a row on a narrow screen moves focus to its inspector.
Dialogs use the native modal element for focus containment, Escape and focus restoration.
Visible focus, descriptive icon labels and reduced-motion preferences are supported. Motion
is limited to brief press feedback and the indeterminate loading indicator.

## Verification

```bash
cd apps/web
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

The end-to-end suite starts FastAPI on port 8100 and Next.js on port 3100. It uses the repo's
`.venv` when present and otherwise `python3`. Install the backend API dependencies first.
Install a Playwright browser once with `npx playwright install chromium`, or use an installed
Google Chrome with `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e`.

To check already-running local services:

```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 \
VIVEKA_TEST_API_URL=http://127.0.0.1:8000 \
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

Verified in this workspace:

- Production build, TypeScript and ESLint passed.
- 8 unit tests passed: response integrity, row joins, review semantics, exports and file validation.
- 8 Playwright tests passed against FastAPI: keyboard upload, pagination, evidence, corrections,
  actual downloaded audit JSON, CSV upload, perspective changes, error recovery, mapping,
  voucher guide, mobile focus and proxy limits.
- Axe WCAG A/AA checks passed on the desktop import screen and mobile ledger.
- All 22 existing Python tests passed with `VIVEKA_SLM=off`.
- Production dependencies have no reported advisories in `npm audit --omit=dev`.

The browser tests deliberately use the rules-only path for repeatability; these checks do
not benchmark or certify SLM accuracy. The failure-recovery test simulates a service outage;
the sample, upload, perspective and export tests use actual FastAPI responses.

`npm audit` currently reports a development-tooling advisory in `braces`, pulled in through
the latest Next.js ESLint configuration. Its suggested automatic fix downgrades the Next
lint configuration across major versions; that incompatible downgrade was not applied.
