type Json = Record<string, unknown> | null | undefined;

type Formatters = {
  field: (key: string) => string;
  invoiceStatus: (code: string) => string;
  costCount: (count: number) => string;
  money: (amount: string) => string;
};

function parseValue(v: unknown): unknown {
  if (typeof v !== "string") return v;
  const t = v.trim();
  if ((t.startsWith("[") && t.endsWith("]")) || (t.startsWith("{") && t.endsWith("}"))) {
    try {
      return JSON.parse(t);
    } catch {
      return v;
    }
  }
  return v;
}

function formatValue(key: string, v: unknown, f: Formatters): string {
  const val = parseValue(v);
  if (val === null || val === undefined || val === "") return "—";
  if (key === "status" && typeof val === "string") return f.invoiceStatus(val);
  if (key === "cost_ids" && Array.isArray(val)) return f.costCount(val.length);
  if (key === "total_amount" && (typeof val === "string" || typeof val === "number")) return f.money(String(val));
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}

/** Keys whose value differs between before and after, with human-readable labels and values. */
export function auditDiff(before: Json, after: Json, f: Formatters): { key: string; label: string; from: string; to: string }[] {
  const b = (before ?? {}) as Record<string, unknown>;
  const a = (after ?? {}) as Record<string, unknown>;
  const keys = Array.from(new Set([...Object.keys(b), ...Object.keys(a)])).sort();
  return keys
    .filter((k) => JSON.stringify(b[k]) !== JSON.stringify(a[k]))
    .map((k) => ({
      key: k,
      label: f.field(k),
      from: formatValue(k, b[k], f),
      to: formatValue(k, a[k], f),
    }));
}

export function auditEntityRef(
  entityType: string,
  entityId: string | null | undefined,
  before: Json,
  after: Json,
  entityLabel: (type: string) => string,
): string {
  const payload = { ...(before ?? {}), ...(after ?? {}) } as Record<string, unknown>;
  if (entityType === "invoice") {
    const num = payload.invoice_number;
    if (typeof num === "string" && num) return `${entityLabel(entityType)} ${num}`;
  }
  if (!entityId) return entityLabel(entityType);
  return `${entityLabel(entityType)} ${entityId.slice(0, 8)}`;
}
