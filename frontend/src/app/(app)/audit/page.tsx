import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Card, PageHeader } from "@/components/layout/AppShell";
import { AuditEntries } from "@/features/audit/AuditTrail";
import { api } from "@/lib/api/client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("audit");
  return { title: t("title") };
}

const ACTIONS = ["cost.created", "cost.updated", "cost.deleted", "invoice.confirmed", "invoice.rejected", "container.loads_replaced", "container.tracking_event_added", "organization.updated"];

export default async function AuditPage({ searchParams }: { searchParams: Promise<{ entity_type?: string; entity_id?: string; action?: string; cursor?: string }> }) {
  const [sp, t, actionLabel] = await Promise.all([searchParams, getTranslations("audit"), getTranslations("domain.auditAction")]);
  const query = { entity_type: sp.entity_type, entity_id: sp.entity_id, action: sp.action, cursor: sp.cursor, limit: 50 };
  const res = await api.GET("/api/v1/audit-log", { params: { query } });
  const entries = res.data?.entries ?? [];
  const next = res.data?.next_cursor ?? null;
  const link = (patch: Record<string, string | undefined>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries({ ...sp, ...patch })) if (v) q.set(k, v);
    return `/audit${q.toString() ? `?${q}` : ""}`;
  };

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="flex flex-wrap gap-1 text-sm mb-3">
        <Link href={link({ action: undefined, cursor: undefined })} className={`px-3 py-1.5 rounded-md ${!sp.action ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{t("filterAll")}</Link>
        {ACTIONS.map((a) => (
          <Link key={a} href={link({ action: a, cursor: undefined })} className={`px-3 py-1.5 rounded-md ${sp.action === a ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{actionLabel(a.replace(".", "_"))}</Link>
        ))}
      </div>
      <Card>
        <AuditEntries entries={entries} />
        {next ? <div className="px-5 py-3 border-t border-slate-200"><Link href={link({ cursor: next })} className="text-sm text-blue-600 hover:underline">{t("next")}</Link></div> : null}
      </Card>
    </>
  );
}
