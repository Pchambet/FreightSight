import Link from "next/link";
import AddCostForm from "./AddCostForm";
import AIInvoiceUpload from "./AIInvoiceUpload";
import { ArrowLeft, Box, DollarSign, FileText, ChevronRight } from "lucide-react";

async function getLandedCosts(containerId: string) {
  try {
    const res = await fetch(`http://127.0.0.1:8001/api/containers/${containerId}/landed-costs`, { cache: "no-store" });
    if (!res.ok) {
      return null;
    }
    return res.json();
  } catch (e) {
    console.error("Erreur backend:", e);
    return null;
  }
}

export default async function ContainerLandedCostPage({ params }: { params: Promise<{ id: string }> }) {
  // Extract id correctly for Server Components in Next 15+
  const { id: containerId } = await params;
  const data = await getLandedCosts(containerId);

  if (!data) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-8">
        <div className="bg-white p-8 rounded-xl shadow-sm border border-slate-200 text-center max-w-md w-full">
          <div className="w-12 h-12 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto mb-4">
            <Box className="w-6 h-6" />
          </div>
          <h1 className="text-xl font-semibold text-slate-900 mb-2">Container Not Found</h1>
          <p className="text-slate-500 mb-6 text-sm">We couldn't find the data for this container, or there was an error connecting to the server.</p>
          <Link href="/" className="inline-flex items-center justify-center bg-slate-900 text-white font-medium py-2 px-4 rounded-lg hover:bg-slate-800 transition-colors w-full">
            Return to Dashboard
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 pb-12">
      
      {/* Top Nav Breadcrumb */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center text-sm font-medium text-slate-500">
          <Link href="/" className="hover:text-slate-900 transition-colors flex items-center gap-1.5">
            <ArrowLeft className="w-4 h-4" />
            Dashboard
          </Link>
          <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
          <span className="text-slate-900">Container {data.container_number}</span>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
              <Box className="w-8 h-8 text-blue-600" />
              {data.container_number}
            </h1>
            <p className="text-slate-500 mt-2 text-sm">Landed Costs & PO Breakdown Analysis</p>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          <div className="lg:col-span-1 space-y-6">
            
            <AIInvoiceUpload containerId={containerId} />

            {/* Added Invoices */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
              <div className="px-6 py-5 border-b border-slate-200 bg-white flex items-center gap-2">
                <FileText className="w-5 h-5 text-slate-500" />
                <h3 className="text-base font-semibold text-slate-900">Logistics Invoices</h3>
              </div>
              <div className="p-6">
                {data.raw_costs.length === 0 ? (
                  <div className="text-center py-6">
                    <p className="text-sm text-slate-500 italic">No additional costs recorded yet.</p>
                  </div>
                ) : (
                  <ul className="space-y-4">
                    {data.raw_costs.map((c: any, idx: number) => (
                      <li key={idx} className="flex justify-between items-center text-sm">
                        <span className="font-medium text-slate-600 bg-slate-100 px-2 py-1 rounded-md">{c.type.replace('_', ' ')}</span>
                        <span className="text-slate-900 font-semibold">${c.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                      </li>
                    ))}
                    <li className="flex justify-between items-center text-sm font-bold border-t border-slate-200 pt-4 mt-4">
                      <span className="text-slate-900">Total Additional Costs</span>
                      <span className="text-indigo-600">${data.total_additional_costs.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </li>
                  </ul>
                )}
              </div>
            </div>

            {/* Form */}
            <AddCostForm containerId={containerId} />

          </div>

          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col h-full">
              <div className="px-6 py-5 border-b border-slate-200 bg-white flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-slate-500" />
                <h3 className="text-base font-semibold text-slate-900">
                  Purchase Orders Impact
                </h3>
              </div>
              
              <div className="p-0 overflow-x-auto flex-1">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50/50">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Purchase Order</th>
                      <th className="px-6 py-4 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">FOB Value</th>
                      <th className="px-6 py-4 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Logistics Allocation</th>
                      <th className="px-6 py-4 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">True Landed Cost</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-200">
                    {data.breakdown.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-6 py-12 text-center text-slate-400">
                          <p className="text-sm font-medium text-slate-600">No purchase orders linked to this container.</p>
                        </td>
                      </tr>
                    ) : (
                      data.breakdown.map((po: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="text-sm font-bold text-slate-900">{po.po_number}</div>
                            <div className="text-xs text-slate-500 mt-0.5">{po.supplier_name} <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded ml-1">{po.allocation_pct}%</span></div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-slate-600 font-medium">
                            ${po.fob_value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-indigo-600 font-medium">
                            + ${po.allocated_freight_and_duty.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-bold text-emerald-600 bg-emerald-50/30">
                            ${po.true_landed_cost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          
        </div>
      </div>
    </main>
  );
}
