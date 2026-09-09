"use client";

import { useRef, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Card, btnSecondary, input, label, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { addRateCard, deleteRateCard } from "@/features/actions";
import type { RateCard } from "@/lib/api/client";
import { COST_TYPES, RATE_BASES, type CostType, type RateBasis } from "@/lib/domain";

export default function RateCards({ cards, currency }: { cards: RateCard[]; currency: string }) {
  const t = useTranslations("rateCards");
  const typeLabel = useTranslations("domain.costType");
  const scopeLabel = useTranslations("domain.costScope");
  const [pending, start] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);
  const router = useRouter();

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    start(async () => {
      const r = await addRateCard({
        cost_type: String(f.get("cost_type")) as CostType,
        scope: String(f.get("scope")) as "CONTAINER" | "SHIPMENT",
        basis: String(f.get("basis")) as RateBasis,
        amount: String(f.get("amount") ?? ""),
        currency: String(f.get("currency") ?? currency),
        hs_code: String(f.get("hs_code") ?? "") || undefined,
        notes: String(f.get("notes") ?? "") || undefined,
      });
      if (!r.ok) return void toast.error(r.error);
      toast.success(t("added"));
      formRef.current?.reset();
      router.refresh();
    });
  };
  const remove = (id: string) =>
    start(async () => {
      const r = await deleteRateCard(id);
      if (!r.ok) return void toast.error(r.error);
      toast.success(t("deleted"));
      router.refresh();
    });

  return (
    <Card title={t("title")} right={<span className="text-xs text-slate-400 max-w-md text-right">{t("hint")}</span>}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50"><tr><th className={th}>{t("costType")}</th><th className={th}>{t("scope")}</th><th className={th}>{t("basis")}</th><th className={thRight}>{t("amount")}</th><th className={th}>{t("hsCode")}</th><th className={th}>{t("notes")}</th><th className={th}></th></tr></thead>
          <tbody className="divide-y divide-slate-200">
            {cards.length === 0 ? <tr><td colSpan={7} className="px-5 py-6 text-center text-sm text-slate-400">{t("empty")}</td></tr> : cards.map((c) => (
              <tr key={c.id}>
                <td className={td}>{typeLabel(c.cost_type)}</td>
                <td className={`${td} text-slate-600`}>{scopeLabel(c.scope)}</td>
                <td className={`${td} text-slate-600`}>{t(`basisLabel.${c.basis}`)}</td>
                <td className={tdRight}>{c.basis === "PCT_OF_FOB" ? `${c.amount} %` : <Money amount={c.amount} currency={c.currency} />}</td>
                <td className={`${td} font-mono text-slate-600`}>{c.hs_code ?? "—"}</td>
                <td className={`${td} text-slate-500 text-xs`}>{c.notes ?? ""}</td>
                <td className={tdRight}><button type="button" onClick={() => remove(c.id)} disabled={pending} className="text-slate-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form ref={formRef} onSubmit={submit} className="p-5 border-t border-slate-200 grid grid-cols-2 md:grid-cols-7 gap-3 items-end">
        <div><label className={label} htmlFor="rc-type">{t("costType")}</label><select id="rc-type" name="cost_type" className={input} defaultValue="OCEAN_FREIGHT">{COST_TYPES.map((c) => <option key={c} value={c}>{typeLabel(c)}</option>)}</select></div>
        <div><label className={label} htmlFor="rc-scope">{t("scope")}</label><select id="rc-scope" name="scope" className={input} defaultValue="CONTAINER"><option value="CONTAINER">{scopeLabel("CONTAINER")}</option><option value="SHIPMENT">{scopeLabel("SHIPMENT")}</option></select></div>
        <div><label className={label} htmlFor="rc-basis">{t("basis")}</label><select id="rc-basis" name="basis" className={input} defaultValue="FLAT">{RATE_BASES.map((b) => <option key={b} value={b}>{t(`basisLabel.${b}`)}</option>)}</select></div>
        <div><label className={label} htmlFor="rc-amount">{t("amount")}</label><input id="rc-amount" name="amount" inputMode="decimal" required className={`${input} tabular-nums`} /></div>
        <div><label className={label} htmlFor="rc-cur">{t("currency")}</label><input id="rc-cur" name="currency" defaultValue={currency} maxLength={3} className={`${input} font-mono uppercase`} /></div>
        <div><label className={label} htmlFor="rc-hs">{t("hsCode")}</label><input id="rc-hs" name="hs_code" maxLength={12} className={`${input} font-mono`} /></div>
        <button type="submit" disabled={pending} className={btnSecondary}>{t("add")}</button>
      </form>
    </Card>
  );
}
