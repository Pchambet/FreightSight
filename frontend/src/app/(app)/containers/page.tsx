import type { Metadata } from "next";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { Ship } from "lucide-react";
import { Card, PageHeader, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { MilestoneBadge, RiskBadge } from "@/components/shared/Badges";
import { Money } from "@/components/shared/Money";
import LoadSampleDataButton from "@/features/containers/LoadSampleDataButton";
import NewContainerForm from "@/features/containers/NewContainerForm";
import { api, type ContainerSummary } from "@/lib/api/client";
import { dateShort, daysUntil } from "@/lib/format";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("containers");
  return { title: t("title") };
}

async function load(): Promise<{ containers: ContainerSummary[]; currency: string; error: "api" | "unreachable" | null }> {
  try {
    const [c, o] = await Promise.all([api.GET("/api/v1/containers"), api.GET("/api/v1/organization")]);
    if (c.error || !c.data) return { containers: [], currency: "EUR", error: "api" };
    return { containers: c.data, currency: o.data?.base_currency ?? "EUR", error: null };
  } catch {
    return { containers: [], currency: "EUR", error: "unreachable" };
  }
}

export default async function ContainersPage() {
  const [{ containers, currency, error }, t, tc, costType, locale] = await Promise.all([
    load(),
    getTranslations("containers"),
    getTranslations("common"),
    getTranslations("domain.costType"),
    getLocale(),
  ]);
  const inTransit = containers.filter((c) => !["DELIVERED", "GATE_IN_EMPTY_RETURN"].includes(c.milestone)).length;
  const atRisk = containers.filter((c) => ["MEDIUM", "HIGH", "INCURRING"].includes(c.dnd_risk)).length;

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle", { total: containers.length, active: inTransit, atRisk })}
        actions={<NewContainerForm />}
      />
      {error ? <div className="rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-4 py-3 mb-6">{error === "api" ? tc("apiError") : tc("apiUnreachable")}</div> : null}

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className={th}>{t("th.container")}</th>
                <th className={th}>{t("th.shipment")}</th>
                <th className={th}>{t("th.milestone")}</th>
                <th className={th}>{t("th.lastFreeDay")}</th>
                <th className={th}>{t("th.risk")}</th>
                <th className={th}>{t("th.purchaseOrders")}</th>
                <th className={thRight}>{t("th.fob")}</th>
                <th className={thRight}>{t("th.allocated")}</th>
                <th className={th}>{t("th.costs")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {containers.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-5 py-14 text-center">
                    <div className="flex flex-col items-center text-slate-400">
                      <Ship className="w-10 h-10 mb-3 text-slate-300" />
                      <p className="text-sm font-medium text-slate-600">{t("empty.title")}</p>
                      <p className="text-xs mt-1">
                        <Link href="/imports/new" className="text-blue-600 hover:underline">{t("empty.importLink")}</Link>{" · "}{t("empty.hint")}
                      </p>
                      <div className="mt-5">
                        <LoadSampleDataButton />
                        <p className="text-xs mt-2 text-slate-400">{t("empty.sampleHint")}</p>
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
                    <td className={`${td} text-slate-600`}>{c.shipment_reference ?? tc("empty")}</td>
                    <td className={td}><MilestoneBadge milestone={c.milestone} /></td>
                    <td className={`${td} text-slate-600`}>{dateShort(c.last_free_day, locale)}</td>
                    <td className={td}><RiskBadge risk={c.dnd_risk} days={daysUntil(c.last_free_day)} /></td>
                    <td className={`${td} text-slate-600`}>{c.po_numbers?.length ? c.po_numbers.join(", ") : <span className="text-slate-400">{t("none")}</span>}</td>
                    <td className={tdRight}><Money amount={c.fob_base} currency={currency} /></td>
                    <td className={tdRight}><Money amount={c.allocated_base} currency={currency} className="text-blue-700" /></td>
                    <td className={`${td} text-xs text-slate-500`}>
                      {c.cost_types_present?.length ? c.cost_types_present.map((k) => costType(k)).join(", ") : <span className="text-slate-400">{t("none")}</span>}
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
