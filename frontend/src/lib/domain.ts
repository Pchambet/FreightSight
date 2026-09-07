import type { Schemas } from "@/lib/api/client";

export type ContainerMilestone = Schemas["ContainerMilestone"];
export type CostType = Schemas["CostType"];
export type CostScope = Schemas["CostScope"];
export type AllocationMethod = Schemas["AllocationMethod"];
export type DndRisk = Schemas["DndRisk"];
export type ImportKind = Schemas["ImportKind"];

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

export const MILESTONE_LABEL: Record<ContainerMilestone, string> = {
  BOOKED: "Booked",
  GATE_IN_FULL_ORIGIN: "Gate in (origin)",
  LOADED: "Loaded on vessel",
  VESSEL_DEPARTED: "Vessel departed",
  VESSEL_ARRIVED: "Vessel arrived",
  DISCHARGED: "Discharged",
  AVAILABLE_FOR_PICKUP: "Available for pickup",
  GATE_OUT_FULL: "Gate out (full)",
  DELIVERED: "Delivered",
  GATE_IN_EMPTY_RETURN: "Empty returned",
};

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

export const COST_TYPE_LABEL: Record<CostType, string> = {
  OCEAN_FREIGHT: "Ocean freight",
  AIR_FREIGHT: "Air freight",
  INSURANCE: "Insurance",
  ORIGIN_CHARGES: "Origin charges",
  THC: "Terminal handling (THC)",
  BL_FEE: "B/L fee",
  CUSTOMS_DUTY: "Customs duty",
  CUSTOMS_BROKERAGE: "Customs brokerage",
  IMPORT_VAT: "Import VAT (recoverable)",
  DRAYAGE: "Drayage / delivery",
  DEMURRAGE: "Demurrage",
  DETENTION: "Detention",
  WAREHOUSING: "Warehousing",
  INSPECTION: "Inspection",
  BANK_FEES: "Bank fees",
  OTHER: "Other",
};

/** Methods a user can pick for ordinary costs. Duty methods are chosen by the backend for CUSTOMS_DUTY. */
export const USER_METHODS: AllocationMethod[] = ["BY_VALUE", "BY_WEIGHT", "BY_VOLUME", "BY_QUANTITY"];

export const METHOD_LABEL: Record<AllocationMethod, string> = {
  BY_VALUE: "By value",
  BY_WEIGHT: "By weight",
  BY_VOLUME: "By volume",
  BY_QUANTITY: "By quantity",
  MANUAL: "Manual %",
  BY_CIF_VALUE: "By CIF value",
  BY_THEORETICAL_DUTY: "By theoretical duty",
};

export const SCOPE_LABEL: Record<CostScope, string> = {
  SHIPMENT: "Shipment",
  CONTAINER: "Container",
  PO: "Purchase order",
  PO_LINE: "PO line",
};

export const RISK_LABEL: Record<DndRisk, string> = {
  NONE: "No risk",
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
  INCURRING: "Incurring",
};

export const IMPORT_FIELDS: Record<ImportKind, { field: string; label: string; required?: boolean }[]> = {
  PURCHASE_ORDERS: [
    { field: "po_number", label: "PO number", required: true },
    { field: "supplier_name", label: "Supplier" },
    { field: "currency", label: "Currency" },
    { field: "order_date", label: "Order date" },
    { field: "line_no", label: "Line no." },
    { field: "sku", label: "SKU / reference" },
    { field: "description", label: "Description" },
    { field: "quantity", label: "Quantity", required: true },
    { field: "unit_price", label: "Unit price", required: true },
    { field: "unit_weight_kg", label: "Unit weight (kg)" },
    { field: "unit_volume_cbm", label: "Unit volume (CBM)" },
    { field: "hs_code", label: "HS code" },
    { field: "duty_rate", label: "Duty rate" },
    { field: "container_number", label: "Container number" },
    { field: "container_quantity", label: "Quantity in container" },
  ],
  LEGACY_PO_CONTAINER: [
    { field: "po_number", label: "PO number", required: true },
    { field: "supplier_name", label: "Supplier" },
    { field: "total_value", label: "Total value" },
    { field: "container_number", label: "Container number" },
    { field: "allocation_percentage", label: "Allocation % (ignored)" },
  ],
};
