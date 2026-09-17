/**
 * `DndLine.rule` / `DndAtRiskLine.rule` are free-text English sentences built in
 * `backend/app/domain/reporting/service.py` (e.g. "last free day was 2026-09-14; demurrage may be
 * running") — there is no code alongside them, unlike every other domain message in this app (see
 * the ERP push blockers for the pattern this should really follow). Audit B30 flags this as the most
 * visible English leak in the app, on the screen a DAF reads for reporting.
 *
 * Until the backend emits a `{code, params}` pair here (needs_other_lane), this parses the current
 * fixed set of English templates back into a French sentence with correctly formatted numbers and
 * dates. Anything that does not match one of them — a template this file has not been taught yet —
 * falls back to a neutral message, never the raw English.
 */
export type DndRule =
  | { kind: "noAlert" }
  | { kind: "noRateCard" }
  | { kind: "estimable"; days: number; dailyRate: string }
  | { kind: "lfdOver"; date: string }
  | { kind: "lfdLeft"; date: string; days: number }
  | { kind: "riskNoLfd"; risk: string }
  | { kind: "unknown" };

export function parseDndRule(raw: string): DndRule {
  if (raw === "no risk alert and no pickup recorded: nothing to estimate") return { kind: "noAlert" };
  if (raw.startsWith("not estimable: add a DEMURRAGE rate card")) return { kind: "noRateCard" };

  let m = raw.match(/^(\d+) day\(s\) between the first risk alert and pickup x ([\d.]+) per day$/);
  if (m) return { kind: "estimable", days: Number(m[1]), dailyRate: m[2] };

  m = raw.match(/^last free day was (\d{4}-\d{2}-\d{2}); demurrage may be running$/);
  if (m) return { kind: "lfdOver", date: m[1] };

  m = raw.match(/^last free day (\d{4}-\d{2}-\d{2}), (\d+) day\(s\) left$/);
  if (m) return { kind: "lfdLeft", date: m[1], days: Number(m[2]) };

  m = raw.match(/^risk (\w+); no last free day recorded$/);
  if (m) return { kind: "riskNoLfd", risk: m[1] };

  return { kind: "unknown" };
}
