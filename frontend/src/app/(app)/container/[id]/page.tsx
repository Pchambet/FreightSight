import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { AlertTriangle, Box } from "lucide-react";
import { PageHeader } from "@/components/layout/AppShell";
import Breadcrumb from "@/components/shared/Breadcrumb";
import MetricLabel from "@/components/shared/MetricLabel";
import CollapsibleSection from "@/components/shared/CollapsibleSection";
import { MilestoneBadge, RiskBadge } from "@/components/shared/Badges";
import { Money } from "@/components/shared/Money";
import AllocationPanel from "@/features/costs/AllocationPanel";
import UnitCostHighlight from "@/features/costs/UnitCostHighlight";
import CostLedger from "@/features/costs/CostLedger";
import AddCostForm from "@/features/costs/AddCostForm";
import LoadsEditor from "@/features/containers/LoadsEditor";
import TrackingPanel from "@/features/containers/TrackingPanel";
import TimelinePanel from "@/features/containers/TimelinePanel";
import AuditTrail from "@/features/audit/AuditTrail";
import EstimatePanel from "@/features/estimates/EstimatePanel";
import LandedCostPush from "@/features/erp/LandedCostPush";
import WorkflowNextStep from "@/features/workflow/WorkflowNextStep";
import { containerWorkflowStep } from "@/features/workflow/steps";
import { api, type ContainerResponse, type EtaHistoryResponse, type LandedCostReport, type LoadResponse, type PurchaseOrderSummary, type Schemas, type TrackingEventResponse } from "@/lib/api/client";
import { dateShort, daysUntil } from "@/lib/format";

type Params = { params: Promise<{ id: string }> };

const API_ERROR = "api_error";

async function load(id: string): Promise<{ container: ContainerResponse; report: LandedCostReport; loads: LoadResponse[]; pos: PurchaseOrderSummary[]; shipmentRef: string | null; events: TrackingEventResponse[]; etaHistory: EtaHistoryResponse[]; subscription: Schemas["TrackingSubscriptionResponse"] | null; erpConnected: boolean; invoicesToReview: number } | null> {
  const c = await api.GET("/api/v1/containers/{container_id}", { params: { path: { container_id: id } } });
  if (c.response.status === 404 || c.response.status === 422) return null;
  if (c.error || !c.data) throw new Error(API_ERROR);
  const [r, l, p, s, ev, eh, sub, erp, inv] = await Promise.all([
    api.GET("/api/v1/landed-costs/containers/{container_id}", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/containers/{container_id}/loads", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/purchase-orders"),
    c.data.shipment_id ? api.GET("/api/v1/shipments/{shipment_id}", { params: { path: { shipment_id: c.data.shipment_id } } }) : Promise.resolve(null),
    api.GET("/api/v1/containers/{container_id}/events", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/containers/{container_id}/eta-history", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/containers/{container_id}/tracking", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/erp/connection"),
    api.GET("/api/v1/invoices", { params: { query: { invoice_status: "NEEDS_REVIEW" } } }),
  ]);
  if (r.error || !r.data || l.error || !l.data) throw new Error(API_ERROR);
  return {
    container: c.data,
    report: r.data,
    loads: l.data,
    pos: p.data ?? [],
    shipmentRef: s?.data?.reference ?? null,
    events: ev.data ?? [],
    etaHistory: eh.data ?? [],
    subscription: sub.response.status === 200 ? (sub.data ?? null) : null,
    erpConnected: erp.response.status === 200,
    invoicesToReview: inv.data?.length ?? 0,
  };
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const data = await load(id).catch(() => null);
  const t = await getTranslations("container");
  return { title: data ? data.container.container_number : t("fallbackTitle") };
}

export default async function ContainerPage({ params }: Params) {
  const { id: containerId } = await params;
  const data = await load(containerId);
  if (!data) notFound();
  const { container, report, loads, pos, shipmentRef, events, etaHistory, subscription, erpConnected, invoicesToReview } = data;
  const [t, errorCode, tg, locale] = await Promise.all([getTranslations("container"), getTranslations("errors"), getTranslations("glossary"), getLocale()]);
  const cur = report.base_currency;
  const revalidate = `/container/${container.id}`;
  const step = containerWorkflowStep(container, loads, report, invoicesToReview);

  return (
    <>
      <Breadcrumb backHref="/containers" backLabel={t("breadcrumb")} current={container.container_number} />

      <PageHeader
        title={<span className="font-mono flex items-center gap-3"><Box className="w-6 h-6 text-blue-600" />{container.container_number}</span>}
        subtitle={
          <span className="flex items-center gap-3 flex-wrap">
            <MilestoneBadge milestone={container.milestone} />
            <RiskBadge risk={container.dnd_risk} days={daysUntil(container.last_free_day)} />
            {container.last_free_day ? <span>{t("lastFreeDay", { date: dateShort(container.last_free_day, locale) })}</span> : null}
            {shipmentRef ? <span>{t("shipment", { reference: shipmentRef })}</span> : null}
          </span>
        }
      />

      <WorkflowNextStep step={step} />

      {report.warnings.length > 0 ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 text-amber-800 text-sm px-4 py-3 space-y-1 mb-6">
          {report.warnings.map((w) => (
            <div key={w.cost_id} className="flex gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                {errorCode.has(w.code) ? errorCode(w.code) : w.message}
                {w.load_labels?.length ? <span className="text-amber-700/80"> {w.load_labels.join(", ")}</span> : null}
                {" ("}<Money amount={w.amount_base} currency={cur} /> {t("unallocatedSuffix")}{")"}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        {(["fob", "allocated", "vat", "landed", "unallocated"] as const).map((k) => (
          <div key={k} className="bg-white rounded-lg border border-slate-200 px-4 py-3">
            <MetricLabel label={t(`totals.${k}`)} hint={tg(k)} />
            <div className={`text-lg font-semibold tabular-nums mt-1 ${k === "unallocated" && report.totals.unallocated !== "0.00" ? "text-amber-700" : ""}`}>
              <Money amount={report.totals[k]} currency={cur} />
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-6 mb-6">
        <UnitCostHighlight report={report} />
        <EstimatePanel report={report} currency={cur} containerId={container.id} />
        <section id="ventilation" className="scroll-mt-6">
          <AllocationPanel key={report.costs.map((c) => c.id).join(",")} containerId={container.id} report={report} />
        </section>
      </div>

      <div className="space-y-3">
        <CollapsibleSection id="suivi" title={t("sections.tracking")} hint={t("sections.trackingHint")}>
          <div className="p-5 space-y-6">
            <TrackingPanel container={container} subscription={subscription} />
            <TimelinePanel containerId={container.id} events={events} etaHistory={etaHistory} />
          </div>
        </CollapsibleSection>

        <CollapsibleSection id="chargements" title={t("sections.loads")} hint={t("sections.loadsHint")} defaultOpen={loads.length === 0}>
          <div className="p-5">
            <LoadsEditor containerId={container.id} loads={loads} purchaseOrders={pos} />
          </div>
        </CollapsibleSection>

        <CollapsibleSection id="ajouter-cout" title={t("sections.addCost")} hint={t("sections.addCostHint")}>
          <div className="p-5">
            <AddCostForm scope="CONTAINER" targetId={container.id} shipmentId={container.shipment_id} currency={cur} revalidate={revalidate} />
          </div>
        </CollapsibleSection>

        <CollapsibleSection title={t("sections.ledger")} hint={t("sections.ledgerHint")}>
          <div className="p-5">
            <CostLedger report={report} currency={cur} revalidate={revalidate} />
          </div>
        </CollapsibleSection>

        {erpConnected ? (
          <CollapsibleSection title={t("sections.erp")}>
            <div className="p-5">
              <LandedCostPush key={report.costs.map((c) => `${c.id}:${c.status ?? ""}:${c.amount_base ?? ""}`).join(",")} containerId={container.id} currency={cur} embedded />
            </div>
          </CollapsibleSection>
        ) : null}

        <CollapsibleSection title={t("sections.audit")}>
          <div className="p-5">
            <AuditTrail entityType="container" entityId={container.id} />
          </div>
        </CollapsibleSection>
      </div>
    </>
  );
}
