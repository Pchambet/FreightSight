import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { Card } from "@/components/layout/AppShell";
import { auditDiff, auditEntityRef } from "@/features/audit/format";
import { api, type AuditEntry } from "@/lib/api/client";
import { dateTimeShort, money } from "@/lib/format";

type Json = Record<string, unknown> | null | undefined;

export async function AuditEntries({ entries }: { entries: AuditEntry[] }) {
  const [t, action, locale] = await Promise.all([getTranslations("audit"), getTranslations("domain.auditAction"), getLocale()]);
  const formatters = {
    field: (key: string) => (t.has(`fields.${key}`) ? t(`fields.${key}`) : key),
    invoiceStatus: (code: string) => (t.has(`invoiceStatus.${code}`) ? t(`invoiceStatus.${code}`) : code),
    costCount: (count: number) => t("costCount", { count }),
    money: (amount: string) => money(amount, "EUR", locale),
  };
  const entityLabel = (type: string) => (t.has(`entity.${type}`) ? t(`entity.${type}`) : type);
  if (entries.length === 0) return <p className="px-5 py-6 text-sm text-slate-500">{t("empty")}</p>;
  return (
    <ul className="divide-y divide-slate-200">
      {entries.map((e) => {
        const changes = auditDiff(e.before as Json, e.after as Json, formatters);
        const key = e.action.replace(".", "_");
        const ref = auditEntityRef(e.entity_type, e.entity_id, e.before as Json, e.after as Json, entityLabel);
        return (
          <li key={e.id} className="px-5 py-3">
            <div className="flex items-baseline justify-between gap-3">
              <div className="text-sm font-medium text-slate-900">
                {action.has(key) ? action(key) : e.action}
                <span className="ml-2 text-xs font-normal text-slate-500">{ref}</span>
              </div>
              <div className="text-xs text-slate-400 tabular-nums whitespace-nowrap">{dateTimeShort(e.at, locale)} · {e.actor_user_id ? t("actor", { id: e.actor_user_id.slice(0, 8) }) : t("system")}</div>
            </div>
            {changes.length ? (
              <dl className="mt-1.5 grid gap-x-4 gap-y-0.5 text-xs" style={{ gridTemplateColumns: "max-content 1fr" }}>
                {changes.slice(0, 12).map((c) => (
                  <div key={c.key} className="contents">
                    <dt className="text-slate-500">{c.label}</dt>
                    <dd className="text-slate-700 break-all"><span className="text-slate-400 line-through decoration-slate-300">{c.from}</span> → {c.to}</dd>
                  </div>
                ))}
                {changes.length > 12 ? <div className="col-span-2 text-slate-400">…</div> : null}
              </dl>
            ) : <div className="text-xs text-slate-400 mt-0.5">{t("unchanged")}</div>}
          </li>
        );
      })}
    </ul>
  );
}

/** Compact history card for one entity, with a link to the full log. */
export default async function AuditTrail({ entityType, entityId }: { entityType: string; entityId: string }) {
  const t = await getTranslations("audit");
  const res = await api.GET("/api/v1/audit-log", { params: { query: { entity_type: entityType, entity_id: entityId, limit: 10 } } });
  const entries = res.data?.entries ?? [];
  return (
    <Card title={t("cardTitle")} right={<Link href={`/audit?entity_type=${entityType}&entity_id=${entityId}`} className="text-xs text-blue-600 hover:underline">{t("seeAll")}</Link>}>
      <AuditEntries entries={entries} />
    </Card>
  );
}
