import type { Metadata } from "next";
import Link from "next/link";
import { Ship } from "lucide-react";
import { Card, PageHeader, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { MilestoneBadge, RiskBadge } from "@/components/shared/Badges";
import { Money } from "@/components/shared/Money";
import LoadSampleDataButton from "@/features/containers/LoadSampleDataButton";
import NewContainerForm from "@/features/containers/NewContainerForm";
import { api, type ContainerSummary } from "@/lib/api/client";
import { COST_TYPE_LABEL } from "@/lib/domain";
import { dateShort, daysUntil } from "@/lib/format";

export const metadata: Metadata = { title: "Containers" };

async function load(): Promise<{ containers: ContainerSummary[]; currency: string; error: string | null }> {
  try {
    const [c, o] = await Promise.all([api.GET("/api/v1/containers"), api.GET("/api/v1/organization")]);
    if (c.error || !c.data) return { containers: [], currency: "EUR", error: "The API returned an error." };
    return { containers: c.data, currency: o.data?.base_currency ?? "EUR", error: null };
  } catch {
    return { containers: [], currency: "EUR", error: "Cannot reach the API. Is the backend running?" };
  }
}

export default async function ContainersPage() {
  const { containers, currency, error } = await load();
  const inTransit = containers.filter((c) => !["DELIVERED", "GATE_IN_EMPTY_RETURN"].includes(c.milestone)).length;
  const atRisk = containers.filter((c) => ["MEDIUM", "HIGH", "INCURRING"].includes(c.dnd_risk)).length;

  return (
    <>
      <PageHeader
        title="Containers"
        subtitle={`${containers.length} tracked · ${inTransit} active · ${atRisk} at demurrage risk`}
        actions={<NewContainerForm />}
      />
      {error ? <div className="rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-4 py-3 mb-6">{error}</div> : null}

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className={th}>Container</th>
                <th className={th}>Shipment</th>
                <th className={th}>Milestone</th>
                <th className={th}>Last free day</th>
                <th className={th}>Risk</th>
                <th className={th}>Purchase orders</th>
                <th className={thRight}>FOB</th>
                <th className={thRight}>Allocated</th>
                <th className={th}>Costs recorded</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {containers.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-5 py-14 text-center">
                    <div className="flex flex-col items-center text-slate-400">
                      <Ship className="w-10 h-10 mb-3 text-slate-300" />
                      <p className="text-sm font-medium text-slate-600">No containers yet</p>
                      <p className="text-xs mt-1">
                        <Link href="/imports/new" className="text-blue-600 hover:underline">Import purchase orders</Link> or add a container above.
                      </p>
                      <div className="mt-5">
                        <LoadSampleDataButton />
                        <p className="text-xs mt-2 text-slate-400">One shipment, two containers and three cost invoices, to try the allocation.</p>
                      </div>
                    </div>
                  </td>
                </tr>
              ) : (
                containers.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <td className={td}>
                      <Link href={`/container/${c.id}`} className="font-mono font-medium text-blue-600 hover:underline">{c.container_number}</Link>
                    </td>
                    <td className={`${td} text-slate-600`}>{c.shipment_reference ?? "—"}</td>
                    <td className={td}><MilestoneBadge milestone={c.milestone} /></td>
                    <td className={`${td} text-slate-600`}>{dateShort(c.last_free_day)}</td>
                    <td className={td}><RiskBadge risk={c.dnd_risk} days={daysUntil(c.last_free_day)} /></td>
                    <td className={`${td} text-slate-600`}>{c.po_numbers?.length ? c.po_numbers.join(", ") : <span className="text-slate-400">none</span>}</td>
                    <td className={tdRight}><Money amount={c.fob_base} currency={currency} /></td>
                    <td className={tdRight}><Money amount={c.allocated_base} currency={currency} className="text-blue-700" /></td>
                    <td className={`${td} text-xs text-slate-500`}>
                      {c.cost_types_present?.length ? c.cost_types_present.map((t) => COST_TYPE_LABEL[t]).join(", ") : <span className="text-slate-400">none</span>}
                    </td>
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
