import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/** Offline by construction: anything that is not the local server fails fast instead of hanging. */
async function goOffline(page: Page) {
  await page.route("**/*", (route) => {
    const host = new URL(route.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? route.continue() : route.abort();
  });
}

/**
 * A Clerk development instance answers the first document request of a cookie-less browser with a 307 to
 * its Frontend API (the "dev browser" handshake), which an offline run cannot follow. Any value of the
 * dev-browser cookie skips it; the visitor stays anonymous, which is exactly what these tests want.
 */
async function skipClerkHandshake(context: BrowserContext, baseURL: string) {
  await context.addCookies([{ name: "__clerk_db_jwt", value: "e2e_stub", url: baseURL }]);
}

test.beforeEach(async ({ page, context, baseURL }) => {
  await skipClerkHandshake(context, baseURL!);
  await goOffline(page);
});

const PUBLIC_PAGES = [
  { path: "/?preview=1", name: "landing" },
  { path: "/securite", name: "security" },
  { path: "/design-partner", name: "design partner one-pager" },
];

for (const { path, name } of PUBLIC_PAGES) {
  test(`${name} renders without a session`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.locator("h1").first()).toBeVisible();
    await expect(page).toHaveTitle(/FreightSight/);
    // A booking link is the point of every public page.
    await expect(page.locator('a[href*="cal.com"], a[href*="calendly"], a[href^="mailto:"]').first()).toHaveCount(1);
  });

  test(`${name} has an Open Graph image (A4-3: a shared link used to show nothing)`, async ({ page }) => {
    await page.goto(path);
    const ogImage = page.locator('meta[property="og:image"]');
    await expect(ogImage).toHaveCount(1);
    expect(await ogImage.getAttribute("content")).toMatch(/^https?:\/\/.+\/(?:[\w-]+\/)*opengraph-image/);
    // Twitter card inherits the same image from Open Graph (no twitter.images set) — see ogImage.tsx.
    await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute("content", "summary_large_image");
  });
}

test("the demurrage calculator computes and reads its state from the URL", async ({ page }) => {
  await page.goto("/?preview=1");
  const total = page.locator("#calculateur .tabular-nums").first(); // the headline figure
  await expect(page.locator("#dd-port")).toHaveValue("ANR");

  // Le Havre, 2 containers, 8 days: 5 x 55 + 3 x 85 = 530 each, 1060 in total.
  await page.goto("/?preview=1&port=LEH&c=2&d=8");
  await expect(page.locator("#dd-port")).toHaveValue("LEH");
  await expect(page.locator("#dd-c")).toHaveValue("2");
  await expect(total).toHaveText(/1\D?060/);

  // Three more days, one of them at Le Havre's third tier: 275 + 425 + 130 = 830 each, 1660 in total.
  await page.locator("#dd-d").fill("11");
  await expect(total).toHaveText(/1\D?660/);
});

test("the sign-in page renders and the app board redirects to it", async ({ page }) => {
  const signIn = await page.goto("/sign-in");
  expect(signIn?.status()).toBe(200);
  await expect(page).toHaveURL(/\/sign-in$/); // no handshake redirect away from the page
  expect(await page.locator('[href*="clerk"], [src*="clerk"]').count()).toBeGreaterThan(0);

  await page.goto("/containers");
  await expect(page).toHaveURL(/\/sign-in/);
});

test("robots.txt keeps the application out of search engines", async ({ request }) => {
  const res = await request.get("/robots.txt");
  expect(res.status()).toBe(200);
  const body = await res.text();
  expect(body).toContain("Disallow: /containers");
  expect(body).toContain("Allow: /securite");
});

test("sitemap.xml lists the public pages (A4-4: it used to 307 to /sign-in)", async ({ request }) => {
  const res = await request.get("/sitemap.xml");
  expect(res.status()).toBe(200);
  const body = await res.text();
  expect(body).toContain("<loc>");
  expect(body).toContain("/securite</loc>");
  expect(body).toContain("/design-partner</loc>");
});

test("an unknown URL renders a real 404, not a sign-in redirect (A4-4)", async ({ page }) => {
  const response = await page.goto("/this-does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page).toHaveURL(/\/this-does-not-exist$/);
  await expect(page.locator("h1").first()).toHaveText(/introuvable/i);
});

test("a shared report link that does not exist answers a real 404, out of search engines, without a session", async ({ page }) => {
  // No API runs here, which is also what an unknown, expired or withdrawn token looks like from the
  // page's side: one answer for all of them, and nothing that says which.
  const response = await page.goto(`/r/${"x".repeat(43)}`);
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/plus valable|no longer valid/);
  await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute("content", /noindex/);
});

test("the public pages answer without the Clerk middleware, so a cookie-less client is never sent to a handshake", async ({ request }) => {
  // On a Clerk development instance the middleware answers a document request that carries no Clerk
  // cookie with a redirect to Clerk's handshake, and a client that keeps no cookies (a search
  // engine, a link preview) looped on it forever on these pages (seen on production, 18 Sept 2026).
  // The middleware marks every response it handles with x-clerk-auth-status.
  for (const path of ["/", "/securite", "/design-partner", `/r/${"x".repeat(43)}`]) {
    const response = await request.get(path, { headers: { accept: "text/html" }, maxRedirects: 0 });
    expect(response.headers()["x-clerk-auth-status"], path).toBeUndefined();
    expect(response.status(), path).not.toBe(307);
  }
  // What the check relies on: on an application page, the middleware does run.
  const signIn = await request.get("/sign-in", { headers: { accept: "text/html" }, maxRedirects: 0 });
  expect(signIn.headers()["x-clerk-auth-status"]).toBeDefined();
});
