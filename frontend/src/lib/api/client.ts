import "server-only";
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";
import { env } from "@/lib/env";

export type Schemas = components["schemas"];
export type ContainerResponse = Schemas["ContainerResponse"];
export type LandedCostResponse = Schemas["LandedCostResponse"];
export type ImportResponse = Schemas["ImportResponse"];
export type CostResponse = Schemas["CostResponse"];
export type Problem = {
  type?: string;
  title?: string;
  status?: number;
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
    const p = error as Problem & { message?: string; code?: string };
    if (p.errors?.length) return p.errors.map((e) => `${e.field}: ${e.message}`).join(", ");
    if (typeof p.detail === "string") return p.detail;
    if (typeof p.message === "string") return p.message;
    if (typeof p.title === "string") return p.title;
  }
  return fallback;
}
