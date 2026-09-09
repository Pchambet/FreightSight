import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { AlertTriangle, ArrowLeft, Box, ChevronRight } from "lucide-react";
import { Card, PageHeader } from "@/components/layout/AppShell";
import { MilestoneBadge, RiskBadge } from "@/components/shared/Badges";
import { Money } from "@/components/shared/Money";
import AllocationPanel from "@/features/costs/AllocationPanel";
import CostLedger from "@/features/costs/CostLedger";
import AddCostForm from "@/features/costs/AddCostForm";
import LoadsEditor from "@/features/containers/LoadsEditor";
import TrackingPanel from "@/features/containers/TrackingPanel";
import TimelinePanel from "@/features/containers/TimelinePanel";
import AuditTrail from "@/features/audit/AuditTrail";
import EstimatePanel from "@/features/estimates/EstimatePanel";
import LandedCostPush from "@/features/erp/LandedCostPush";
import { api, type ContainerResponse, type EtaHistoryResponse, type LandedCostReport, type LoadResponse, type PurchaseOrderSummary, type Schemas, type TrackingEventResponse } from "@/lib/api/client";
import { dateShort, daysUntil } from "@/lib/format";

type Params = { params: Promise<{ id: string }> };

// Thrown, never rendered: the error boundary shows the translated message.
const API_ERROR = "api_error";

async function load(id: string): Promise<{ container: ContainerResponse; report: LandedCostReport; loads: LoadResponse[]; pos: PurchaseOrderSummary[]; shipmentRef: string | null; events: TrackingEventResponse[]; etaHistory: EtaHistoryResponse[]; subscription: Schemas["TrackingSubscriptionResponse"] | null; erpConnected: boolean } | null> {
  const c = await api.GET("/api/v1/containers/{container_id}", { params: { path: { container_id: id } } });
  if (c.response.status === 404 || c.response.status === 422) return null;
  if (c.error || !c.data) throw new Error(API_ERROR);
  const [r, l, p, s, ev, eh, sub, erp] = await Promise.all([
    api.GET("/api/v1/landed-costs/containers/{container_id}", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/containers/{container_id}/loads", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/purchase-orders"),
    c.data.shipment_id ? api.GET("/api/v1/shipments/{shipment_id}", { params: { path: { shipment_id: c.data.shipment_id } } }) : Promise.resolve(null),
    api.GET("/api/v1/containers/{container_id}/events", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/containers/{container_id}/eta-history", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/containers/{container_id}/tracking", { params: { path: { container_id: id } } }),
    api.GET("/api/v1/erp/connection"),
  ]);
  if (r.error || !r.data || l.error || !l.data) throw new Error(API_ERROR);
  return { container: c.data, report: r.data, loads: l.data, pos: p.data ?? [], shipmentRef: s?.data?.reference ?? null, events: ev.data ?? [], etaHistory: eh.data ?? [], subscription: sub.response.status === 200 ? (sub.data ?? null) : null, erpConnected: erp.response.status === 200 };
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
  const { container, report, loads, pos, shipmentRef, events, etaHistory, subscription, erpConnected } = data;
  const [t, errorCode, locale] = await Promise.all([getTranslations("container"), getTranslations("errors"), getLocale()]);
  const cur = report.base_currency;
  const revalidate = `/container/${container.id}`;

  return (
    <>
      <div className="flex items-center text-sm text-slate-500 mb-4">
        <Link href="/containers" className="hover:text-slate-900 flex items-center gap-1.5"><ArrowLeft className="w-4 h-4" />{t("breadcrumb")}</Link>
        <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
        <span className="text-slate-900 font-mono">{container.container_number}</span>
      </div>

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

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-1 space-y-6">
          <TrackingPanel container={container} subscription={subscription} />
          <TimelinePanel containerId={container.id} events={events} etaHistory={etaHistory} />
          <Card title={t("cards.loads")}>
            <LoadsEditor containerId={container.id} loads={loads} purchaseOrders={pos} />
          </Card>
          <Card title={t("cards.addCost")}>
            <AddCostForm scope="CONTAINER" targetId={container.id} shipmentId={container.shipment_id} currency={cur} revalidate={revalidate} />
          </Card>
        </div>

        <div className="xl:col-span-2 space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {(["fob", "allocated", "vat", "landed", "unallocated"] as const).map((k) => (
              <div key={k} className="bg-white rounded-lg border border-slate-200 px-4 py-3">
                <div className="text-xs text-slate-500 uppercase tracking-wider">{t(`totals.${k}`)}</div>
                <div className={`text-lg font-semibold tabular-nums mt-1 ${k === "unallocated" && report.totals.unallocated !== "0.00" ? "text-amber-700" : ""}`}>
                  <Money amount={report.totals[k]} currency={cur} />
                </div>
              </div>
            ))}
          </div>
          <EstimatePanel report={report} currency={cur} containerId={container.id} />
          <AllocationPanel key={report.costs.map((c) => c.id).join(",")} containerId={container.id} report={report} />
          <CostLedger report={report} currency={cur} revalidate={revalidate} />
          {erpConnected ? <LandedCostPush containerId={container.id} currency={cur} /> : null}
          <AuditTrail entityType="container" entityId={container.id} />
        </div>
      </div>
    </>
  );
}
