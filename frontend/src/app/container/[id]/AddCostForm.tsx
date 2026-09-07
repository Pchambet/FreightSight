"use client";

import { useRef, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";
import { addCost } from "@/features/actions";
import { COST_TYPES, COST_TYPE_LABEL } from "@/lib/domain";

export default function AddCostForm({ containerId, currency }: { containerId: string; currency: string }) {
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);
  const router = useRouter();

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const input = {
      cost_type: String(formData.get("cost_type") ?? ""),
      amount: String(formData.get("amount") ?? ""),
    };
    startTransition(async () => {
      const result = await addCost(containerId, currency, input);
      if (!result.ok) {
        toast.error(result.error);
        return;
      }
      toast.success("Cost added. Allocation recalculated.");
      formRef.current?.reset();
      router.refresh();
    });
  };

  return (
    <div className="bg-white p-5 rounded-lg border border-slate-200">
      <h3 className="text-sm font-semibold mb-4">Add a logistics cost</h3>
      <form ref={formRef} onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor="cost_type" className="block text-xs font-medium text-slate-600 mb-1">Cost type</label>
          <select
            id="cost_type"
            name="cost_type"
            required
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
          >
            {COST_TYPES.map((t) => (
              <option key={t} value={t}>{COST_TYPE_LABEL[t]}</option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="amount" className="block text-xs font-medium text-slate-600 mb-1">Amount ({currency})</label>
          <input
            id="amount"
            type="text"
            inputMode="decimal"
            name="amount"
            required
            placeholder="0.00"
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm tabular-nums focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
          />
        </div>

        <button
          type="submit"
          disabled={pending}
          className="w-full inline-flex items-center justify-center bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-sm font-medium py-2 px-4 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2"
        >
          {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
          Add cost
        </button>
      </form>
    </div>
  );
}
