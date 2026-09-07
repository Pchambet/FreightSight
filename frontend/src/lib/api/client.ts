import "server-only";
import createClient from "openapi-fetch";
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

export const api = createClient<paths>({
  baseUrl: env.API_URL,
  headers: { "X-Org-Id": env.ORG_ID },
  fetch: (request) => fetch(request, { cache: "no-store" }),
});

/** Turn a problem+json error body into one readable sentence. */
export function problemMessage(error: unknown, fallback = "Request failed"): string {
  if (error && typeof error === "object") {
    const p = error as Problem & { message?: string };
    if (p.errors?.length) return p.errors.map((e) => `${e.field}: ${e.message}`).join(", ");
    if (typeof p.detail === "string") return p.detail;
    if (typeof p.message === "string") return p.message;
    if (typeof p.title === "string") return p.title;
  }
  return fallback;
}
