"use server";

import { revalidatePath } from "next/cache";
import { api, problemMessage, type ImportJobResponse, type LandedCostReport } from "@/lib/api/client";
import { protectAction } from "@/lib/auth";
import type { AllocationMethod, ContainerMilestone, CostScope, CostType, ImportKind } from "@/lib/domain";

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

function fail<T>(error: unknown, fallback: string): ActionResult<T> {
  return { ok: false, error: problemMessage(error, fallback) };
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
  revalidate: string;
}): Promise<ActionResult<{ id: string }>> {
  const amount = normalizeAmount(input.amount);
  if (amount === null) return { ok: false, error: "Amount must be a positive number with at most two decimals." };
  const fx = input.fx_rate ? normalizeAmount(input.fx_rate) : null;
  const { data, error } = await api.POST("/api/v1/costs", {
    body: {
      scope: input.scope,
      target_id: input.target_id,
      cost_type: input.cost_type as CostType,
      amount,
      currency: input.currency,
      cost_date: input.cost_date,
      allocation_method: (input.allocation_method || null) as AllocationMethod | null,
      fx_rate: fx,
      vendor: input.vendor || null,
      invoice_number: input.invoice_number || null,
    },
  });
  if (error || !data) return fail(error, "Could not add the cost");
  revalidatePath(input.revalidate);
  return { ok: true, data: { id: data.id } };
}

export async function deleteCost(costId: string, revalidate: string): Promise<ActionResult<null>> {
  await protectAction();
  const { error } = await api.DELETE("/api/v1/costs/{cost_id}", { params: { path: { cost_id: costId } } });
  if (error) return fail(error, "Could not delete the cost");
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
  if (error || !data) return fail(error, "Preview failed");
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
  if (error) return fail(error, "Could not update the container");
  revalidatePath(`/container/${containerId}`);
  revalidatePath("/containers");
  return { ok: true, data: null };
}

export async function createContainer(containerNumber: string): Promise<ActionResult<{ id: string }>> {
  const { data, error } = await api.POST("/api/v1/containers", {
    body: { container_number: containerNumber.trim().toUpperCase() },
  });
  if (error || !data) return fail(error, "Could not create the container");
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
  if (error) return fail(error, "Could not update the loads");
  revalidatePath(`/container/${containerId}`);
  revalidatePath("/containers");
  return { ok: true, data: null };
}

// ---------------------------------------------------------------------------- imports

export async function createImport(formData: FormData): Promise<ActionResult<ImportJobResponse>> {
  await protectAction();
  const file = formData.get("file");
  const kind = String(formData.get("kind") ?? "PURCHASE_ORDERS") as ImportKind;
  if (!(file instanceof File) || file.size === 0) return { ok: false, error: "Choose a file first." };
  const body = new FormData();
  body.append("kind", kind);
  body.append("file", file, file.name);
  const { data, error } = await api.POST("/api/v1/imports", {
    body: body as unknown as { kind: ImportKind; file: string },
    bodySerializer: (b) => b as unknown as BodyInit,
  });
  if (error || !data) return fail(error, "Upload failed");
  return { ok: true, data };
}

export async function validateImport(importId: string, mapping: Record<string, string>): Promise<ActionResult<ImportJobResponse>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/imports/{import_id}/validate", {
    params: { path: { import_id: importId } },
    body: { mapping },
  });
  if (error || !data) return fail(error, "Validation failed");
  return { ok: true, data };
}

export async function commitImport(importId: string, onError: "skip_rows" | "abort"): Promise<ActionResult<ImportJobResponse>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/imports/{import_id}/commit", {
    params: { path: { import_id: importId } },
    body: { on_error: onError },
  });
  if (error || !data) return fail(error, "Import failed");
  revalidatePath("/containers");
  revalidatePath("/purchase-orders");
  revalidatePath("/imports");
  return { ok: true, data };
}

// ---------------------------------------------------------------------------- demo data

export async function loadSampleData(): Promise<ActionResult<{ containerIds: string[] }>> {
  await protectAction();
  const { data, error } = await api.POST("/api/v1/organization/sample-data", {});
  if (error || !data) return fail(error, "Could not load the sample data");
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
  if (error) return fail(error, "Could not save the settings");
  revalidatePath("/settings");
  revalidatePath("/containers");
  return { ok: true, data: null };
}
