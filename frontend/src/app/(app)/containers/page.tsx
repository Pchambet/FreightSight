import type { Metadata } from "next";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { AlertTriangle, ArrowRight } from "lucide-react";
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

const CLOSED = ["DELIVERED", "GATE_IN_EMPTY_RETURN"];
const RISKY = ["MEDIUM", "HIGH", "INCURRING"];

/** Money strings from the API are summed as integers of cents to stay exact. */
function sumCents(values: string[]): string {
  const cents = values.reduce((acc, v) => acc + Math.round(Number(v) * 100), 0);
  return (cents / 100).toFixed(2);
}

type Todo = { container: ContainerSummary; kind: "lfd" | "lfdOver" | "noLoads" | "noCost"; date?: string | null };

function buildTodos(containers: ContainerSummary[]): Todo[] {
  const todos: Todo[] = [];
  for (const c of containers.filter((x) => !CLOSED.includes(x.milestone))) {
    const days = daysUntil(c.last_free_day);
    if (days !== null && days < 0) todos.push({ container: c, kind: "lfdOver", date: c.last_free_day });
    else if (days !== null && days <= 7) todos.push({ container: c, kind: "lfd", date: c.last_free_day });
    if (c.load_count === 0) todos.push({ container: c, kind: "noLoads" });
    else if (!c.cost_types_present?.length) todos.push({ container: c, kind: "noCost" });
  }
  const order = { lfdOver: 0, lfd: 1, noLoads: 2, noCost: 3 };
  return todos.sort((a, b) => order[a.kind] - order[b.kind] || (a.date ?? "").localeCompare(b.date ?? ""));
}

export default async function ContainersPage() {
  const [{ containers, currency, error }, t, tc, costType, locale] = await Promise.all([
    load(),
    getTranslations("containers"),
    getTranslations("common"),
    getTranslations("domain.costType"),
    getLocale(),
  ]);
  const active = containers.filter((c) => !CLOSED.includes(c.milestone));
  const atRisk = active.filter((c) => RISKY.includes(c.dnd_risk));
  const noCost = active.filter((c) => c.load_count > 0 && !c.cost_types_present?.length);
  const nextLfd = atRisk.map((c) => c.last_free_day).filter((d): d is string => !!d).sort()[0] ?? null;
  const todos = buildTodos(containers);

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle", { total: containers.length, active: active.length, atRisk: atRisk.length })}
        actions={<NewContainerForm />}
      />
      {error ? <div className="rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-4 py-3 mb-6">{error === "api" ? tc("apiError") : tc("apiUnreachable")}</div> : null}

      {containers.length > 0 ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
            <Kpi label={t("kpi.fobActive")} hint={t("kpi.activeCount", { count: active.length })}>
              <Money amount={sumCents(active.map((c) => c.fob_base))} currency={currency} />
            </Kpi>
            <Kpi label={t("kpi.allocated")} hint={t("kpi.ofActive", { count: active.length })}>
              <Money amount={sumCents(active.map((c) => c.allocated_base))} currency={currency} className="text-blue-700" />
            </Kpi>
            <Kpi label={t("kpi.atRisk")} hint={nextLfd ? t("kpi.nextLfd", { date: dateShort(nextLfd, locale) }) : t("kpi.noneAtRisk")} tone={atRisk.length ? "warn" : undefined}>
              {atRisk.length}
            </Kpi>
            <Kpi label={t("kpi.noCost")} hint={t("kpi.ofActive", { count: active.length })} tone={noCost.length ? "warn" : undefined}>
              {noCost.length}
            </Kpi>
          </div>

          <Card title={t("todo.title")} className="mb-6">
            {todos.length === 0 ? (
              <p className="px-5 py-4 text-sm text-slate-500">{t("todo.empty")}</p>
            ) : (
              <ul className="divide-y divide-slate-200 text-sm">
                {todos.map((x) => (
                  <li key={`${x.container.id}-${x.kind}`} className="px-5 py-2.5 flex items-center gap-3">
                    <AlertTriangle className={`w-4 h-4 shrink-0 ${x.kind === "lfdOver" || x.kind === "lfd" ? "text-amber-600" : "text-slate-400"}`} />
                    <span className="font-mono font-medium">{x.container.container_number}</span>
                    <span className="text-slate-600">
                      {x.kind === "lfd" || x.kind === "lfdOver" ? t(`todo.${x.kind}`, { date: dateShort(x.date, locale) }) : t(`todo.${x.kind}`)}
                    </span>
                    <Link href={`/container/${x.container.id}`} className="ml-auto inline-flex items-center gap-1 text-blue-600 hover:underline whitespace-nowrap">
                      {t("todo.open")} <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      ) : null}

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
                  <td colSpan={9} className="px-5 py-10">
                    <div className="max-w-3xl mx-auto">
                      <p className="text-sm font-semibold text-slate-800 text-center">{t("steps.title")}</p>
                      <ol className="mt-5 grid gap-4 sm:grid-cols-3 text-sm">
                        {(["one", "two", "three"] as const).map((k, i) => (
                          <li key={k} className="rounded-lg border border-slate-200 p-4">
                            <div className="w-6 h-6 rounded-full bg-slate-900 text-white text-xs font-semibold flex items-center justify-center">{i + 1}</div>
                            <div className="mt-3 font-medium text-slate-800">
                              {k === "one" ? <Link href="/imports/new" className="text-blue-600 hover:underline">{t("steps.one")}</Link> : t(`steps.${k}`)}
                            </div>
                            <p className="mt-1 text-xs text-slate-500 leading-relaxed">{t(`steps.${k}Hint`)}</p>
                          </li>
                        ))}
                      </ol>
                      <div className="mt-6 flex flex-col items-center gap-2 text-center">
                        <span className="text-xs uppercase tracking-wider text-slate-400">{t("steps.or")}</span>
                        <LoadSampleDataButton />
                        <p className="text-xs text-slate-400">{t("empty.sampleHint")}</p>
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

function Kpi({ label, hint, tone, children }: { label: string; hint?: string; tone?: "warn"; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 px-5 py-4">
      <div className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "warn" ? "text-amber-700" : ""}`}>{children}</div>
      {hint ? <div className="text-xs text-slate-400 mt-0.5">{hint}</div> : null}
    </div>
  );
}
