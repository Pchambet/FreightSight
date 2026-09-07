"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary, input, label } from "@/components/layout/AppShell";
import { addCost } from "@/features/actions";
import { COST_TYPES, COST_TYPE_LABEL, METHOD_LABEL, USER_METHODS, type CostScope } from "@/lib/domain";

export default function AddCostForm({ scope, targetId, shipmentId, currency, revalidate }: { scope: CostScope; targetId: string; shipmentId?: string | null; currency: string; revalidate: string }) {
  const [pending, startTransition] = useTransition();
  const [cur, setCur] = useState(currency);
  const [costType, setCostType] = useState("OCEAN_FREIGHT");
  const formRef = useRef<HTMLFormElement>(null);
  const router = useRouter();
  const today = new Date().toISOString().slice(0, 10);

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const chosenScope = String(f.get("scope") ?? scope) as CostScope;
    startTransition(async () => {
      const result = await addCost({
        scope: chosenScope,
        target_id: chosenScope === "SHIPMENT" && shipmentId ? shipmentId : targetId,
        cost_type: String(f.get("cost_type")),
        amount: String(f.get("amount") ?? ""),
        currency: String(f.get("currency") ?? currency).toUpperCase(),
        cost_date: String(f.get("cost_date") ?? today),
        allocation_method: String(f.get("allocation_method") ?? "") || undefined,
        fx_rate: String(f.get("fx_rate") ?? "") || undefined,
        vendor: String(f.get("vendor") ?? "") || undefined,
        invoice_number: String(f.get("invoice_number") ?? "") || undefined,
        revalidate,
      });
      if (!result.ok) return void toast.error(result.error);
      toast.success("Cost added. Allocation recalculated.");
      formRef.current?.reset();
      setCur(currency);
      router.refresh();
    });
  };

  return (
    <form ref={formRef} onSubmit={submit} className="p-5 space-y-3">
      {shipmentId ? (
        <div>
          <label className={label} htmlFor="scope">Applies to</label>
          <select id="scope" name="scope" defaultValue={scope} className={input}>
            <option value="CONTAINER">This container only</option>
            <option value="SHIPMENT">The whole shipment (all its containers)</option>
          </select>
        </div>
      ) : null}
      <div>
        <label className={label} htmlFor="cost_type">Cost type</label>
        <select id="cost_type" name="cost_type" value={costType} onChange={(e) => setCostType(e.target.value)} className={input}>
          {COST_TYPES.map((t) => <option key={t} value={t}>{COST_TYPE_LABEL[t]}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2">
          <label className={label} htmlFor="amount">Amount</label>
          <input id="amount" name="amount" inputMode="decimal" required placeholder="0.00" className={`${input} tabular-nums`} />
        </div>
        <div>
          <label className={label} htmlFor="currency">Currency</label>
          <input id="currency" name="currency" value={cur} onChange={(e) => setCur(e.target.value.toUpperCase())} maxLength={3} className={`${input} uppercase font-mono`} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={label} htmlFor="cost_date">Invoice date</label>
          <input id="cost_date" name="cost_date" type="date" defaultValue={today} required className={input} />
        </div>
        <div>
          <label className={label} htmlFor="fx_rate">FX rate {cur !== currency ? `(1 ${cur} = ? ${currency})` : ""}</label>
          <input id="fx_rate" name="fx_rate" inputMode="decimal" placeholder={cur === currency ? "n/a" : "ECB at date"} disabled={cur === currency} className={`${input} tabular-nums`} />
        </div>
      </div>
      {costType !== "CUSTOMS_DUTY" ? (
        <div>
          <label className={label} htmlFor="allocation_method">Allocation method</label>
          <select id="allocation_method" name="allocation_method" defaultValue="" className={input}>
            <option value="">Organization default</option>
            {USER_METHODS.map((m) => <option key={m} value={m}>{METHOD_LABEL[m]}</option>)}
          </select>
        </div>
      ) : (
        <p className="text-xs text-slate-500">Customs duty is allocated on the CIF basis, by theoretical duty when every line has a duty rate.</p>
      )}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={label} htmlFor="vendor">Vendor</label>
          <input id="vendor" name="vendor" className={input} />
        </div>
        <div>
          <label className={label} htmlFor="invoice_number">Invoice no.</label>
          <input id="invoice_number" name="invoice_number" className={input} />
        </div>
      </div>
      <button type="submit" disabled={pending} className={`${btnPrimary} w-full`}>
        {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
        Add cost
      </button>
    </form>
  );
}
