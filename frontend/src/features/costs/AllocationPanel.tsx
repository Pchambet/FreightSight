"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { Card, input, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { previewAllocation } from "@/features/actions";
import type { LandedCostReport } from "@/lib/api/client";
import { COST_TYPE_LABEL, METHOD_LABEL, USER_METHODS, type CostType } from "@/lib/domain";
import { qty, unitCost } from "@/lib/format";

/**
 * Breakdown per PO line with a live "what if" switch: change the method per cost type and the
 * unit landed cost recomputes through the backend preview endpoint. Nothing is persisted here.
 */
export default function AllocationPanel({ containerId, poId, report }: { containerId?: string; poId?: string; report: LandedCostReport }) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<LandedCostReport | null>(null);
  const [pending, startTransition] = useTransition();
  const cur = report.base_currency;

  const costTypes = useMemo(() => {
    const present = new Set<CostType>();
    for (const c of report.costs) if (c.cost_type !== "CUSTOMS_DUTY" && c.cost_type !== "IMPORT_VAT") present.add(c.cost_type);
    return [...present];
  }, [report.costs]);

  const setOverride = (t: string, value: string) => {
    const next = { ...overrides };
    if (value) next[t] = value;
    else delete next[t];
    setOverrides(next);
    if (Object.keys(next).length === 0) setPreview(null);
  };

  useEffect(() => {
    if (Object.keys(overrides).length === 0) return;
    const handle = setTimeout(() => {
      startTransition(async () => {
        const result = await previewAllocation({ container_id: containerId, po_id: poId, method_overrides: overrides });
        if (result.ok) setPreview(result.data);
      });
    }, 150);
    return () => clearTimeout(handle);
  }, [overrides, containerId, poId]);

  const shown = preview ?? report;
  const isPreview = preview !== null;

  return (
    <Card
      title="Landed cost per purchase-order line"
      right={isPreview ? <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded">preview, not saved</span> : <span className="text-xs text-slate-500">{shown.lines.length} lines</span>}
    >
      {costTypes.length > 0 ? (
        <div className="px-5 py-3 border-b border-slate-200 bg-slate-50/60 flex flex-wrap gap-3 items-center text-xs">
          <span className="text-slate-500">What if the allocation were:</span>
          {costTypes.map((t) => (
            <label key={t} className="flex items-center gap-1.5">
              <span className="text-slate-600">{COST_TYPE_LABEL[t]}</span>
              <select
                value={overrides[t] ?? ""}
                onChange={(e) => setOverride(t, e.target.value)}
                className={`${input} w-auto py-1 text-xs`}
              >
                <option value="">as recorded</option>
                {USER_METHODS.map((m) => <option key={m} value={m}>{METHOD_LABEL[m]}</option>)}
              </select>
            </label>
          ))}
          {pending ? <span className="text-slate-400">recomputing…</span> : null}
          {isPreview ? <button type="button" onClick={() => { setOverrides({}); setPreview(null); }} className="text-blue-600 hover:underline">reset</button> : null}
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className={th}>Line</th>
              {poId ? <th className={th}>Container</th> : null}
              <th className={thRight}>Qty</th>
              <th className={thRight}>FOB</th>
              <th className={thRight}>Landed</th>
              <th className={thRight}>Unit cost</th>
              {Object.keys(shown.by_cost_type).map((t) => <th key={t} className={`${thRight} text-blue-700/80`}>{COST_TYPE_LABEL[t as CostType] ?? t}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {shown.lines.length === 0 ? (
              <tr><td colSpan={8} className="px-5 py-8 text-center text-sm text-slate-500">No purchase-order line loaded. Add loads first.</td></tr>
            ) : (
              shown.lines.map((ln) => (
                <tr key={ln.load_id} className="hover:bg-slate-50">
                  <td className={td}>
                    <div className="font-medium">{ln.po_number} <span className="text-slate-500 font-normal">#{ln.line_no}</span></div>
                    <div className="text-xs text-slate-500">{[ln.sku, ln.description].filter(Boolean).join(" · ") || "—"}</div>
                  </td>
                  {poId ? <td className={`${td} font-mono text-xs text-slate-600`}>{ln.container_number}</td> : null}
                  <td className={tdRight}>{qty(ln.quantity)}</td>
                  <td className={`${tdRight} text-slate-600`}><Money amount={ln.fob} currency={cur} /></td>
                  <td className={`${tdRight} font-semibold`}><Money amount={ln.landed} currency={cur} /></td>
                  <td className={`${tdRight} font-semibold text-emerald-700`}>{unitCost(ln.unit_landed_cost, cur)}</td>
                  {Object.keys(shown.by_cost_type).map((t) => (
                    <td key={t} className={`${tdRight} text-blue-700`}>{ln.by_cost_type[t] ? <Money amount={ln.by_cost_type[t]} currency={cur} /> : <span className="text-slate-300">—</span>}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
          {shown.lines.length > 0 ? (
            <tfoot className="bg-slate-50 text-sm font-medium">
              <tr>
                <td className={td} colSpan={poId ? 3 : 2}>Total</td>
                <td className={tdRight}><Money amount={shown.totals.fob} currency={cur} /></td>
                <td className={tdRight}><Money amount={shown.totals.landed} currency={cur} /></td>
                <td className={tdRight}></td>
                {Object.keys(shown.by_cost_type).map((t) => <td key={t} className={tdRight}><Money amount={shown.by_cost_type[t]} currency={cur} /></td>)}
              </tr>
            </tfoot>
          ) : null}
        </table>
      </div>
    </Card>
  );
}
