"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Loader2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { btnSecondary } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { applyEstimates } from "@/features/actions";
import type { LandedCostReport } from "@/lib/api/client";

/** Estimated vs actual strip: the variance is signed (positive = paid more than planned) and the gauge counts cost types, not euros. */
export default function EstimatePanel({ report, currency, containerId }: { report: LandedCostReport; currency: string; containerId?: string }) {
  const t = useTranslations("estimates");
  const typeLabel = useTranslations("domain.costType");
  const [pending, start] = useTransition();
  const router = useRouter();
  const detail = Object.entries(report.by_cost_type_detail ?? {});
  const expected = detail.filter(([, v]) => Number(v.estimated) > 0 || Number(v.actual) > 0);
  const invoiced = expected.filter(([, v]) => Number(v.actual) > 0);
  const variance = Number(report.totals.variance ?? "0");
  const missing = expected.filter(([, v]) => Number(v.actual) === 0).map(([k]) => typeLabel(k as never));

  const apply = () =>
    start(async () => {
      if (!containerId) return;
      const r = await applyEstimates(containerId);
      if (!r.ok) return void toast.error(r.error);
      const skipped = Object.entries(r.data.skipped);
      if (r.data.created === 0 && skipped.length === 0) toast.info(t("noRateCards"));
      else if (skipped.length) toast.warning(`${t("appliedSkipped", { created: r.data.created, skipped: skipped.length })} · ${skipped.map(([k, v]) => `${k}: ${v}`).join(" · ")}`, { duration: 8000 });
      else toast.success(t("applied", { created: r.data.created }));
      router.refresh();
    });

  return (
    <div className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex flex-wrap items-center gap-x-8 gap-y-2">
      <div>
        <div className="text-xs text-slate-500 uppercase tracking-wider">{t("estimated")}</div>
        <div className="text-base font-semibold tabular-nums text-violet-800"><Money amount={report.totals.estimated ?? "0.00"} currency={currency} /></div>
      </div>
      <div>
        <div className="text-xs text-slate-500 uppercase tracking-wider">{t("actual")}</div>
        <div className="text-base font-semibold tabular-nums"><Money amount={report.totals.actual ?? "0.00"} currency={currency} /></div>
      </div>
      <div title={t("varianceHint")}>
        <div className="text-xs text-slate-500 uppercase tracking-wider">{t("variance")}</div>
        <div className={`text-base font-semibold tabular-nums ${variance > 0 ? "text-red-700" : variance < 0 ? "text-emerald-700" : "text-slate-700"}`}>{variance > 0 ? "+" : ""}<Money amount={report.totals.variance ?? "0.00"} currency={currency} /></div>
      </div>
      <div className="min-w-[12rem]">
        <div className="text-xs text-slate-500 uppercase tracking-wider">{t("completeness")}</div>
        {expected.length === 0 ? (
          <div className="text-sm text-slate-400">{t("noExpected")}</div>
        ) : (
          <div className="flex items-center gap-2">
            <div className="h-2 w-28 rounded bg-slate-200 overflow-hidden"><div className="h-2 bg-emerald-500" style={{ width: `${Math.round((invoiced.length / expected.length) * 100)}%` }} /></div>
            <span className="text-sm tabular-nums text-slate-700" title={missing.length ? missing.join(", ") : undefined}>{t("completenessDetail", { actual: invoiced.length, expected: expected.length })}</span>
          </div>
        )}
      </div>
      {containerId ? (
        <button type="button" onClick={apply} disabled={pending} className={`${btnSecondary} ml-auto`}>
          {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Wand2 className="w-4 h-4 mr-2" />}{t("apply")}
        </button>
      ) : null}
    </div>
  );
}
