import "server-only";
import { auth } from "@clerk/nextjs/server";
import createClient, { type Middleware } from "openapi-fetch";
import { getTranslations } from "next-intl/server";
import type { components, paths } from "./schema";
import { env } from "@/lib/env";

export type Schemas = components["schemas"];
export type ContainerSummary = Schemas["ContainerSummary"];
export type ContainerResponse = Schemas["ContainerResponse"];
export type LandedCostReport = Schemas["LandedCostReport"];
export type TrackingEventResponse = Schemas["TrackingEventResponse"];
export type InvoiceResponse = Schemas["InvoiceResponse"];
export type AuditEntry = Schemas["AuditEntryResponse"];
export type RateCard = Schemas["RateCardResponse"];
export type VarianceReport = Schemas["VarianceReport"];
export type ErpConnection = Schemas["ErpConnectionResponse"];
export type ErpSyncRun = Schemas["ErpSyncRunResponse"];
export type LandedCostAnalysis = Schemas["LandedCostAnalysis"];
export type DndAnalysis = Schemas["DndAnalysis"];
export type InvoiceSummary = Schemas["InvoiceSummary"];
export type InvoiceLineResponse = Schemas["InvoiceLineResponse"];
export type EtaHistoryResponse = Schemas["EtaHistoryResponse"];
export type ReportLine = Schemas["ReportLine"];
export type CostResponse = Schemas["CostResponse"];
export type PurchaseOrderSummary = Schemas["PurchaseOrderSummary"];
export type PurchaseOrderResponse = Schemas["PurchaseOrderResponse"];
export type ImportJobResponse = Schemas["ImportJobResponse"];
export type OrganizationResponse = Schemas["OrganizationResponse"];
export type ShipmentResponse = Schemas["ShipmentResponse"];
export type LoadResponse = Schemas["LoadResponse"];

export type Problem = {
  type?: string;
  title?: string;
  status?: number;
  code?: string | null;
  detail?: string | null;
  errors?: { field: string; code: string; message: string }[] | null;
  //: The moving parts of the top-level `code`'s sentence (a host, a count of seconds, a login) — a
  //: `DomainError(..., params={...})` on the backend lands here verbatim. Absent on a problem with no
  //: params, never on the per-field `errors[]` entries, which carry no params of their own yet.
  params?: Record<string, string> | null;
  //: Same id as the response's X-Request-ID header and the server log line — see core/observability.py.
  request_id?: string | null;
};

/**
 * Every request carries the caller's Clerk session token, fetched right before the call (tokens live
 * 60 s). The backend derives the organization from the token; nothing about the tenant is trusted
 * from this side.
 */
const authHeaders: Middleware = {
  async onRequest({ request }) {
    const { getToken } = await auth();
    const token = await getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    if (env.ORG_ID) request.headers.set("X-Org-Id", env.ORG_ID); // dev backends without Clerk only
    return request;
  },
};

/**
 * A request that never reaches the server (offline, DNS, TLS, or a hang past 30 s) throws instead of
 * resolving, and openapi-fetch does not catch that — it would surface as an unhandled exception in a
 * server action instead of a translatable error. Manufacturing a problem+json response here keeps
 * every caller on the single `{ data, error }` shape and the single `problemMessage` translation path.
 */
async function resilientFetch(request: Request): Promise<Response> {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  request.signal?.addEventListener("abort", onAbort);
  const timeout = setTimeout(() => controller.abort(), 30_000);
  try {
    return await fetch(request, { cache: "no-store", signal: controller.signal });
  } catch (err) {
    const code = err instanceof Error && err.name === "AbortError" ? "REQUEST_TIMEOUT" : "NETWORK_ERROR";
    return new Response(JSON.stringify({ title: code, status: 503, code }), {
      status: 503,
      headers: { "content-type": "application/json" },
    });
  } finally {
    clearTimeout(timeout);
    request.signal?.removeEventListener("abort", onAbort);
  }
}

export const api = createClient<paths>({
  baseUrl: env.API_URL,
  fetch: resilientFetch,
});
api.use(authHeaders);

/**
 * Turn a problem+json error body into one readable sentence in the user's language.
 *
 * The backend answers in English with a machine-readable `code`; the front translates the code. A
 * code we have no key for — or no code at all — never falls back to the server's own English
 * sentence: that sentence is a debugging aid (`detail`) that can legitimately carry internal detail
 * (a hostname, an errno, a stack fragment), never vetted for a screen a DAF reads. It falls back to a
 * neutral sentence instead, with the request id when there is one so a support ticket can find the
 * exact log line.
 */
export async function problemMessage(error: unknown, fallback?: string): Promise<string> {
  const t = await getTranslations("errors");
  const has = (code: string | null | undefined): code is string => !!code && t.has(code);
  const fallbackMessage = fallback ?? t("fallback");
  if (error && typeof error === "object") {
    const p = error as Problem;
    const withRef = (message: string) => (p.request_id ? t("withRequestId", { message, id: p.request_id }) : message);
    if (p.errors?.length) {
      return p.errors
        .map((e) => t("fieldPrefix", { field: e.field, message: has(e.code) ? t(e.code) : t("unknownField") }))
        .join(", ");
    }
    if (has(p.code)) return t(p.code, p.params ?? undefined);
    return withRef(fallbackMessage);
  }
  return fallbackMessage;
}
