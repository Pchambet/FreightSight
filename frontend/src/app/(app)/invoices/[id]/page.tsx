import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { Loader2 } from "lucide-react";
import { Card } from "@/components/layout/AppShell";
import Breadcrumb from "@/components/shared/Breadcrumb";
import ConfidenceBadge from "@/components/shared/ConfidenceBadge";
import AutoRefresh from "@/features/invoices/AutoRefresh";
import { containerLinksFromLines } from "@/features/invoices/containerLinks";
import { formatInvoiceNote } from "@/features/invoices/lineNotes";
import RejectedInvoiceActions from "@/features/invoices/RejectedInvoiceActions";
import ReopenConfirmedAction from "@/features/invoices/ReopenConfirmedAction";
import ReviewPanel, { type Targets } from "@/features/invoices/ReviewPanel";
import WorkflowNextStep from "@/features/workflow/WorkflowNextStep";
import { invoiceDetailStep } from "@/features/workflow/steps";
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
  const [t, noteT, costType, statusLabel, extractorKind, locale] = await Promise.all([
    getTranslations("invoices.detail"),
    getTranslations("invoices.lineNotes"),
    getTranslations("domain.costType"),
    getTranslations("domain.invoiceStatus"),
    getTranslations("domain.extractorKind"),
    getLocale(),
  ]);
  const inProgress = invoice.status === "UPLOADED" || invoice.status === "EXTRACTING";
  const isPdf = (invoice.filename ?? "").toLowerCase().endsWith(".pdf");
  const continueContainers = invoice.status === "CONFIRMED" ? containerLinksFromLines(lines, targets) : [];
  const primaryContainer = continueContainers[0];
  const detailStep = invoiceDetailStep(invoice.status, primaryContainer ? { id: primaryContainer.id, number: primaryContainer.container_number } : undefined);
  // `extractor_kind` (RULES/MODEL/UNKNOWN) and each line's `confidence_band` (HIGH/MEDIUM/LOW) are
  // new fields the generated schema does not carry yet (needs_other_lane) — read through a narrow
  // type rather than the raw `extractor` string ("regex") a DAF cannot make sense of (audit B24/B25).
  const extractorKindValue = (invoice as { extractor_kind?: string }).extractor_kind ?? "";
  const confidenceBandValue = (invoice as { confidence_band?: "HIGH" | "MEDIUM" | "LOW" }).confidence_band;
  const confirmedCostCount = lines.filter((l) => l.cost_id).length;

  return (
    <>
      {inProgress ? <AutoRefresh /> : null}
      <Breadcrumb
        backHref="/invoices"
        backLabel={t("back")}
        current={invoice.invoice_number ?? invoice.vendor ?? invoice.filename ?? invoice.id.slice(0, 8)}
      />
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-semibold">{invoice.vendor ?? "—"} <span className="text-slate-400 font-normal">{invoice.invoice_number ?? ""}</span></h1>
          <p className="text-sm text-slate-500 mt-1">
            {statusLabel(invoice.status)}
            {invoice.invoice_date ? ` · ${dateShort(invoice.invoice_date, locale)}` : ""}
            {invoice.currency && (invoice.total_amount || invoice.vat_amount || invoice.subtotal_amount)
              ? ` · ${t("subtotal")} ${invoice.subtotal_amount ? money(invoice.subtotal_amount, invoice.currency, locale) : t("subtotalMissing")} · ${t("vat")} ${invoice.vat_amount ? money(invoice.vat_amount, invoice.currency, locale) : "—"} · ${t("total")} ${invoice.total_amount ? money(invoice.total_amount, invoice.currency, locale) : "—"}`
              : ""}
            {invoice.extractor ? (
              <>
                {" · "}
                {t("extractedBy", { extractor: extractorKind.has(extractorKindValue as never) ? extractorKind(extractorKindValue as never) : invoice.extractor })}{" "}
                <ConfidenceBadge value={invoice.confidence} band={confidenceBandValue} className="align-middle" />
              </>
            ) : null}
          </p>
        </div>
      </div>

      {inProgress ? <div className="rounded-md border border-blue-200 bg-blue-50 text-blue-800 text-sm px-4 py-3 mb-6 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />{t("reading")} <span className="text-blue-600/70">{t("readingHint")}</span></div> : null}
      {/* invoice.error is a raw, uncoded backend string (extractor failure detail) — never shown verbatim to a DAF; see needs_other_lane. */}
      {invoice.status === "FAILED" ? <div className="rounded-md border border-red-200 bg-red-50 text-red-800 text-sm px-4 py-3 mb-6"><span className="font-medium">{t("failedTitle")}</span></div> : null}
      {invoice.status === "NEEDS_REVIEW" && invoice.confidence != null && Number(invoice.confidence) < 0.7 ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 text-amber-900 text-sm px-4 py-3 mb-6">
          <span className="font-medium">{t("lowConfidenceTitle")}</span> {t("lowConfidenceBody")}
        </div>
      ) : null}
      {detailStep ? <WorkflowNextStep step={detailStep} /> : null}
      {invoice.status === "CONFIRMED" ? (
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <p className="text-sm text-slate-500">{t("confirmedBanner", { count: confirmedCostCount, date: dateShort(invoice.created_at, locale) })}</p>
          <ReopenConfirmedAction invoiceId={invoice.id} costsCreated={confirmedCostCount} />
        </div>
      ) : null}
      {invoice.status === "REJECTED" ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 text-amber-950 text-sm px-4 py-4 mb-6">
          <p>{t("rejectedBanner")} {t("rejectedHint")}</p>
          <RejectedInvoiceActions invoiceId={invoice.id} hasLines={lines.length > 0} />
        </div>
      ) : null}
      {notes.length ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 text-amber-800 text-sm px-4 py-3 mb-6">
          <div className="text-xs font-medium uppercase tracking-wider mb-1">{t("notes")}</div>
          <ul className="list-disc pl-5 space-y-0.5">{notes.map((n, i) => <li key={i}>{formatInvoiceNote(n, noteT, (k) => costType(k as never), locale, invoice.currency ?? "EUR")}</li>)}</ul>
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
          <div id="lignes" className="scroll-mt-6">
            <ReviewPanel invoice={invoice} targets={targets} />
          </div>
        </Card>
      </div>
    </>
  );
}
