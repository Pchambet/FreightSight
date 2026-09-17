type Json = Record<string, unknown> | null | undefined;

export type Formatters = {
  field: (key: string) => string;
  invoiceStatus: (code: string) => string;
  costCount: (count: number) => string;
  money: (amount: string) => string;
  rate: (amount: string) => string;
  costType: (code: string) => string;
  method: (code: string) => string;
  scope: (code: string) => string;
  milestone: (code: string) => string;
  bool: (value: boolean) => string;
  lineRef: (id: string) => string;
  documentState: (code: string) => string;
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** First 8 hex chars of a uuid, the way the rest of the app already shortens ids for display. */
function shortId(v: string): string {
  return `${v.slice(0, 8)}…`;
}

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

/**
 * A record's before/after is whatever the domain model held — raw enum members, decimal strings,
 * uuids, booleans. This is the one place that turns that back into what a DAF (or an auditor) reads:
 * every enum through its existing `domain.*` translation, every amount and fx rate through the same
 * locale-aware formatters as the rest of the screen, every id shortened rather than shown in full.
 * See audit B41: this table used to be the one screen where the raw model leaked straight through.
 */
function formatValue(key: string, v: unknown, f: Formatters): string {
  const val = parseValue(v);
  if (val === null || val === undefined || val === "") return "—";
  if (typeof val === "boolean") return f.bool(val);
  if (key === "status" && typeof val === "string") return f.invoiceStatus(val);
  if (key === "cost_ids" && Array.isArray(val)) return f.costCount(val.length);
  if ((key === "total_amount" || key === "amount" || key === "amount_base") && (typeof val === "string" || typeof val === "number")) return f.money(String(val));
  if (key === "fx_rate" && (typeof val === "string" || typeof val === "number")) return f.rate(String(val));
  if (key === "cost_type" && typeof val === "string") return f.costType(val);
  if (key === "allocation_method" && typeof val === "string") return f.method(val);
  if (key === "scope" && typeof val === "string") return f.scope(val);
  if (key === "milestone" && typeof val === "string") return f.milestone(val);
  if (key === "document_state" && typeof val === "string") return f.documentState(val);
  if (typeof val === "string" && UUID_RE.test(val)) return shortId(val);
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
      // container_loads_replaced logs one entry per po_line_id, so the "field" is itself a uuid —
      // there is no sku or line number in this payload to name it by (needs_other_lane: the backend
      // would need to log a label alongside the id for a real one).
      label: UUID_RE.test(k) ? f.lineRef(shortId(k)) : f.field(k),
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
