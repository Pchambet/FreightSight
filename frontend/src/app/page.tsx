import UploadCSV from "../components/UploadCSV";
import { Ship, PackageSearch, AlertCircle, CheckCircle2 } from "lucide-react";
import Link from "next/link";

// Note: Server Component fetching from the local API
async function getContainers() {
  try {
    const res = await fetch("http://127.0.0.1:8001/api/containers", { cache: "no-store" });
    if (!res.ok) {
      return [];
    }
    return res.json();
  } catch (e) {
    console.error("Erreur de connexion au backend:", e);
    return [];
  }
}

export default async function Dashboard() {
  const containers = await getContainers();

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-2">
              <div className="bg-blue-600 p-2 rounded-lg">
                <Ship className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                Freight<span className="text-blue-600">Sight</span>
              </h1>
            </div>
            <div className="flex items-center gap-4">
              <span className="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700 ring-1 ring-inset ring-blue-700/10">
                MVP Version
              </span>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">Control Tower</h2>
            <p className="text-slate-500 mt-1 text-sm">Monitor your shipments, landed costs, and logistics status.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          <div className="lg:col-span-1">
            <UploadCSV />
          </div>

          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col h-full">
              <div className="px-6 py-5 border-b border-slate-200 bg-white flex justify-between items-center">
                <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <PackageSearch className="w-4 h-4 text-slate-500" />
                  Active Containers
                </h3>
                <span className="text-xs font-medium text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full">
                  {containers.length} Total
                </span>
              </div>
              <div className="p-0 overflow-x-auto flex-1">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50/50">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Container No.</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Carrier</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">API Status</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-200">
                    {containers.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-6 py-12 text-center">
                          <div className="flex flex-col items-center justify-center text-slate-400">
                            <Ship className="w-12 h-12 mb-3 text-slate-300" />
                            <p className="text-sm font-medium text-slate-600">No containers tracked</p>
                            <p className="text-xs mt-1">Upload a PO spreadsheet to start tracking.</p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      containers.map((c: any) => (
                        <tr key={c.id} className="hover:bg-slate-50/80 transition-colors group">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <Link href={`/container/${c.id}`} className="text-sm font-semibold text-blue-600 group-hover:text-blue-700 group-hover:underline">
                              {c.container_number}
                            </Link>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-600 font-medium">
                            {c.carrier || "-"}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`px-2.5 py-1 inline-flex items-center gap-1.5 text-xs font-medium rounded-md
                              ${c.status === "COMPLETED" ? "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20" : 
                                c.status === "ERROR" ? "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/10" : 
                                "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20"}`}>
                              {c.status === "COMPLETED" ? <CheckCircle2 className="w-3.5 h-3.5" /> : 
                               c.status === "ERROR" ? <AlertCircle className="w-3.5 h-3.5" /> : 
                               <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />}
                              {c.status}
                            </span>
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
