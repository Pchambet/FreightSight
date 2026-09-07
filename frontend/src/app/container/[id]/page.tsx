import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AlertTriangle, ArrowLeft, Box, ChevronRight, DollarSign, FileText, Sparkles } from "lucide-react";
import AddCostForm from "./AddCostForm";
import StatusSelect from "./StatusSelect";
import { Money } from "@/components/shared/Money";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { api, type LandedCostResponse } from "@/lib/api/client";
import { ALLOCATION_METHOD_LABEL, COST_TYPE_LABEL } from "@/lib/domain";
import { pct } from "@/lib/format";

type Params = { params: Promise<{ id: string }> };

async function getLandedCosts(id: string): Promise<LandedCostResponse | null> {
  const { data, error, response } = await api.GET("/api/containers/{container_id}/landed-costs", {
    params: { path: { container_id: id } },
  });
  if (response.status === 404 || response.status === 422) return null;
  if (error || !data) throw new Error("The API returned an error.");
  return data;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const data = await getLandedCosts(id).catch(() => null);
  return { title: data ? data.container.container_number : "Container" };
}

export default async function ContainerPage({ params }: Params) {
  const { id } = await params;
  const data = await getLandedCosts(id);
  if (!data) notFound();

  const cur = data.base_currency;

  return (
    <main className="min-h-screen pb-12">
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center text-sm text-slate-500">
          <Link href="/" className="hover:text-slate-900 flex items-center gap-1.5">
            <ArrowLeft className="w-4 h-4" />
            Containers
          </Link>
          <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
          <span className="text-slate-900 font-mono">{data.container.container_number}</span>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold flex items-center gap-3 font-mono">
              <Box className="w-6 h-6 text-blue-600" />
              {data.container.container_number}
            </h1>
            <div className="mt-2 flex items-center gap-3">
              <StatusBadge status={data.container.status} />
              <span className="text-sm text-slate-500">{data.container.carrier || "Carrier unknown"}</span>
            </div>
          </div>
          <StatusSelect containerId={data.container.id} status={data.container.status} />
        </header>

        {data.warnings.length > 0 ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 text-amber-800 text-sm px-4 py-3 space-y-1">
            {data.warnings.map((w) => (
              <div key={w.code} className="flex gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <span><span className="font-mono text-xs mr-2">{w.code}</span>{w.message}</span>
              </div>
            ))}
          </div>
        ) : null}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-200 flex items-center gap-2">
                <FileText className="w-4 h-4 text-slate-500" />
                <h3 className="text-sm font-semibold">Logistics costs</h3>
              </div>
              <div className="p-5">
                {data.raw_costs.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-4">No costs recorded yet.</p>
                ) : (
                  <ul className="space-y-3 text-sm">
                    {data.raw_costs.map((c) => (
                      <li key={c.id} className="flex justify-between items-center">
                        <span className="text-slate-600">{COST_TYPE_LABEL[c.cost_type]}</span>
                        <Money amount={c.amount} currency={c.currency} className="font-medium" />
                      </li>
                    ))}
                    <li className="flex justify-between items-center font-semibold border-t border-slate-200 pt-3 mt-3">
                      <span>Total</span>
                      <Money amount={data.total_additional_costs} currency={cur} />
                    </li>
                  </ul>
                )}
              </div>
            </div>

            <AddCostForm containerId={data.container.id} currency={cur} />

            <div className="rounded-lg border border-dashed border-slate-300 p-5 text-sm text-slate-500">
              <div className="flex items-center gap-2 font-medium text-slate-700 mb-1">
                <Sparkles className="w-4 h-4" />
                Invoice extraction
              </div>
              Planned for Phase 2: upload a forwarder invoice PDF, review the extracted lines, confirm. Until then, add
              costs manually above.
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-slate-500" />
                  Landed cost per purchase order
                </h3>
                <span className="text-xs text-slate-500">
                  {data.allocation_method ? ALLOCATION_METHOD_LABEL[data.allocation_method] : "No allocation"}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-5 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Purchase order</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">FOB value</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Share</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Allocated costs</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Landed cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {data.breakdown.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-5 py-12 text-center text-sm text-slate-500">
                          No purchase order linked to this container.
                        </td>
                      </tr>
                    ) : (
                      data.breakdown.map((po) => (
                        <tr key={po.po_id} className="hover:bg-slate-50">
                          <td className="px-5 py-3 whitespace-nowrap">
                            <div className="font-medium">{po.po_number}</div>
                            <div className="text-xs text-slate-500">{po.supplier_name || "—"}</div>
                          </td>
                          <td className="px-5 py-3 text-right whitespace-nowrap text-slate-600"><Money amount={po.fob_value} currency={cur} /></td>
                          <td className="px-5 py-3 text-right whitespace-nowrap text-slate-600">{pct(po.allocation_pct)}</td>
                          <td className="px-5 py-3 text-right whitespace-nowrap text-blue-700">+ <Money amount={po.allocated_costs} currency={cur} /></td>
                          <td className="px-5 py-3 text-right whitespace-nowrap font-semibold"><Money amount={po.true_landed_cost} currency={cur} /></td>
                        </tr>
                      ))
                    )}
                  </tbody>
                  {data.breakdown.length > 0 ? (
                    <tfoot className="bg-slate-50 text-sm">
                      <tr>
                        <td className="px-5 py-3 font-medium" colSpan={3}>Allocated / unallocated</td>
                        <td className="px-5 py-3 text-right font-medium"><Money amount={data.total_allocated} currency={cur} /></td>
                        <td className="px-5 py-3 text-right text-slate-500"><Money amount={data.unallocated} currency={cur} /> unallocated</td>
                      </tr>
                    </tfoot>
                  ) : null}
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
