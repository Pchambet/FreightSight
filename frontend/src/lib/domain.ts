import type { Schemas } from "@/lib/api/client";

export type ContainerStatus = Schemas["ContainerStatus"];
export type CostType = Schemas["CostType"];
export type AllocationMethod = Schemas["AllocationMethod"];

export const CONTAINER_STATUSES: ContainerStatus[] = ["PENDING", "IN_TRANSIT", "DISCHARGED", "DELIVERED"];

export const CONTAINER_STATUS_LABEL: Record<ContainerStatus, string> = {
  PENDING: "Pending",
  IN_TRANSIT: "In transit",
  DISCHARGED: "Discharged",
  DELIVERED: "Delivered",
};

export const COST_TYPES: CostType[] = ["OCEAN_FREIGHT", "CUSTOMS", "DRAYAGE", "DEMURRAGE"];

export const COST_TYPE_LABEL: Record<CostType, string> = {
  OCEAN_FREIGHT: "Ocean freight",
  CUSTOMS: "Customs duties",
  DRAYAGE: "Drayage (inland)",
  DEMURRAGE: "Demurrage / detention",
};

export const ALLOCATION_METHOD_LABEL: Record<AllocationMethod, string> = {
  BY_VALUE: "Pro rata of PO value",
  MANUAL: "Manual percentages",
};

export function isContainerStatus(value: string): value is ContainerStatus {
  return (CONTAINER_STATUSES as string[]).includes(value);
}
