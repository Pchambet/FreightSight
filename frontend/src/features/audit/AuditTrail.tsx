import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { Card } from "@/components/layout/AppShell";
import { api, type AuditEntry } from "@/lib/api/client";
import { dateTimeShort } from "@/lib/format";

type Json = Record<string, unknown> | null | undefined;

/** Keys whose value differs between before and after, rendered as a generic diff: the payload has no fixed schema. */
function diff(before: Json, after: Json): { key: string; from: string; to: string }[] {
  const b = (before ?? {}) as Record<string, unknown>;
  const a = (after ?? {}) as Record<string, unknown>;
  const keys = Array.from(new Set([...Object.keys(b), ...Object.keys(a)])).sort();
  const show = (v: unknown) => (v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));
  return keys.filter((k) => JSON.stringify(b[k]) !== JSON.stringify(a[k])).map((k) => ({ key: k, from: show(b[k]), to: show(a[k]) }));
}

export async function AuditEntries({ entries }: { entries: AuditEntry[] }) {
  const [t, action, locale] = await Promise.all([getTranslations("audit"), getTranslations("domain.auditAction"), getLocale()]);
  if (entries.length === 0) return <p className="px-5 py-6 text-sm text-slate-500">{t("empty")}</p>;
  return (
    <ul className="divide-y divide-slate-200">
      {entries.map((e) => {
        const changes = diff(e.before as Json, e.after as Json);
        const key = e.action.replace(".", "_");
        return (
          <li key={e.id} className="px-5 py-3">
            <div className="flex items-baseline justify-between gap-3">
              <div className="text-sm font-medium text-slate-900">
                {action.has(key) ? action(key) : e.action}
                <span className="ml-2 text-xs font-normal text-slate-500">{t.has(`entity.${e.entity_type}`) ? t(`entity.${e.entity_type}`) : e.entity_type}{e.entity_id ? <span className="font-mono"> {e.entity_id.slice(0, 8)}</span> : null}</span>
              </div>
              <div className="text-xs text-slate-400 tabular-nums whitespace-nowrap">{dateTimeShort(e.at, locale)} · {e.actor_user_id ? t("actor", { id: e.actor_user_id.slice(0, 8) }) : t("system")}</div>
            </div>
            {changes.length ? (
              <dl className="mt-1.5 grid gap-x-4 gap-y-0.5 text-xs" style={{ gridTemplateColumns: "max-content 1fr" }}>
                {changes.slice(0, 12).map((c) => (
                  <div key={c.key} className="contents">
                    <dt className="font-mono text-slate-500">{c.key}</dt>
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
