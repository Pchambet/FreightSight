import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AlertTriangle, ArrowLeft, ChevronRight } from "lucide-react";
import { Card, PageHeader, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import AddCostForm from "@/features/costs/AddCostForm";
import AllocationPanel from "@/features/costs/AllocationPanel";
import CostLedger from "@/features/costs/CostLedger";
import { api } from "@/lib/api/client";
import { qty } from "@/lib/format";

type Params = { params: Promise<{ id: string }> };

async function load(id: string) {
  const po = await api.GET("/api/v1/purchase-orders/{po_id}", { params: { path: { po_id: id } } });
  if (po.response.status === 404 || po.response.status === 422) return null;
  if (po.error || !po.data) throw new Error("The API returned an error.");
  const rep = await api.GET("/api/v1/landed-costs/purchase-orders/{po_id}", { params: { path: { po_id: id } } });
  if (rep.error || !rep.data) throw new Error("The API returned an error.");
  return { po: po.data, report: rep.data };
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const data = await load(id).catch(() => null);
  return { title: data ? data.po.po_number : "Purchase order" };
}

export default async function PurchaseOrderPage({ params }: Params) {
  const { id } = await params;
  const data = await load(id);
  if (!data) notFound();
  const { po, report } = data;
  const cur = report.base_currency;
  const revalidate = `/purchase-orders/${po.id}`;

  return (
    <>
      <div className="flex items-center text-sm text-slate-500 mb-4">
        <Link href="/purchase-orders" className="hover:text-slate-900 flex items-center gap-1.5"><ArrowLeft className="w-4 h-4" />Purchase orders</Link>
        <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
        <span className="text-slate-900">{po.po_number}</span>
      </div>
      <PageHeader
        title={po.po_number}
        subtitle={<span>{po.supplier_name ?? "No supplier"} · {po.currency}{po.currency !== cur ? ` @ ${po.fx_rate} ${cur}` : ""}{po.order_date ? ` · ordered ${po.order_date}` : ""}{po.incoterm ? ` · ${po.incoterm}` : ""}</span>}
      />

      {report.warnings.length > 0 ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 text-amber-800 text-sm px-4 py-3 space-y-1 mb-6">
          {report.warnings.map((w) => (
            <div key={w.cost_id} className="flex gap-2"><AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /><span><span className="font-mono text-xs mr-2">{w.code}</span>{w.message}</span></div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-1 space-y-6">
          <Card title="Lines">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50"><tr><th className={th}>#</th><th className={th}>SKU</th><th className={thRight}>Qty</th><th className={thRight}>Unit price</th><th className={thRight}>kg</th><th className={thRight}>CBM</th><th className={thRight}>Duty</th></tr></thead>
                <tbody className="divide-y divide-slate-200">
                  {po.lines.map((l) => (
                    <tr key={l.id}>
                      <td className={td}>{l.line_no}</td>
                      <td className={td}><div>{l.sku ?? "—"}</div><div className="text-xs text-slate-500">{l.description}</div></td>
                      <td className={tdRight}>{qty(l.quantity)}</td>
                      <td className={tdRight}>{qty(l.unit_price)}</td>
                      <td className={`${tdRight} text-slate-500`}>{l.unit_weight_kg ? qty(l.unit_weight_kg) : "—"}</td>
                      <td className={`${tdRight} text-slate-500`}>{l.unit_volume_cbm ? qty(l.unit_volume_cbm) : "—"}</td>
                      <td className={`${tdRight} text-slate-500`}>{l.duty_rate ? `${(Number(l.duty_rate) * 100).toFixed(2)} %` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="Add a cost on this order">
            <AddCostForm scope="PO" targetId={po.id} currency={cur} revalidate={revalidate} />
          </Card>
        </div>
        <div className="xl:col-span-2 space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {(["fob", "allocated", "vat", "landed"] as const).map((k) => (
              <div key={k} className="bg-white rounded-lg border border-slate-200 px-4 py-3">
                <div className="text-xs text-slate-500 uppercase tracking-wider">{k === "vat" ? "Import VAT" : k === "fob" ? "FOB" : k}</div>
                <div className="text-lg font-semibold tabular-nums mt-1"><Money amount={report.totals[k]} currency={cur} /></div>
              </div>
            ))}
          </div>
          <AllocationPanel key={report.costs.map((c) => c.id).join(",")} poId={po.id} report={report} />
          <CostLedger report={report} currency={cur} revalidate={revalidate} />
        </div>
      </div>
    </>
  );
}
