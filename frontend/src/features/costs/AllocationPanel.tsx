"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Card, input, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { previewAllocation } from "@/features/actions";
import type { LandedCostReport } from "@/lib/api/client";
import { USER_METHODS, type CostType } from "@/lib/domain";
import { qty, unitCost } from "@/lib/format";

/**
 * Breakdown per PO line with a live "what if" switch: change the method per cost type and the
 * unit landed cost recomputes through the backend preview endpoint. Nothing is persisted here.
 */
export default function AllocationPanel({ containerId, poId, report }: { containerId?: string; poId?: string; report: LandedCostReport }) {
  const tr = useTranslations("allocation");
  const costTypeLabel = useTranslations("domain.costType");
  const methodLabel = useTranslations("domain.method");
  const locale = useLocale();
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
      title={tr("title")}
      right={isPreview ? <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded">{tr("preview")}</span> : <span className="text-xs text-slate-500">{tr("lineCount", { count: shown.lines.length })}</span>}
    >
      {costTypes.length > 0 ? (
        <div className="px-5 py-3 border-b border-slate-200 bg-slate-50/60 flex flex-wrap gap-3 items-center text-xs">
          <span className="text-slate-500">{tr("whatIf")}</span>
          {costTypes.map((ct) => (
            <label key={ct} className="flex items-center gap-1.5">
              <span className="text-slate-600">{costTypeLabel(ct)}</span>
              <select
                value={overrides[ct] ?? ""}
                onChange={(e) => setOverride(ct, e.target.value)}
                className={`${input} w-auto py-1 text-xs`}
              >
                <option value="">{tr("asRecorded")}</option>
                {USER_METHODS.map((m) => <option key={m} value={m}>{methodLabel(m)}</option>)}
              </select>
            </label>
          ))}
          {pending ? <span className="text-slate-400">{tr("recomputing")}</span> : null}
          {isPreview ? <button type="button" onClick={() => { setOverrides({}); setPreview(null); }} className="text-blue-600 hover:underline">{tr("reset")}</button> : null}
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className={th}>{tr("th.line")}</th>
              {poId ? <th className={th}>{tr("th.container")}</th> : null}
              <th className={thRight}>{tr("th.quantity")}</th>
              <th className={thRight}>{tr("th.fob")}</th>
              <th className={thRight}>{tr("th.landed")}</th>
              <th className={thRight}>{tr("th.unitCost")}</th>
              {Object.keys(shown.by_cost_type).map((ct) => <th key={ct} className={`${thRight} text-blue-700/80`}>{costTypeLabel(ct as CostType)}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {shown.lines.length === 0 ? (
              <tr><td colSpan={8} className="px-5 py-8 text-center text-sm text-slate-500">{tr("empty")}</td></tr>
            ) : (
              shown.lines.map((ln) => (
                <tr key={ln.load_id} className="hover:bg-slate-50">
                  <td className={td}>
                    <div className="font-medium">{ln.po_number} <span className="text-slate-500 font-normal">#{ln.line_no}</span></div>
                    <div className="text-xs text-slate-500">{[ln.sku, ln.description].filter(Boolean).join(" · ") || "—"}</div>
                  </td>
                  {poId ? <td className={`${td} font-mono text-xs text-slate-600`}>{ln.container_number}</td> : null}
                  <td className={tdRight}>{qty(ln.quantity, locale)}</td>
                  <td className={`${tdRight} text-slate-600`}><Money amount={ln.fob} currency={cur} /></td>
                  <td className={`${tdRight} font-semibold`}><Money amount={ln.landed} currency={cur} /></td>
                  <td className={`${tdRight} font-semibold text-emerald-700`}>{unitCost(ln.unit_landed_cost, cur, locale)}</td>
                  {Object.keys(shown.by_cost_type).map((ct) => (
                    <td key={ct} className={`${tdRight} text-blue-700`}>{ln.by_cost_type[ct] ? <Money amount={ln.by_cost_type[ct]} currency={cur} /> : <span className="text-slate-300">—</span>}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
          {shown.lines.length > 0 ? (
            <tfoot className="bg-slate-50 text-sm font-medium">
              <tr>
                <td className={td} colSpan={poId ? 3 : 2}>{tr("total")}</td>
                <td className={tdRight}><Money amount={shown.totals.fob} currency={cur} /></td>
                <td className={tdRight}><Money amount={shown.totals.landed} currency={cur} /></td>
                <td className={tdRight}></td>
                {Object.keys(shown.by_cost_type).map((ct) => <td key={ct} className={tdRight}><Money amount={shown.by_cost_type[ct]} currency={cur} /></td>)}
              </tr>
            </tfoot>
          ) : null}
        </table>
      </div>
    </Card>
  );
}
