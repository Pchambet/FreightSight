import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { AlertTriangle, ArrowLeft, ChevronRight } from "lucide-react";
import { Card, PageHeader, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import AddCostForm from "@/features/costs/AddCostForm";
import AllocationPanel from "@/features/costs/AllocationPanel";
import EstimatePanel from "@/features/estimates/EstimatePanel";
import CostLedger from "@/features/costs/CostLedger";
import { api } from "@/lib/api/client";
import { dateShort, pct, qty } from "@/lib/format";

type Params = { params: Promise<{ id: string }> };

// Thrown, never rendered: the error boundary shows the translated message.
const API_ERROR = "api_error";

async function load(id: string) {
  const po = await api.GET("/api/v1/purchase-orders/{po_id}", { params: { path: { po_id: id } } });
  if (po.response.status === 404 || po.response.status === 422) return null;
  if (po.error || !po.data) throw new Error(API_ERROR);
  const rep = await api.GET("/api/v1/landed-costs/purchase-orders/{po_id}", { params: { path: { po_id: id } } });
  if (rep.error || !rep.data) throw new Error(API_ERROR);
  return { po: po.data, report: rep.data };
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const data = await load(id).catch(() => null);
  const t = await getTranslations("purchaseOrder");
  return { title: data ? data.po.po_number : t("fallbackTitle") };
}

export default async function PurchaseOrderPage({ params }: Params) {
  const { id } = await params;
  const data = await load(id);
  if (!data) notFound();
  const { po, report } = data;
  const [t, tc, errorCode, locale] = await Promise.all([
    getTranslations("purchaseOrder"),
    getTranslations("common"),
    getTranslations("errors"),
    getLocale(),
  ]);
  const cur = report.base_currency;
  const revalidate = `/purchase-orders/${po.id}`;

  return (
    <>
      <div className="flex items-center text-sm text-slate-500 mb-4">
        <Link href="/purchase-orders" className="hover:text-slate-900 flex items-center gap-1.5"><ArrowLeft className="w-4 h-4" />{t("breadcrumb")}</Link>
        <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
        <span className="text-slate-900">{po.po_number}</span>
      </div>
      <PageHeader
        title={po.po_number}
        subtitle={<span>{po.supplier_name ?? t("noSupplier")} · {po.currency}{po.currency !== cur ? ` @ ${po.fx_rate} ${cur}` : ""}{po.order_date ? ` · ${t("ordered", { date: dateShort(po.order_date, locale) })}` : ""}{po.incoterm ? ` · ${po.incoterm}` : ""}</span>}
      />

      {report.warnings.length > 0 ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 text-amber-800 text-sm px-4 py-3 space-y-1 mb-6">
          {report.warnings.map((w) => (
            <div key={w.cost_id} className="flex gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                {errorCode.has(w.code) ? errorCode(w.code) : w.message}
                {w.load_labels?.length ? <span className="text-amber-700/80"> {w.load_labels.join(", ")}</span> : null}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-1 space-y-6">
          <Card title={t("linesCard")}>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50"><tr><th className={th}>{t("th.lineNo")}</th><th className={th}>{t("th.sku")}</th><th className={thRight}>{t("th.quantity")}</th><th className={thRight}>{t("th.unitPrice")}</th><th className={thRight}>{t("th.weight")}</th><th className={thRight}>{t("th.volume")}</th><th className={thRight}>{t("th.duty")}</th></tr></thead>
                <tbody className="divide-y divide-slate-200">
                  {po.lines.map((l) => (
                    <tr key={l.id}>
                      <td className={td}>{l.line_no}</td>
                      <td className={td}><div>{l.sku ?? tc("empty")}</div><div className="text-xs text-slate-500">{l.description}</div></td>
                      <td className={tdRight}>{qty(l.quantity, locale)}</td>
                      <td className={tdRight}>{qty(l.unit_price, locale)}</td>
                      <td className={`${tdRight} text-slate-500`}>{l.unit_weight_kg ? qty(l.unit_weight_kg, locale) : tc("empty")}</td>
                      <td className={`${tdRight} text-slate-500`}>{l.unit_volume_cbm ? qty(l.unit_volume_cbm, locale) : tc("empty")}</td>
                      <td className={`${tdRight} text-slate-500`}>{l.duty_rate ? pct(Number(l.duty_rate) * 100, locale) : tc("empty")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title={t("addCostCard")}>
            <AddCostForm scope="PO" targetId={po.id} currency={cur} revalidate={revalidate} />
          </Card>
        </div>
        <div className="xl:col-span-2 space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {(["fob", "allocated", "vat", "landed"] as const).map((k) => (
              <div key={k} className="bg-white rounded-lg border border-slate-200 px-4 py-3">
                <div className="text-xs text-slate-500 uppercase tracking-wider">{t(`totals.${k}`)}</div>
                <div className="text-lg font-semibold tabular-nums mt-1"><Money amount={report.totals[k]} currency={cur} /></div>
              </div>
            ))}
          </div>
          <EstimatePanel report={report} currency={cur} />
          <AllocationPanel key={report.costs.map((c) => c.id).join(",")} poId={po.id} report={report} />
          <CostLedger report={report} currency={cur} revalidate={revalidate} />
        </div>
      </div>
    </>
  );
}
