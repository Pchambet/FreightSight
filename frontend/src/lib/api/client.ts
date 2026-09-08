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

export const api = createClient<paths>({
  baseUrl: env.API_URL,
  fetch: (request) => fetch(request, { cache: "no-store" }),
});
api.use(authHeaders);

/**
 * Turn a problem+json error body into one readable sentence in the user's language.
 *
 * The backend answers in English with a machine-readable `code`; the front translates the code and
 * only falls back to the server's own sentence when it carries detail we have no key for.
 */
export async function problemMessage(error: unknown, fallback?: string): Promise<string> {
  const t = await getTranslations("errors");
  const has = (code: string | null | undefined): code is string => !!code && t.has(code);
  const fallbackMessage = fallback ?? t("fallback");
  if (error && typeof error === "object") {
    const p = error as Problem & { message?: string };
    if (p.errors?.length) {
      return p.errors
        .map((e) => t("fieldPrefix", { field: e.field, message: has(e.code) ? t(e.code) : e.message }))
        .join(", ");
    }
    if (has(p.code)) return t(p.code);
    if (typeof p.detail === "string") return p.detail;
    if (typeof p.message === "string") return p.message;
    if (typeof p.title === "string") return p.title;
  }
  return fallbackMessage;
}
