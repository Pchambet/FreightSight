import type { Metadata } from "next";
import Link from "next/link";
import { Card, PageHeader, btnPrimary, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { api } from "@/lib/api/client";
import { dateShort } from "@/lib/format";

export const metadata: Metadata = { title: "Imports" };

const STATUS_STYLE: Record<string, string> = {
  PARSED: "bg-slate-100 text-slate-700",
  VALIDATED: "bg-blue-50 text-blue-700",
  DONE: "bg-emerald-50 text-emerald-700",
  FAILED: "bg-red-50 text-red-700",
};

export default async function ImportsPage() {
  const { data } = await api.GET("/api/v1/imports");
  const jobs = data ?? [];
  return (
    <>
      <PageHeader title="Imports" subtitle="Purchase orders and container loads from CSV or Excel" actions={<Link href="/imports/new" className={btnPrimary}>New import</Link>} />
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50"><tr><th className={th}>Date</th><th className={th}>File</th><th className={th}>Kind</th><th className={th}>Status</th><th className={thRight}>Rows</th><th className={thRight}>Errors</th><th className={th}>Result</th></tr></thead>
            <tbody className="divide-y divide-slate-200">
              {jobs.length === 0 ? (
                <tr><td colSpan={7} className="px-5 py-14 text-center text-sm text-slate-500">No import yet.</td></tr>
              ) : (
                jobs.map((j) => {
                  const r = j.report as Record<string, number | undefined>;
                  return (
                    <tr key={j.id}>
                      <td className={`${td} text-slate-600`}>{dateShort(j.created_at)}</td>
                      <td className={td}>{j.original_filename ?? "—"}</td>
                      <td className={`${td} text-xs text-slate-600`}>{j.kind === "PURCHASE_ORDERS" ? "PO lines" : "Legacy PO + container"}</td>
                      <td className={td}><span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[j.status]}`}>{j.status}</span></td>
                      <td className={tdRight}>{j.row_count}</td>
                      <td className={`${tdRight} ${j.error_count ? "text-amber-700" : ""}`}>{j.error_count}</td>
                      <td className={`${td} text-xs text-slate-600`}>
                        {j.status === "DONE" ? `${r.purchase_orders_created ?? 0} POs, ${r.lines_created ?? 0} lines, ${r.containers_created ?? 0} containers, ${r.loads_created ?? 0} loads` : j.status === "PARSED" || j.status === "VALIDATED" ? <Link href={`/imports/new?job=${j.id}`} className="text-blue-600 hover:underline">continue</Link> : "—"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
