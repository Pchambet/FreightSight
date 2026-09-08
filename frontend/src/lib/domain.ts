import type { Schemas } from "@/lib/api/client";

export type ContainerMilestone = Schemas["ContainerMilestone"];
export type CostType = Schemas["CostType"];
export type CostScope = Schemas["CostScope"];
export type AllocationMethod = Schemas["AllocationMethod"];
export type DndRisk = Schemas["DndRisk"];
export type ImportKind = Schemas["ImportKind"];

// Labels live in messages/*.json under `domain.*`, keyed by these API values: a component reads
// t(`domain.costType.${value}`). The lists below are only the order the user sees them in.

export const MILESTONES: ContainerMilestone[] = [
  "BOOKED",
  "GATE_IN_FULL_ORIGIN",
  "LOADED",
  "VESSEL_DEPARTED",
  "VESSEL_ARRIVED",
  "DISCHARGED",
  "AVAILABLE_FOR_PICKUP",
  "GATE_OUT_FULL",
  "DELIVERED",
  "GATE_IN_EMPTY_RETURN",
];

export const COST_TYPES: CostType[] = [
  "OCEAN_FREIGHT",
  "AIR_FREIGHT",
  "INSURANCE",
  "ORIGIN_CHARGES",
  "THC",
  "BL_FEE",
  "CUSTOMS_DUTY",
  "CUSTOMS_BROKERAGE",
  "IMPORT_VAT",
  "DRAYAGE",
  "DEMURRAGE",
  "DETENTION",
  "WAREHOUSING",
  "INSPECTION",
  "BANK_FEES",
  "OTHER",
];

/** Methods a user can pick for ordinary costs. Duty methods are chosen by the backend for CUSTOMS_DUTY. */
export const USER_METHODS: AllocationMethod[] = ["BY_VALUE", "BY_WEIGHT", "BY_VOLUME", "BY_QUANTITY"];

export const IMPORT_FIELDS: Record<ImportKind, { field: string; required?: boolean }[]> = {
  PURCHASE_ORDERS: [
    { field: "po_number", required: true },
    { field: "supplier_name" },
    { field: "currency" },
    { field: "order_date" },
    { field: "line_no" },
    { field: "sku" },
    { field: "description" },
    { field: "quantity", required: true },
    { field: "unit_price", required: true },
    { field: "unit_weight_kg" },
    { field: "unit_volume_cbm" },
    { field: "hs_code" },
    { field: "duty_rate" },
    { field: "container_number" },
    { field: "container_quantity" },
  ],
  LEGACY_PO_CONTAINER: [
    { field: "po_number", required: true },
    { field: "supplier_name" },
    { field: "total_value" },
    { field: "container_number" },
    { field: "allocation_percentage" },
  ],
};
