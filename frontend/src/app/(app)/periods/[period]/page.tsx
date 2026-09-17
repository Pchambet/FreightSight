import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { CheckCircle2, Download, Hourglass, LockKeyhole } from "lucide-react";
import { PageHeader, btnSecondary } from "@/components/layout/AppShell";
import BreakdownBar from "@/components/charts/BreakdownBar";
import { COST_FAMILIES, foldFamilies, type CostFamily } from "@/components/charts/families";
import ApiErrorNotice from "@/components/shared/ApiErrorNotice";
import Breadcrumb from "@/components/shared/Breadcrumb";
import Panel from "@/components/ui/Panel";
import StatTile from "@/components/ui/StatTile";
import PeriodActions from "@/features/periods/PeriodActions";
import { isPeriodKey, periodTitle, signedMoney } from "@/features/periods/format";
import { api } from "@/lib/api/client";
import { dateShort, dateTimeShort, money } from "@/lib/format";

type Params = { params: Promise<{ period: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const [{ period }, locale] = await Promise.all([params, getLocale()]);
  return { title: isPeriodKey(period) ? periodTitle(period, locale) : period };
}

export default async function PeriodPage({ params }: Params) {
  const { period } = await params;
  if (!isPeriodKey(period)) notFound();
  const [t, tf, tt, locale, res, me] = await Promise.all([
    getTranslations("periods"),
    getTranslations("costFamily"),
    getTranslations("domain.costType"),
    getLocale(),
    api.GET("/api/v1/periods/{period}", { params: { path: { period } } }),
    api.GET("/api/v1/me"),
  ]);
  if (res.response.status === 404) notFound();
  const title = periodTitle(period, locale);
  if (res.error || !res.data) {
    return (
      <>
        <Breadcrumb backHref="/periods" backLabel={t("title")} />
        <PageHeader title={title} />
        <ApiErrorNotice error={res.error} retryHref={`/periods/${period}`} />
      </>
    );
  }
  const { summary: s, readiness, drift_lines: lines, base_currency: currency } = res.data;
  const closed = s.status === "closed";
  const role = me.data?.role;
  const fmt = (v: number) => money(v, currency, locale);
  const ratio = s.coefficient === null || s.coefficient === undefined ? "—" : new Intl.NumberFormat(locale === "fr" ? "fr-FR" : "en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(s.coefficient));
  const familyLabels = Object.fromEntries(COST_FAMILIES.map((f) => [f, tf(f)])) as Record<CostFamily, string>;
  const drift = Number(s.drift ?? 0);
  const estimatedTotal = Number(readiness?.estimated_total ?? 0);
  const loose = readiness ? readiness.invoices_to_review + readiness.unallocated_costs + readiness.containers_without_cost : 0;

  return (
    <>
      <Breadcrumb backHref="/periods" backLabel={t("title")} />
      <PageHeader
        title={<span className="flex items-center gap-2.5">{closed ? <LockKeyhole className="w-5 h-5 text-slate-500" aria-hidden /> : null}{title}</span>}
        subtitle={closed ? t("detail.closedSubtitle", { date: dateShort(s.closed_at, locale), by: s.closed_by_name ?? "—" }) : t("detail.openSubtitle", { count: s.containers })}
        actions={<PeriodActions period={period} title={periodTitle(period, locale, true)} status={closed ? "closed" : "open"} canClose={role === "OWNER" || role === "ADMIN"} canReopen={role === "OWNER" || role === "ADMIN"} estimated={estimatedTotal > 0 ? money(estimatedTotal, currency, locale) : null} />}
      />

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 mb-6">
        <StatTile label={closed ? t("detail.frozenLanded") : t("detail.liveLanded")} hint={closed ? t("detail.frozenHint") : undefined} value={money(s.landed, currency, locale)} sub={t("detail.onFob", { fob: money(s.fob, currency, locale) })} />
        <StatTile label={t("detail.coef")} value={ratio} sub={t("detail.containers", { count: s.containers })} />
        {closed ? (
          <StatTile label={t("detail.drift")} hint={t("detail.driftHint")} value={signedMoney(s.drift ?? "0", fmt)} tone={drift !== 0 ? "warning" : "default"} sub={drift === 0 ? t("detail.driftNone") : t("driftContainers", { count: s.drift_containers ?? 0 })} />
        ) : (
          <StatTile label={t("detail.estimated")} hint={t("detail.estimatedHint")} value={money(estimatedTotal, currency, locale)} tone={estimatedTotal > 0 ? "warning" : "default"} sub={estimatedTotal > 0 ? t("detail.estimatedSub", { count: readiness?.containers_with_estimates.length ?? 0 }) : t("detail.estimatedNone")} />
        )}
        {closed ? (
          <StatTile label={t("detail.liveNow")} value={money(Number(s.landed) + drift, currency, locale)} sub={t("detail.liveNowSub")} />
        ) : (
          <StatTile label={t("detail.loose")} value={loose} tone={loose > 0 ? "warning" : "default"} sub={loose > 0 ? t("detail.looseSub") : t("detail.looseNone")} />
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-3 items-start mb-6">
        <Panel title={closed ? t("detail.breakdownFrozen") : t("detail.breakdownLive")} className="xl:col-span-2">
          <BreakdownBar fob={Number(s.fob)} families={foldFamilies(s.by_cost_type as Record<string, string>)} currency={currency} locale={locale} fobLabel={t("detail.fob")} familyLabels={familyLabels} ofFobLabel={t("detail.ofFob")} />
        </Panel>

        {closed ? (
          <Panel title={t("exports.title")} subtitle={t("exports.subtitle")}>
            <div className="flex flex-col gap-2">
              <a href={`/api/exports/period-close?period=${period}&locale=${locale}`} className={btnSecondary}><Download className="w-4 h-4 mr-2" aria-hidden />{t("exports.close")}</a>
              {drift !== 0 || lines.length > 0 ? <a href={`/api/exports/period-drift?period=${period}&locale=${locale}`} className={btnSecondary}><Download className="w-4 h-4 mr-2" aria-hidden />{t("exports.drift")}</a> : null}
            </div>
          </Panel>
        ) : readiness ? (
          <Panel title={t("ready.title")} subtitle={t("ready.subtitle")}>
            <ul className="space-y-2 text-sm">
              {[
                { n: readiness.containers_with_estimates.length, key: "estimates", href: "/reports/variance" },
                { n: readiness.invoices_to_review, key: "invoices", href: "/invoices?filter=review" },
                { n: readiness.unallocated_costs, key: "unallocated", href: "/containers" },
                { n: readiness.containers_without_cost, key: "nocost", href: "/containers?view=nocost" },
              ].map((r) => (
                <li key={r.key} className="flex items-start gap-2.5">
                  {r.n === 0 ? <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-emerald-600" aria-hidden /> : <Hourglass className="w-4 h-4 mt-0.5 shrink-0 text-amber-600" aria-hidden />}
                  <span className="flex-1 text-slate-700">{t(`ready.${r.key}`, { count: r.n })}</span>
                  {r.n > 0 ? <Link href={r.href} className="shrink-0 text-blue-700 hover:underline">{t("ready.see")}</Link> : null}
                </li>
              ))}
            </ul>
          </Panel>
        ) : null}
      </div>

      {!closed && readiness && readiness.containers_with_estimates.length > 0 ? (
        <Panel title={t("estimates.title")} subtitle={t("estimates.subtitle")} className="[&>div:last-child]:p-0">
          <table className="min-w-full text-sm">
            <tbody className="divide-y divide-slate-100 border-t border-slate-200">
              {readiness.containers_with_estimates.map((c) => (
                <tr key={c.container_id} className="hover:bg-slate-50">
                  <td className="px-5 py-2.5"><Link href={`/container/${c.container_id}`} className="font-mono text-blue-700 hover:underline">{c.container_number}</Link></td>
                  <td className="px-5 py-2.5 text-right tabular-nums font-medium text-slate-900">{money(c.estimated, currency, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}

      {closed ? (
        <Panel title={t("driftTable.title")} subtitle={lines.length === 0 ? undefined : t("driftTable.subtitle")} className={lines.length === 0 ? "" : "[&>div:last-child]:p-0"}>
          {lines.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-slate-600"><CheckCircle2 className="w-4 h-4 text-emerald-600" aria-hidden />{t("driftTable.none")}</p>
          ) : (
            <ul className="divide-y divide-slate-100 border-t border-slate-200">
              {lines.map((l) => (
                <li key={l.container_id} className="px-5 py-3.5">
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
                    <Link href={`/container/${l.container_id}`} className="font-mono font-medium text-blue-700 hover:underline">{l.container_number}</Link>
                    <span className="text-slate-600">{t(`driftTable.reason.${l.reason === "left_period" || l.reason === "joined_period" ? l.reason : "costs"}`)}</span>
                    <span className="ml-auto tabular-nums text-slate-500">{money(l.frozen_landed, currency, locale)} → {money(l.live_landed, currency, locale)}</span>
                    <span className="tabular-nums font-semibold text-amber-800">{signedMoney(l.difference, fmt)}</span>
                  </div>
                  {l.costs_changed.length > 0 || l.costs_deleted > 0 ? (
                    <ul className="mt-2 space-y-1 text-xs text-slate-600">
                      {l.costs_changed.map((c) => (
                        <li key={c.cost_id} className="flex flex-wrap gap-x-2">
                          <span className="text-slate-900">{tt.has(c.cost_type) ? tt(c.cost_type) : c.cost_type}</span>
                          <span className="tabular-nums">{money(c.amount_base, currency, locale)}</span>
                          {c.vendor || c.invoice_number ? <span className="text-slate-500">{[c.vendor, c.invoice_number].filter(Boolean).join(" · ")}</span> : null}
                          <span className="text-slate-500">{t("driftTable.changedAt", { when: dateTimeShort(c.changed_at, locale) })}</span>
                        </li>
                      ))}
                      {l.costs_deleted > 0 ? <li className="text-slate-500">{t("driftTable.deleted", { count: l.costs_deleted })}</li> : null}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ) : null}
    </>
  );
}
