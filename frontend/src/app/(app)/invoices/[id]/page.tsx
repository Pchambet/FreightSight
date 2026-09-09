import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { ArrowLeft, ChevronRight, Loader2 } from "lucide-react";
import { Card } from "@/components/layout/AppShell";
import AutoRefresh from "@/features/invoices/AutoRefresh";
import ReviewPanel, { type Targets } from "@/features/invoices/ReviewPanel";
import { api, type InvoiceResponse } from "@/lib/api/client";
import { dateShort, money } from "@/lib/format";

type Params = { params: Promise<{ id: string }> };

async function load(id: string): Promise<{ invoice: InvoiceResponse; targets: Targets } | null> {
  const r = await api.GET("/api/v1/invoices/{invoice_id}", { params: { path: { invoice_id: id } } });
  if (r.response.status === 404 || r.response.status === 422 || !r.data) return null;
  const [c, p, s] = await Promise.all([api.GET("/api/v1/containers"), api.GET("/api/v1/purchase-orders"), api.GET("/api/v1/shipments")]);
  const targets: Targets = {
    SHIPMENT: (s.data ?? []).map((x) => ({ id: x.id, label: x.reference })),
    CONTAINER: (c.data ?? []).map((x) => ({ id: x.id, label: x.container_number })),
    PO: (p.data ?? []).map((x) => ({ id: x.id, label: x.po_number })),
    PO_LINE: [],
  };
  return { invoice: r.data, targets };
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const data = await load(id).catch(() => null);
  const t = await getTranslations("invoices");
  return { title: data?.invoice.invoice_number ? `${t("title")} ${data.invoice.invoice_number}` : t("title") };
}

export default async function InvoicePage({ params }: Params) {
  const { id } = await params;
  const data = await load(id);
  if (!data) notFound();
  const { invoice, targets } = data;
  const lines = invoice.lines ?? [];
  const notes = invoice.notes ?? [];
  const [t, statusLabel, locale] = await Promise.all([getTranslations("invoices.detail"), getTranslations("domain.invoiceStatus"), getLocale()]);
  const inProgress = invoice.status === "UPLOADED" || invoice.status === "EXTRACTING";
  const isPdf = (invoice.filename ?? "").toLowerCase().endsWith(".pdf");

  return (
    <>
      {inProgress ? <AutoRefresh /> : null}
      <div className="flex items-center text-sm text-slate-500 mb-4">
        <Link href="/invoices" className="hover:text-slate-900 flex items-center gap-1.5"><ArrowLeft className="w-4 h-4" />{t("back")}</Link>
        <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
        <span className="text-slate-900">{invoice.vendor ?? invoice.filename ?? invoice.id.slice(0, 8)}</span>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-semibold">{invoice.vendor ?? "—"} <span className="text-slate-400 font-normal">{invoice.invoice_number ?? ""}</span></h1>
          <p className="text-sm text-slate-500 mt-1">
            {statusLabel(invoice.status)}
            {invoice.invoice_date ? ` · ${dateShort(invoice.invoice_date, locale)}` : ""}
            {invoice.total_amount && invoice.currency ? ` · ${t("total")} ${money(invoice.total_amount, invoice.currency, locale)}` : ""}
            {invoice.vat_amount && invoice.currency ? ` · ${t("vat")} ${money(invoice.vat_amount, invoice.currency, locale)}` : ""}
            {invoice.extractor ? ` · ${t("extractor", { extractor: invoice.extractor, confidence: invoice.confidence ? Number(invoice.confidence).toFixed(2) : "—" })}` : ""}
          </p>
        </div>
      </div>

      {inProgress ? <div className="rounded-md border border-blue-200 bg-blue-50 text-blue-800 text-sm px-4 py-3 mb-6 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />{t("reading")} <span className="text-blue-600/70">{t("readingHint")}</span></div> : null}
      {invoice.status === "FAILED" ? <div className="rounded-md border border-red-200 bg-red-50 text-red-800 text-sm px-4 py-3 mb-6"><span className="font-medium">{t("failedTitle")}</span>{invoice.error ? ` · ${invoice.error}` : ""}</div> : null}
      {invoice.status === "CONFIRMED" ? <div className="rounded-md border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm px-4 py-3 mb-6">{t("confirmedBanner", { count: lines.filter((l) => l.cost_id).length, date: dateShort(invoice.created_at, locale) })}</div> : null}
      {invoice.status === "REJECTED" ? <div className="rounded-md border border-slate-200 bg-slate-50 text-slate-600 text-sm px-4 py-3 mb-6">{t("rejectedBanner")}</div> : null}
      {notes.length ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 text-amber-800 text-sm px-4 py-3 mb-6">
          <div className="text-xs font-medium uppercase tracking-wider mb-1">{t("notes")}</div>
          <ul className="list-disc pl-5 space-y-0.5">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </div>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6 items-start">
        <Card title={t("document")} className="xl:col-span-2">
          {isPdf ? (
            <iframe title={t("document")} src={`/api/invoices/${invoice.id}/document`} className="w-full h-[70vh] bg-slate-100" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`/api/invoices/${invoice.id}/document`} alt={invoice.filename ?? t("document")} className="w-full" />
          )}
        </Card>
        <Card title={t("lines")} right={<span className="text-xs text-slate-400">{lines.length}</span>} className="xl:col-span-3">
          <ReviewPanel invoice={invoice} targets={targets} />
        </Card>
      </div>
    </>
  );
}
