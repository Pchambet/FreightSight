"use server";

import { revalidatePath } from "next/cache";
import { api, problemMessage, type ImportResponse } from "@/lib/api/client";
import { COST_TYPES, type CostType } from "@/lib/domain";

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

export async function uploadPurchaseOrders(formData: FormData): Promise<ActionResult<ImportResponse>> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, error: "Choose a CSV file first." };
  if (!file.name.toLowerCase().endsWith(".csv")) return { ok: false, error: "Only CSV files are supported." };

  const body = new FormData();
  body.append("file", file, file.name);
  const { data, error } = await api.POST("/api/purchase-orders/upload", {
    // openapi-fetch serialises multipart bodies itself when given FormData
    body: body as unknown as { file: string },
  });
  if (error || !data) return { ok: false, error: problemMessage(error, "Upload failed") };
  revalidatePath("/");
  return { ok: true, data };
}

export async function addCost(
  containerId: string,
  currency: string,
  input: { cost_type: string; amount: string },
): Promise<ActionResult<{ id: string }>> {
  if (!(COST_TYPES as string[]).includes(input.cost_type)) return { ok: false, error: "Unknown cost type." };
  const amount = input.amount.trim().replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0) {
    return { ok: false, error: "Amount must be a positive number with at most two decimals." };
  }
  const { data, error } = await api.POST("/api/containers/{container_id}/costs", {
    params: { path: { container_id: containerId } },
    body: { cost_type: input.cost_type as CostType, amount, currency },
  });
  if (error || !data) return { ok: false, error: problemMessage(error, "Could not add the cost") };
  revalidatePath(`/container/${containerId}`);
  return { ok: true, data: { id: data.id } };
}

export async function updateContainerStatus(containerId: string, status: string): Promise<ActionResult<null>> {
  const { error } = await api.PATCH("/api/containers/{container_id}", {
    params: { path: { container_id: containerId } },
    body: { status: status as never },
  });
  if (error) return { ok: false, error: problemMessage(error, "Could not update the status") };
  revalidatePath(`/container/${containerId}`);
  revalidatePath("/");
  return { ok: true, data: null };
}
