"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary, btnSecondary, input } from "@/components/layout/AppShell";
import { confirmInvoice, rejectInvoice, retryInvoice, updateInvoiceLine } from "@/features/actions";
import type { InvoiceLineResponse, InvoiceResponse } from "@/lib/api/client";
import { COST_SCOPES, COST_TYPES, type CostScope, type CostType } from "@/lib/domain";
import { money } from "@/lib/format";

export type Target = { id: string; label: string };
export type Targets = Record<CostScope, Target[]>;

function LineRow({ invoiceId, line, targets, editable }: { invoiceId: string; line: InvoiceLineResponse; targets: Targets; editable: boolean }) {
  const t = useTranslations("invoices.line");
  const typeLabel = useTranslations("domain.costType");
  const scopeLabel = useTranslations("domain.costScope");
  const [amount, setAmount] = useState(line.amount);
  const [currency, setCurrency] = useState(line.currency);
  const [costType, setCostType] = useState<CostType | "">(line.cost_type ?? "");
  const [scope, setScope] = useState<CostScope | "">(line.scope ?? "");
  const [target, setTarget] = useState(line.target_id ?? "");
  const [accepted, setAccepted] = useState(line.accepted);
  const [pending, start] = useTransition();
  const router = useRouter();
  const dirty = amount !== line.amount || currency !== line.currency || costType !== (line.cost_type ?? "") || scope !== (line.scope ?? "") || target !== (line.target_id ?? "") || accepted !== line.accepted;
  const conf = Number(line.confidence);
  const confClass = conf >= 0.85 ? "text-emerald-700" : conf >= 0.6 ? "text-amber-700" : "text-red-700";

  const save = (patch?: Partial<Parameters<typeof updateInvoiceLine>[2]>) =>
    start(async () => {
      const r = await updateInvoiceLine(invoiceId, line.id, {
        amount, currency: currency.toUpperCase(),
        cost_type: costType || null, scope: scope || null, target_id: target || null, accepted,
        ...patch,
      });
      if (!r.ok) return void toast.error(r.error);
      toast.success(t("saved"));
      router.refresh();
    });

  const options = scope ? targets[scope] : [];
  return (
    <li className={`px-5 py-4 ${accepted ? "" : "bg-slate-50/60"}`}>
      <div className="flex items-start gap-3">
        <input type="checkbox" className="mt-1" checked={accepted} disabled={!editable || pending} aria-label={t("accepted")} onChange={(e) => { setAccepted(e.target.checked); start(async () => { const r = await updateInvoiceLine(invoiceId, line.id, { accepted: e.target.checked }); if (!r.ok) toast.error(r.error); router.refresh(); }); }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-sm font-medium text-slate-900 truncate">{line.line_no}. {line.description}</div>
            <div className={`text-xs tabular-nums whitespace-nowrap ${confClass}`}>{t("confidence", { value: conf.toFixed(2) })}</div>
          </div>
          {editable ? (
            <div className="mt-2 grid grid-cols-2 md:grid-cols-6 gap-2">
              <input aria-label={t("amount")} value={amount} onChange={(e) => setAmount(e.target.value)} className={`${input} text-right tabular-nums`} />
              <input aria-label={t("currency")} value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} className={`${input} font-mono uppercase`} />
              <select aria-label={t("costType")} value={costType} onChange={(e) => setCostType(e.target.value as CostType)} className={input}>
                <option value="">—</option>
                {COST_TYPES.map((c) => <option key={c} value={c}>{typeLabel(c)}</option>)}
              </select>
              <select aria-label={t("scope")} value={scope} onChange={(e) => { setScope(e.target.value as CostScope); setTarget(""); }} className={input}>
                <option value="">—</option>
                {COST_SCOPES.map((s) => <option key={s} value={s}>{scopeLabel(s)}</option>)}
              </select>
              <select aria-label={t("target")} value={target} onChange={(e) => setTarget(e.target.value)} className={input} disabled={!scope}>
                <option value="">{scope ? t("chooseTarget") : t("noTarget")}</option>
                {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <button type="button" onClick={() => save()} disabled={!dirty || pending} className={btnSecondary}>{pending ? <Loader2 className="w-4 h-4 animate-spin" /> : t("save")}</button>
            </div>
          ) : (
            <div className="mt-1 text-xs text-slate-500">
              {money(line.amount, line.currency)} · {line.cost_type ? typeLabel(line.cost_type) : "—"} · {line.scope ? scopeLabel(line.scope) : "—"}{line.target_id && line.scope ? ` · ${targets[line.scope].find((o) => o.id === line.target_id)?.label ?? ""}` : ""}
            </div>
          )}
          {line.notes ? <div className="mt-1 text-xs text-amber-700">{line.notes}</div> : null}
          {accepted && !target && editable ? <div className="mt-1 text-xs text-red-600">{t("needsTarget")}</div> : null}
        </div>
      </div>
    </li>
  );
}

export default function ReviewPanel({ invoice, targets }: { invoice: InvoiceResponse; targets: Targets }) {
  const t = useTranslations("invoices.detail");
  const locale = useLocale();
  const [pending, start] = useTransition();
  const router = useRouter();
  const editable = invoice.status === "NEEDS_REVIEW";
  const lines = invoice.lines ?? [];
  const acceptedCount = lines.filter((l) => l.accepted).length;
  const ready = acceptedCount > 0 && lines.filter((l) => l.accepted).every((l) => l.target_id && l.cost_type && l.scope);

  const run = (fn: () => Promise<{ ok: boolean; error?: string; data?: unknown }>, okMsg: (d: unknown) => string) =>
    start(async () => {
      const r = await fn();
      if (!r.ok) return void toast.error(r.error ?? t("failed"));
      toast.success(okMsg(r.data));
      router.refresh();
    });

  return (
    <div>
      {lines.length === 0 ? <p className="px-5 py-6 text-sm text-slate-500">{t("noLines")}</p> : null}
      <ul className="divide-y divide-slate-200">
        {lines.map((l) => <LineRow key={l.id} invoiceId={invoice.id} line={l} targets={targets} editable={editable} />)}
      </ul>
      {editable ? (
        <div className="px-5 py-4 border-t border-slate-200 flex flex-wrap items-center gap-3">
          <button type="button" disabled={!ready || pending} onClick={() => run(() => confirmInvoice(invoice.id), (d) => t("confirmed", { count: (d as { costsCreated: number }).costsCreated }))} className={btnPrimary}>
            {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}{acceptedCount ? t("confirm", { count: acceptedCount }) : t("confirmNone")}
          </button>
          <button type="button" disabled={pending} onClick={() => run(() => rejectInvoice(invoice.id), () => t("rejected"))} className={btnSecondary}>{t("reject")}</button>
          <button type="button" disabled={pending} onClick={() => run(() => retryInvoice(invoice.id), () => t("retried"))} className="text-sm text-slate-500 hover:underline">{t("retry")}</button>
          <span className="text-xs text-slate-400 ml-auto">{new Intl.DateTimeFormat(locale === "fr" ? "fr-FR" : "en-GB", { dateStyle: "medium" }).format(new Date(invoice.created_at))}</span>
        </div>
      ) : null}
      {invoice.status === "FAILED" ? (
        <div className="px-5 py-4 border-t border-slate-200 flex items-center gap-3">
          <button type="button" disabled={pending} onClick={() => run(() => retryInvoice(invoice.id), () => t("retried"))} className={btnSecondary}>{t("retry")}</button>
          <button type="button" disabled={pending} onClick={() => run(() => rejectInvoice(invoice.id), () => t("rejected"))} className="text-sm text-slate-500 hover:underline">{t("reject")}</button>
        </div>
      ) : null}
    </div>
  );
}
