"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Card, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { deleteCost } from "@/features/actions";
import type { LandedCostReport } from "@/lib/api/client";
import { dateShort } from "@/lib/format";

export default function CostLedger({ report, currency, revalidate }: { report: LandedCostReport; currency: string; revalidate: string }) {
  const t = useTranslations("costs.ledger");
  const tc = useTranslations("common");
  const costTypeLabel = useTranslations("domain.costType");
  const methodLabel = useTranslations("domain.method");
  const scopeLabel = useTranslations("domain.scope");
  const te = useTranslations("estimates");
  const locale = useLocale();
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const remove = (id: string) =>
    startTransition(async () => {
      const result = await deleteCost(id, revalidate);
      if (!result.ok) return void toast.error(result.error);
      toast.success(t("deleted"));
      router.refresh();
    });

  return (
    <Card title={t("title")} right={<span className="text-xs text-slate-500">{t("recorded", { count: report.costs.length })}</span>}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className={th}>{t("th.date")}</th>
              <th className={th}>{t("th.type")}</th>
              <th className={th}>{t("th.scope")}</th>
              <th className={thRight}>{t("th.amount")}</th>
              <th className={thRight}>{t("th.inCurrency", { currency })}</th>
              <th className={th}>{t("th.method")}</th>
              <th className={th}>{t("th.vendor")}</th>
              <th className={th}></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {report.costs.length === 0 ? (
              <tr><td colSpan={8} className="px-5 py-8 text-center text-sm text-slate-500">{t("empty")}</td></tr>
            ) : (
              report.costs.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className={`${td} text-slate-600`}>{dateShort(c.cost_date, locale)}</td>
                  <td className={td}>
                    {costTypeLabel(c.cost_type)}
                    {c.status === "ESTIMATE" ? <span className={`ml-2 inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${c.closed_at ? "bg-slate-100 text-slate-500" : "bg-violet-100 text-violet-800"}`}>{c.closed_at ? te("closed") : te("statusEstimate")}</span> : null}
                    {c.supersedes_cost_id ? <span className="ml-2 text-[10px] text-slate-400 uppercase tracking-wider">↩ {te("statusEstimate").toLowerCase()}</span> : null}
                  </td>
                  <td className={`${td} text-slate-600`}>{scopeLabel(c.scope)}</td>
                  <td className={tdRight}><Money amount={c.amount} currency={c.currency} /></td>
                  <td className={tdRight}>
                    <Money amount={c.amount_base} currency={currency} className="font-medium" />
                    {c.currency !== currency ? <div className="text-xs text-slate-400">@ {c.fx_rate} ({c.fx_source})</div> : null}
                  </td>
                  <td className={`${td} text-slate-600`}>{methodLabel(c.allocation_method)}</td>
                  <td className={`${td} text-slate-600 text-xs`}>{[c.vendor, c.invoice_number].filter(Boolean).join(" · ") || tc("empty")}</td>
                  <td className={td}>
                    <button type="button" disabled={pending} onClick={() => remove(c.id)} className="text-slate-400 hover:text-red-600" aria-label={t("delete")}><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
