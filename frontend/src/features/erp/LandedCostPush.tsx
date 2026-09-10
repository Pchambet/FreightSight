"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Send } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary, btnSecondary, Card } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { previewErpLandedCost, pushErpLandedCost, type ErpLandedCostPreview } from "@/features/actions";

const KNOWN_BLOCKERS = new Set(["no_erp_connection", "no_actual_costs", "no_receipt", "multiple_receipts", "not_valued", "unmatched_line", "already_pushed"]);

/**
 * The landed cost as it would land in the ERP, shown before it exists. The preview is loaded after
 * the page, because it reads the ERP live and a slow Odoo should not slow the container page down.
 * The push creates a draft only: validating posts entries in someone else's books.
 */
export default function LandedCostPush({ containerId, currency }: { containerId: string; currency: string }) {
  const t = useTranslations("erp.push");
  const router = useRouter();
  const [state, setState] = useState<{ loading: boolean; preview: ErpLandedCostPreview | null; error: string | null }>({ loading: true, preview: null, error: null });
  const { loading, preview, error } = state;
  const [pending, start] = useTransition();
  const [open, setOpen] = useState(false);

  const apply = (r: Awaited<ReturnType<typeof previewErpLandedCost>>) =>
    setState(r.ok ? { loading: false, preview: r.data, error: null } : { loading: false, preview: null, error: r.error });
  useEffect(() => {
    let alive = true;
    previewErpLandedCost(containerId).then((r) => {
      if (alive) apply(r);
    });
    return () => {
      alive = false;
    };
  }, [containerId]);
  const load = () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    previewErpLandedCost(containerId).then(apply);
  };

  const push = () =>
    start(async () => {
      const r = await pushErpLandedCost(containerId);
      if (!r.ok) return void toast.error(r.error);
      toast.success(t("pushed", { name: r.data.odoo_name ?? String(r.data.odoo_id) }), { duration: 8000 });
      load();
      router.refresh();
    });

  const blockers = preview?.blockers ?? [];
  /** The blocker in the reader's language, from its code and moving parts; the API's own sentence only for a code this screen does not know. */
  const blockerText = (b: { code: string; message: string; params?: Record<string, string> }) => {
    if (!KNOWN_BLOCKERS.has(b.code)) return b.message;
    const params = { ...(b.params ?? {}) };
    if (b.code === "unmatched_line" && !params.sku) params.sku = t("blocker.noSku");
    return t(`blocker.${b.code}` as never, params as never);
  };
  const alreadyPushed = preview?.already_pushed_as ?? blockers.find((b) => b.code === "already_pushed") ?? null;

  return (
    <Card title={t("title")}>
      <p className="text-sm text-slate-500 mb-3">{t("hint")}</p>
      {loading ? (
        <div className="flex items-center text-sm text-slate-500"><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t("loading")}</div>
      ) : error ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="inline-flex items-center text-red-700"><AlertTriangle className="w-4 h-4 mr-2" />{error}</span>
          <button type="button" onClick={load} className={btnSecondary}><RefreshCw className="w-4 h-4 mr-2" />{t("retry")}</button>
        </div>
      ) : preview ? (
        <div className="space-y-3">
          {alreadyPushed ? (
            <div className="flex items-start text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md px-3 py-2">
              <CheckCircle2 className="w-4 h-4 mr-2 mt-0.5 shrink-0" />
              <span>{t("alreadyPushed", { name: typeof alreadyPushed === "string" ? alreadyPushed : preview.already_pushed_as ?? "" })}<span className="block text-xs text-emerald-700 mt-0.5">{t("draftReminder")}</span></span>
            </div>
          ) : null}

          {blockers.filter((b) => b.code !== "already_pushed").map((b, i) => (
            <div key={`${b.code}-${i}`} className="flex items-start text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
              <AlertTriangle className="w-4 h-4 mr-2 mt-0.5 shrink-0 text-amber-600" />
              <span>{blockerText(b)}</span>
            </div>
          ))}

          {preview.costs.length > 0 ? (
            <div className="border border-slate-200 rounded-md overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 bg-slate-50 text-sm">
                <span className="text-slate-700">
                  {preview.receipt_name ? t("receipt", { name: preview.receipt_name }) : t("noReceipt")}
                  <span className="text-slate-400"> · {t("costCount", { count: preview.costs.length })}</span>
                </span>
                <span className="font-semibold tabular-nums"><Money amount={preview.total} currency={currency} /></span>
              </div>
              <ul className="divide-y divide-slate-100">
                {preview.costs.map((c, i) => (
                  <li key={i} className="px-3 py-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-800">{c.label}</span>
                      <span className="tabular-nums"><Money amount={c.amount} currency={currency} /></span>
                    </div>
                    {open && c.lines.length ? (
                      <ul className="mt-1 space-y-0.5">
                        {c.lines.map((l) => (
                          <li key={l.move_id} className="flex items-center justify-between text-xs text-slate-500 pl-3">
                            <span>{l.sku ? <span className="font-mono text-slate-600">{l.sku}</span> : null} {l.product_name} <span className="text-slate-400">× {l.quantity}</span></span>
                            <span className="tabular-nums"><Money amount={l.amount} currency={currency} /></span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ul>
              <button type="button" onClick={() => setOpen((v) => !v)} className="w-full text-left text-xs text-slate-500 hover:text-slate-700 px-3 py-1.5 border-t border-slate-100">
                {open ? t("hideLines") : t("showLines")}
              </button>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={push} disabled={pending || !preview.pushable} className={btnPrimary} title={preview.pushable ? undefined : t("notPushable")}>
              {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}{t("push")}
            </button>
            <button type="button" onClick={load} disabled={pending} className={btnSecondary}><RefreshCw className="w-4 h-4 mr-2" />{t("refresh")}</button>
            <span className="text-xs text-slate-500">{t("draftReminder")}</span>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
