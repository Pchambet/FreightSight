import type { Metadata } from "next";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { Bell } from "lucide-react";
import { Card, PageHeader } from "@/components/layout/AppShell";
import { MarkAllReadButton, MarkReadButton } from "@/features/alerts/AlertActions";
import { api, type Schemas } from "@/lib/api/client";
import { dateTimeShort } from "@/lib/format";

type Alert = Schemas["AlertResponse"];

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("alerts");
  return { title: t("title") };
}

const SEVERITY_STYLE: Record<Alert["severity"], string> = {
  info: "bg-slate-100 text-slate-700",
  warning: "bg-amber-100 text-amber-800",
  critical: "bg-red-100 text-red-800",
};

export default async function AlertsPage({ searchParams }: { searchParams: Promise<{ all?: string }> }) {
  const [{ all }, t, kind, severity, locale] = await Promise.all([
    searchParams,
    getTranslations("alerts"),
    getTranslations("domain.alertKind"),
    getTranslations("domain.alertSeverity"),
    getLocale(),
  ]);
  const unreadOnly = all !== "1";
  const res = await api.GET("/api/v1/alerts", { params: { query: unreadOnly ? { unread: true } : {} } });
  const alerts: Alert[] = res.data ?? [];
  const unread = alerts.filter((a) => !a.read_at).length;

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle", { unread, total: alerts.length })}
        actions={
          <div className="flex items-center gap-3">
            <Link href={unreadOnly ? "/alerts?all=1" : "/alerts"} className="text-sm text-blue-600 hover:underline">{unreadOnly ? t("showAll") : t("unreadOnly")}</Link>
            {unread > 0 ? <MarkAllReadButton /> : null}
          </div>
        }
      />
      <Card>
        {alerts.length === 0 ? (
          <div className="px-5 py-14 text-center text-slate-400">
            <Bell className="w-10 h-10 mx-auto mb-3 text-slate-300" />
            <p className="text-sm text-slate-600">{t("empty")}</p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-200">
            {alerts.map((a) => (
              <li key={a.id} className={`px-5 py-3.5 flex gap-4 ${a.read_at ? "opacity-60" : ""}`}>
                <span className={`mt-0.5 shrink-0 inline-flex px-2 py-0.5 rounded text-[11px] font-medium uppercase tracking-wider ${SEVERITY_STYLE[a.severity]}`}>{severity(a.severity)}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-900">{a.title}</div>
                  <div className="text-sm text-slate-600">{a.body}</div>
                  <div className="text-xs text-slate-400 mt-1 tabular-nums">{kind(a.kind)} · {dateTimeShort(a.created_at, locale)}</div>
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  {a.container_id ? <Link href={`/container/${a.container_id}`} className="text-xs text-blue-600 hover:underline whitespace-nowrap">{t("openContainer")}</Link> : null}
                  {!a.read_at ? <MarkReadButton alertId={a.id} /> : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
