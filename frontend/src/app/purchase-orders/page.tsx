import type { Metadata } from "next";
import Link from "next/link";
import { Card, PageHeader, btnSecondary, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { api } from "@/lib/api/client";

export const metadata: Metadata = { title: "Purchase orders" };

export default async function PurchaseOrdersPage() {
  const [p, o] = await Promise.all([api.GET("/api/v1/purchase-orders"), api.GET("/api/v1/organization")]);
  const pos = p.data ?? [];
  const cur = o.data?.base_currency ?? "EUR";
  return (
    <>
      <PageHeader title="Purchase orders" subtitle={`${pos.length} orders`} actions={<Link href="/imports/new" className={btnSecondary}>Import from CSV / Excel</Link>} />
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className={th}>PO</th>
                <th className={th}>Supplier</th>
                <th className={th}>Currency</th>
                <th className={thRight}>Lines</th>
                <th className={thRight}>FOB ({cur})</th>
                <th className={th}>Containers</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {pos.length === 0 ? (
                <tr><td colSpan={6} className="px-5 py-14 text-center text-sm text-slate-500">No purchase order yet. <Link href="/imports/new" className="text-blue-600 hover:underline">Import a file</Link> to get started.</td></tr>
              ) : (
                pos.map((po) => (
                  <tr key={po.id} className="hover:bg-slate-50">
                    <td className={td}><Link href={`/purchase-orders/${po.id}`} className="font-medium text-blue-600 hover:underline">{po.po_number}</Link></td>
                    <td className={`${td} text-slate-600`}>{po.supplier_name ?? "—"}</td>
                    <td className={`${td} font-mono text-xs`}>{po.currency}</td>
                    <td className={tdRight}>{po.line_count}</td>
                    <td className={tdRight}><Money amount={po.fob_base} currency={cur} /></td>
                    <td className={`${td} font-mono text-xs text-slate-600`}>{po.container_numbers.join(", ") || <span className="text-slate-400">not loaded</span>}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
