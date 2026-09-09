"use server";

import { revalidatePath } from "next/cache";
import { getTranslations } from "next-intl/server";
import { api, problemMessage, type ImportJobResponse, type LandedCostReport } from "@/lib/api/client";
import { protectAction } from "@/lib/auth";
import type { AllocationMethod, ContainerMilestone, CostScope, CostStatus, CostType, ImportKind, MilestoneCode, RateBasis } from "@/lib/domain";

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

/** `fallbackKey` is a message key: the API's own English sentence is only a last resort. */
async function fail<T>(error: unknown, fallbackKey: string): Promise<ActionResult<T>> {
  const t = await getTranslations();
  return { ok: false, error: await problemMessage(error, t(fallbackKey)) };
}

function normalizeAmount(raw: string): string | null {
  const s = raw.trim().replace(/[\s  ]/g, "");
  if (!s) return null;
  let n = s;
  if (n.includes(",") && n.includes(".")) n = n.lastIndexOf(",") > n.lastIndexOf(".") ? n.replace(/\./g, "").replace(",", ".") : n.replace(/,/g, "");
  else if (n.includes(",")) {
    const [head, tail] = [n.slice(0, n.lastIndexOf(",")), n.slice(n.lastIndexOf(",") + 1)];
    n = tail.length <= 2 ? `${head}.${tail}` : n.replace(/,/g, "");
  }
  return /^\d+(\.\d{1,4})?$/.test(n) ? n : null;
}

// ---------------------------------------------------------------------------- costs

export async function addCost(input: {
  scope: CostScope;
  target_id: string;
  cost_type: string;
  amount: string;
  currency: string;
  cost_date: string;
  allocation_method?: string;
  fx_rate?: string;
  vendor?: string;
  invoice_number?: string;
  status?: CostStatus;
  revalidate: string;
}): Promise<ActionResult<{ id: string }>> {
  const amount = normalizeAmount(input.amount);
  if (amount === null) {
    const t = await getTranslations("costs.form");
    return { ok: false, error: t("amountInvalid") };
  }
  const fx = input.fx_rate ? normalizeAmount(input.fx_rate) : null;
  const { data, error } = await api.POST("/api/v1/costs", {
    body: {
      scope: input.scope,
      target_id: input.target_id,
      cost_type: input.cost_type as CostType,
      status: input.status ?? "ACTUAL",
      amount,
      currency: input.currency,
      cost_date: input.cost_date,
      allocation_method: (input.allocation_method || null) as AllocationMethod | null,
      fx_rate: fx,
      vendor: input.vendor || null,
      invoice_number: input.invoice_number || null,
    },
  });
  if (error || !data) return await fail(error, "costs.form.failed");
  revalidatePath(input.revalidate);
  return { ok: true, data: { id: data.id } };
}

export async function deleteCost(costId: string, revalidate: string): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.DELETE("/api/v1/costs/{cost_id}", { params: { path: { cost_id: costId } } });
  if (error) return await fail(error, "costs.ledger.deleteFailed");
  revalidatePath(revalidate);
  return { ok: true, data: null };
}

export async function previewAllocation(input: {
  container_id?: string;
  po_id?: string;
  method_overrides: Record<string, string>;
}): Promise<ActionResult<LandedCostReport>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/landed-costs/preview", {
    body: {
      container_id: input.container_id ?? null,
      po_id: input.po_id ?? null,
      method_overrides: input.method_overrides as Record<string, AllocationMethod>,
    },
  });
  if (error || !data) return await fail(error, "allocation.previewFailed");
  return { ok: true, data };
}

// ---------------------------------------------------------------------------- containers

export async function updateContainer(
  containerId: string,
  patch: { milestone?: ContainerMilestone; free_days_demurrage?: number | null; discharged_at?: string | null },
): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.PATCH("/api/v1/containers/{container_id}", {
    params: { path: { container_id: containerId } },
    body: patch,
  });
  if (error) return await fail(error, "tracking.failed");
  revalidatePath(`/container/${containerId}`);
  revalidatePath("/containers");
  return { ok: true, data: null };
}

export async function addTrackingEvent(
  containerId: string,
  event: {
    code: MilestoneCode;
    occurred_at: string;
    is_estimate: boolean;
    location_unlocode?: string | null;
    location_name?: string | null;
    vessel_name?: string | null;
    voyage?: string | null;
    note?: string | null;
  },
): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.POST("/api/v1/containers/{container_id}/events", {
    params: { path: { container_id: containerId } },
    body: event,
  });
  if (error) return await fail(error, "timeline.failed");
  revalidatePath(`/container/${containerId}`);
  revalidatePath("/containers");
  return { ok: true, data: null };
}

export async function markAlertRead(alertId: string): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.POST("/api/v1/alerts/{alert_id}/read", { params: { path: { alert_id: alertId } } });
  if (error) return await fail(error, "alerts.failed");
  revalidatePath("/alerts");
  revalidatePath("/", "layout");
  return { ok: true, data: null };
}

export async function markAllAlertsRead(): Promise<ActionResult<{ marked: number }>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/alerts/read-all");
  if (error || !data) return await fail(error, "alerts.failed");
  revalidatePath("/alerts");
  revalidatePath("/", "layout");
  return { ok: true, data: { marked: data.marked } };
}

// ---------------------------------------------------------------------------- invoices

export async function uploadInvoice(formData: FormData): Promise<ActionResult<{ id: string }>> {
  await protectAction();
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return await fail(null, "invoices.upload.failed");
  const { data, error, response } = await api.POST("/api/v1/invoices", {
    body: { file: file as unknown as string },
    bodySerializer: (b) => {
      const fd = new FormData();
      fd.append("file", b.file as unknown as File, file.name);
      return fd;
    },
  });
  if (response.status === 409) return await fail(error, "invoices.upload.duplicate");
  if (error || !data) return await fail(error, "invoices.upload.failed");
  revalidatePath("/invoices");
  return { ok: true, data: { id: data.id } };
}

export async function updateInvoiceLine(
  invoiceId: string,
  lineId: string,
  patch: { amount?: string | null; currency?: string | null; cost_type?: CostType | null; scope?: CostScope | null; target_id?: string | null; accepted?: boolean | null; description?: string | null },
): Promise<ActionResult<null>> {
  await protectAction();
  const body = { ...patch };
  if (typeof body.amount === "string") {
    const n = normalizeAmount(body.amount);
    if (!n) return await fail(null, "invoices.line.failed");
    body.amount = n;
  }
  const { error } = await api.PATCH("/api/v1/invoices/{invoice_id}/lines/{line_id}", {
    params: { path: { invoice_id: invoiceId, line_id: lineId } },
    body,
  });
  if (error) return await fail(error, "invoices.line.failed");
  revalidatePath(`/invoices/${invoiceId}`);
  return { ok: true, data: null };
}

export async function confirmInvoice(invoiceId: string): Promise<ActionResult<{ costsCreated: number }>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/invoices/{invoice_id}/confirm", { params: { path: { invoice_id: invoiceId } } });
  if (error || !data) return await fail(error, "invoices.detail.failed");
  revalidatePath(`/invoices/${invoiceId}`);
  revalidatePath("/invoices");
  revalidatePath("/containers");
  return { ok: true, data: { costsCreated: data.costs_created } };
}

export async function rejectInvoice(invoiceId: string): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.POST("/api/v1/invoices/{invoice_id}/reject", { params: { path: { invoice_id: invoiceId } } });
  if (error) return await fail(error, "invoices.detail.failed");
  revalidatePath(`/invoices/${invoiceId}`);
  revalidatePath("/invoices");
  return { ok: true, data: null };
}

export async function retryInvoice(invoiceId: string): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.POST("/api/v1/invoices/{invoice_id}/retry", { params: { path: { invoice_id: invoiceId } } });
  if (error) return await fail(error, "invoices.detail.failed");
  revalidatePath(`/invoices/${invoiceId}`);
  return { ok: true, data: null };
}

// ---------------------------------------------------------------------------- estimates

export async function applyEstimates(containerId: string): Promise<ActionResult<{ created: number; skipped: Record<string, string> }>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/containers/{container_id}/estimates", { params: { path: { container_id: containerId } } });
  if (error || !data) return await fail(error, "estimates.failed");
  revalidatePath(`/container/${containerId}`);
  revalidatePath("/containers");
  return { ok: true, data: { created: data.created.length, skipped: data.skipped } };
}

export async function closeEstimate(costId: string, reason: string, revalidate: string): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.POST("/api/v1/costs/{cost_id}/close", { params: { path: { cost_id: costId } }, body: { reason: reason.trim() || "closed" } });
  if (error) return await fail(error, "estimates.failed");
  revalidatePath(revalidate);
  return { ok: true, data: null };
}

export async function addRateCard(input: { cost_type: CostType; scope: "CONTAINER" | "SHIPMENT"; basis: RateBasis; amount: string; currency: string; hs_code?: string; notes?: string }): Promise<ActionResult<null>> {
  await protectAction();
  const amount = normalizeAmount(input.amount);
  if (amount === null) return await fail(null, "rateCards.failed");
  const { error } = await api.POST("/api/v1/organization/rate-cards", {
    body: { cost_type: input.cost_type, scope: input.scope, basis: input.basis, amount, currency: input.currency.toUpperCase(), hs_code: input.hs_code || null, notes: input.notes || null },
  });
  if (error) return await fail(error, "rateCards.failed");
  revalidatePath("/settings");
  return { ok: true, data: null };
}

export async function deleteRateCard(cardId: string): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.DELETE("/api/v1/organization/rate-cards/{card_id}", { params: { path: { card_id: cardId } } });
  if (error) return await fail(error, "rateCards.failed");
  revalidatePath("/settings");
  return { ok: true, data: null };
}

// ---------------------------------------------------------------------------- erp

export async function connectErp(input: { url: string; database: string; login: string; api_key: string }): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.POST("/api/v1/erp/connection", { body: { kind: "ODOO", url: input.url.trim(), database: input.database.trim(), login: input.login.trim(), api_key: input.api_key } });
  if (error) return await fail(error, "erp.connectFailed");
  revalidatePath("/settings");
  return { ok: true, data: null };
}

export async function disconnectErp(): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.DELETE("/api/v1/erp/connection");
  if (error) return await fail(error, "erp.connectFailed");
  revalidatePath("/settings");
  return { ok: true, data: null };
}

export async function syncErp(): Promise<ActionResult<{ orders: number; lines: number; status: string; error: string | null }>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/erp/sync");
  if (error || !data) return await fail(error, "erp.syncFailed");
  revalidatePath("/settings");
  revalidatePath("/purchase-orders");
  revalidatePath("/containers");
  return { ok: true, data: { orders: data.purchase_orders, lines: data.lines, status: data.status, error: data.error ?? null } };
}

export async function createContainer(containerNumber: string): Promise<ActionResult<{ id: string }>> {
  const { data, error } = await api.POST("/api/v1/containers", {
    body: { container_number: containerNumber.trim().toUpperCase() },
  });
  if (error || !data) return await fail(error, "containers.new.failed");
  revalidatePath("/containers");
  return { ok: true, data: { id: data.id } };
}

export async function replaceLoads(
  containerId: string,
  loads: { po_line_id: string; quantity: string }[],
): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.PUT("/api/v1/containers/{container_id}/loads", {
    params: { path: { container_id: containerId } },
    body: loads,
  });
  if (error) return await fail(error, "loads.failed");
  revalidatePath(`/container/${containerId}`);
  revalidatePath("/containers");
  return { ok: true, data: null };
}

// ---------------------------------------------------------------------------- imports

export async function createImport(formData: FormData): Promise<ActionResult<ImportJobResponse>> {
  await protectAction();
  const file = formData.get("file");
  const kind = String(formData.get("kind") ?? "PURCHASE_ORDERS") as ImportKind;
  if (!(file instanceof File) || file.size === 0) {
    const t = await getTranslations("importWizard.upload");
    return { ok: false, error: t("chooseFirst") };
  }
  const body = new FormData();
  body.append("kind", kind);
  body.append("file", file, file.name);
  const { data, error } = await api.POST("/api/v1/imports", {
    body: body as unknown as { kind: ImportKind; file: string },
    bodySerializer: (b) => b as unknown as BodyInit,
  });
  if (error || !data) return await fail(error, "importWizard.upload.failed");
  return { ok: true, data };
}

export async function validateImport(importId: string, mapping: Record<string, string>): Promise<ActionResult<ImportJobResponse>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/imports/{import_id}/validate", {
    params: { path: { import_id: importId } },
    body: { mapping },
  });
  if (error || !data) return await fail(error, "importWizard.mapping.failed");
  return { ok: true, data };
}

export async function commitImport(importId: string, onError: "skip_rows" | "abort"): Promise<ActionResult<ImportJobResponse>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/imports/{import_id}/commit", {
    params: { path: { import_id: importId } },
    body: { on_error: onError },
  });
  if (error || !data) return await fail(error, "importWizard.review.failed");
  revalidatePath("/containers");
  revalidatePath("/purchase-orders");
  revalidatePath("/imports");
  return { ok: true, data };
}

// ---------------------------------------------------------------------------- demo data

export async function loadSampleData(): Promise<ActionResult<{ containerIds: string[] }>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/organization/sample-data", {});
  if (error || !data) return await fail(error, "containers.sample.failed");
  revalidatePath("/containers");
  revalidatePath("/purchase-orders");
  return { ok: true, data: { containerIds: data.container_ids } };
}

// ---------------------------------------------------------------------------- settings

export async function updateOrganization(input: {
  name?: string;
  base_currency?: string;
  default_allocation_method?: string;
  free_days_demurrage?: number;
  free_days_detention?: number;
}): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.PATCH("/api/v1/organization", {
    body: { ...input, default_allocation_method: input.default_allocation_method as AllocationMethod | undefined },
  });
  if (error) return await fail(error, "settings.failed");
  revalidatePath("/settings");
  revalidatePath("/containers");
  return { ok: true, data: null };
}
