"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary, btnSecondary, input, label } from "@/components/layout/AppShell";
import { uploadInvoice } from "@/features/actions";
import { addManualCosts, type ManualCost } from "@/features/start/actions";
import { amountPlaceholder } from "@/lib/format";

const FIELDS: ManualCost["cost_type"][] = ["OCEAN_FREIGHT", "CUSTOMS_DUTY", "CUSTOMS_BROKERAGE", "DRAYAGE"];

/** Drop the forwarder's PDF — it is read for this container — or type the four figures known by heart. */
export function InvoiceDrop({ base, containerId }: { base: string; containerId: string }) {
  const t = useTranslations("start.costs");
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [pending, start] = useTransition();
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-col sm:flex-row sm:items-end gap-3">
      <label className="flex-1 min-w-0 flex items-center gap-3 rounded-lg border border-dashed border-slate-300 px-4 py-4 cursor-pointer hover:bg-slate-50 focus-within:ring-2 focus-within:ring-blue-500">
        <FileUp className="w-5 h-5 text-slate-400 shrink-0" aria-hidden />
        <span className="text-sm text-slate-600 truncate">{file ? file.name : t("choose")}</span>
        <input ref={ref} type="file" accept="application/pdf,image/png,image/jpeg" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <button
        type="button"
        disabled={!file || pending}
        className={`${btnPrimary} shrink-0`}
        onClick={() =>
          start(async () => {
            if (!file) return;
            const fd = new FormData();
            fd.append("file", file);
            fd.append("default_container_id", containerId);
            const r = await uploadInvoice(fd);
            if (!r.ok) return void toast.error(r.error);
            router.push(`${base}&invoice=${r.data.id}`);
          })
        }
      >
        {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" aria-hidden /> : null}
        {pending ? t("uploading") : t("upload")}
      </button>
    </div>
  );
}

export function ManualCosts({ base, containerId, costDate, baseCurrency }: { base: string; containerId: string; costDate: string; baseCurrency: string }) {
  const t = useTranslations("start.costs");
  const tt = useTranslations("domain.costType");
  const locale = useLocale();
  const router = useRouter();
  const [rows, setRows] = useState<ManualCost[]>(FIELDS.map((cost_type) => ({ cost_type, amount: "", currency: cost_type === "OCEAN_FREIGHT" ? "USD" : baseCurrency })));
  const [pending, start] = useTransition();
  const currencies = [...new Set([baseCurrency, "EUR", "USD"])];
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await addManualCosts(containerId, costDate, rows);
          if (!r.ok) return void toast.error(r.error);
          router.push(`${base}&step=result`);
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {rows.map((row, i) => (
          <div key={row.cost_type}>
            <label className={label} htmlFor={`manual-${row.cost_type}`}>{tt(row.cost_type)}</label>
            <div className="flex gap-2">
              <input id={`manual-${row.cost_type}`} inputMode="decimal" placeholder={amountPlaceholder(locale)} value={row.amount} onChange={(e) => setRows((prev) => prev.map((p, k) => (k === i ? { ...p, amount: e.target.value } : p)))} className={`${input} text-right tabular-nums`} />
              <select aria-label={t("currencyOf", { cost: tt(row.cost_type) })} value={row.currency} onChange={(e) => setRows((prev) => prev.map((p, k) => (k === i ? { ...p, currency: e.target.value } : p)))} className={`${input} !w-24`}>
                {currencies.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-500">{t("manualHint")}</p>
      <button type="submit" disabled={pending} className={btnSecondary}>{pending ? t("saving") : t("manualSubmit")}</button>
    </form>
  );
}

/**
 * While the invoice is being read: refresh every few seconds, and after twenty without an answer say
 * so — the reading runs in a background worker, and a worker that is down would otherwise look like
 * a reading that never ends.
 */
export function ReadingWatch({ workerAlive }: { workerAlive: boolean }) {
  const t = useTranslations("start.costs");
  const router = useRouter();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const tick = window.setInterval(() => router.refresh(), 3000);
    const late = window.setTimeout(() => setSlow(true), 20_000);
    return () => {
      window.clearInterval(tick);
      window.clearTimeout(late);
    };
  }, [router]);
  return (
    <div className="flex items-start gap-3 text-sm text-slate-700" role="status">
      <Loader2 className="w-4 h-4 mt-0.5 animate-spin text-blue-600 shrink-0" aria-hidden />
      <div>
        <p>{t("reading")}</p>
        {slow || !workerAlive ? <p className="mt-1 text-amber-800">{workerAlive ? t("readingSlow") : t("readingDown")}</p> : null}
      </div>
    </div>
  );
}
