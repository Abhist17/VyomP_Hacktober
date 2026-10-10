import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

async function sample(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /Take a look with a sample ledger/ }).click();
  await expect(page.getByRole("heading", { name: "Your ledger, understood." })).toBeVisible();
  await expect(page.getByText("Kaveri Fabricators Pvt Ltd", { exact: true })).toBeVisible();
}

test("brand landing is accessible and has a working keyboard upload action", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Every entry/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Service connected" })).toBeVisible();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose a ledger" }).focus();
  await page.keyboard.press("Enter");
  await (await chooser).setFiles([]);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
});

test("real sample supports pagination, search, exact labels and evidence", async ({ page }) => {
  await sample(page);
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(12);
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(6);
  await page.getByRole("textbox", { name: "Search transactions" }).fill("CTR/12");
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(1);
  await expect(page.locator(".transactions-table")).toContainText("Contra");
  await page.getByRole("button", { name: "Inspect CTR/12", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Contra", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Source fields/ }).click();
  await expect(page.locator(".source-fields")).toContainText(
    "Fund transfer for salary disbursement",
  );
  await page.getByRole("button", { name: "Clear search" }).click();
  await page.getByLabel("Filter by voucher type").selectOption("Purchase");
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(1);
});

test("corrections update review counts and export without rewriting original confidence", async ({
  page,
}) => {
  await sample(page);
  await page.getByRole("button", { name: /Review queue/ }).click();
  // Rules-only mode (SLM off, no local sentinel) under the tuned 0.96 auto-accept cut-off.
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(9);
  await page.getByRole("button", { name: "Inspect CN/2026/018", exact: true }).click();
  await page.getByLabel("Final voucher type").selectOption("Purchase Return / Debit Note");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(8);
  await page.getByRole("button", { name: "Export results", exact: true }).click();
  await page.getByRole("radio", { name: /Full decision trail/ }).check();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export 18 entries", exact: true }).click();
  const file = await downloadPromise;
  const audit = JSON.parse(await readFile((await file.path())!, "utf8"));
  const corrected = audit.find(
    (item: { prediction: { invoice_number: string } }) =>
      item.prediction.invoice_number === "CN/2026/018",
  );
  expect(corrected.voucher_type).toBe("Purchase Return / Debit Note");
  expect(corrected.prediction.voucher_type).toBe("Sales Return / Credit Note");
  expect(corrected.prediction.confidence).toBeLessThan(0.9);
  expect(corrected.status).toBe("corrected");
  await page.getByRole("button", { name: "Workspace", exact: true }).click();
  await page.getByRole("button", { name: "Reviewed", exact: true }).click();
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Inspect CN/2026/018", exact: true }).click();
  await page.getByRole("button", { name: "Undo review" }).click();
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(0);
});

test("real CSV upload and company perspective reach FastAPI", async ({ page }) => {
  await page.goto("/");
  const upload = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/viveka/workbench") && response.request().method() === "POST",
  );
  await page
    .getByLabel("Ledger file", { exact: true })
    .setInputFiles(resolve(import.meta.dirname, "../../../examples/sample_transactions.csv"));
  expect((await upload).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Your ledger, understood." })).toBeVisible();
  await page.getByRole("button", { name: "Change perspective" }).click();
  await page.getByLabel("Company GSTIN").fill("24AABCN5678P1ZT");
  await page.getByRole("button", { name: "Reclassify ledger" }).click();
  await expect(page.getByText("Provided by you", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Search transactions" }).fill("KF/S/101");
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(1);
  await expect(page.locator(".voucher-label")).toHaveText("Purchase");
});

test("invalid files and upstream failures are actionable and preserve the loaded ledger", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Ledger file", { exact: true }).setInputFiles({
    name: "invoice.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("test"),
  });
  await expect(page.locator(".inline-error")).toContainText("Choose an Excel");
  await page.getByRole("button", { name: /Take a look with a sample ledger/ }).click();
  await expect(page.getByRole("heading", { name: "Your ledger, understood." })).toBeVisible();
  await page.route("**/api/viveka/workbench", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail:
          "The classification service is unavailable. Start the Viveka backend and try again.",
      }),
    }),
  );
  await page.getByRole("button", { name: "New ledger" }).click();
  await page.getByLabel("Ledger file", { exact: true }).setInputFiles({
    name: "retry.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Narration\nTest"),
  });
  await expect(page.locator(".error-banner")).toContainText("Start the Viveka backend");
  await expect(page.getByText("Kaveri Fabricators Pvt Ltd", { exact: true })).toBeVisible();
  await expect(page.locator(".transactions-table tbody tr")).toHaveCount(12);
});

test("mapping, service details and all voucher families come from the backend", async ({
  page,
}) => {
  await sample(page);
  await page.getByRole("button", { name: "Column mapping", exact: true }).click();
  await expect(page.locator(".mapping-table")).toContainText("Invoice No");
  await expect(page.locator(".mapping-table")).toContainText("Invoice number");
  await page.getByRole("button", { name: "Voucher guide", exact: true }).click();
  await expect(page.locator(".voucher-families li")).toHaveCount(27);
  await page.getByRole("textbox", { name: "Find a voucher type" }).fill("payroll");
  await expect(page.locator(".voucher-families li")).toHaveCount(1);
  await page.getByRole("button", { name: "Service connected" }).click();
  await expect(page.locator(".service-facts")).toContainText("Rules");
});

test("mobile layout, keyboard dialog dismissal and review remain accessible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "How it works" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: /Take a look with a sample ledger/ }).click();
  await expect(page.getByRole("heading", { name: "Your ledger, understood." })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Inspect CTR/12", exact: true }).click();
  await expect(page.locator("#transaction-inspector")).toBeFocused();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
});

test("proxy rejects unknown endpoints, wrong methods and oversized bodies", async ({ request }) => {
  expect((await request.get("/api/viveka/arbitrary-path")).status()).toBe(404);
  expect((await request.post("/api/viveka/model-card")).status()).toBe(405);
  expect((await request.post("/api/viveka/workbench", { data: { rows: [] } })).status()).toBe(415);
  expect(
    (
      await request.post("/api/viveka/workbench", {
        headers: { "Content-Type": "multipart/form-data; boundary=test" },
        data: Buffer.alloc(21 * 1024 * 1024),
      })
    ).status(),
  ).toBe(413);
});
