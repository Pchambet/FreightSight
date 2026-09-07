import type { Metadata } from "next";
import Link from "next/link";
import { PackageSearch, Ship } from "lucide-react";
import UploadCSV from "@/components/UploadCSV";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { api, type ContainerResponse } from "@/lib/api/client";

export const metadata: Metadata = { title: "Containers" };

async function getContainers(): Promise<{ containers: ContainerResponse[]; error: string | null }> {
  try {
    const { data, error } = await api.GET("/api/containers");
    if (error || !data) return { containers: [], error: "The API returned an error." };
    return { containers: data, error: null };
  } catch {
    return { containers: [], error: "Cannot reach the API. Is the backend running?" };
  }
}

export default async function Dashboard() {
  const { containers, error } = await getContainers();

  return (
    <main className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-md">
              <Ship className="w-4 h-4 text-white" />
            </div>
            <span className="text-lg font-semibold tracking-tight">
              Freight<span className="text-blue-600">Sight</span>
            </span>
          </div>
          <span className="text-xs font-medium text-slate-500">Pre-alpha</span>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Containers</h1>
          <p className="text-slate-500 mt-1 text-sm">Import purchase orders, attach logistics costs, get landed cost per PO.</p>
        </div>

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-4 py-3">{error}</div>
        ) : null}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <UploadCSV />
          </div>

          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-200 flex justify-between items-center">
                <h2 className="text-sm font-semibold flex items-center gap-2">
                  <PackageSearch className="w-4 h-4 text-slate-500" />
                  Tracked containers
                </h2>
                <span className="text-xs text-slate-500">{containers.length} total</span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-5 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Container</th>
                      <th className="px-5 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Carrier</th>
                      <th className="px-5 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {containers.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-5 py-12 text-center">
                          <div className="flex flex-col items-center text-slate-400">
                            <Ship className="w-10 h-10 mb-3 text-slate-300" />
                            <p className="text-sm font-medium text-slate-600">No containers yet</p>
                            <p className="text-xs mt-1">Import a purchase-order CSV to create the first ones.</p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      containers.map((c) => (
                        <tr key={c.id} className="hover:bg-slate-50">
                          <td className="px-5 py-3 whitespace-nowrap">
                            <Link href={`/container/${c.id}`} className="font-mono font-medium text-blue-600 hover:underline">
                              {c.container_number}
                            </Link>
                          </td>
                          <td className="px-5 py-3 whitespace-nowrap text-slate-600">{c.carrier || "—"}</td>
                          <td className="px-5 py-3 whitespace-nowrap">
                            <StatusBadge status={c.status} />
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
