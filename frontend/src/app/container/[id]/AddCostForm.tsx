"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Calculator, Plus, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AddCostForm({ containerId }: { containerId: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleAddCost = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);

    const formData = new FormData(e.currentTarget);
    const payload = {
      cost_type: formData.get("cost_type") as string,
      amount: parseFloat(formData.get("amount") as string),
      currency: "USD",
    };

    try {
      const res = await fetch(`http://localhost:8001/api/containers/${containerId}/costs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        toast.success("Cost added successfully. Landed costs updated.");
        (e.target as HTMLFormElement).reset();
        router.refresh();
      } else {
        toast.error("Failed to add cost. Please check the inputs.");
      }
    } catch (err) {
      toast.error("Network error. Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-indigo-100 p-1.5 rounded-lg">
          <Calculator className="w-5 h-5 text-indigo-600" />
        </div>
        <h3 className="text-lg font-semibold text-slate-900">Add Logistics Cost</h3>
      </div>
      
      <form onSubmit={handleAddCost} className="flex flex-col space-y-4">
        
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">Cost Type</label>
          <select name="cost_type" required className="w-full border border-slate-300 rounded-lg p-2.5 text-sm bg-white focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow">
            <option value="OCEAN_FREIGHT">Ocean Freight</option>
            <option value="CUSTOMS">Customs Duties</option>
            <option value="DRAYAGE">Drayage (Inland)</option>
            <option value="DEMURRAGE">Demurrage / Detention</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">Amount (USD)</label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="text-slate-500 sm:text-sm">$</span>
            </div>
            <input 
              type="number" 
              name="amount" 
              step="0.01" 
              required 
              placeholder="0.00"
              className="w-full pl-7 border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow"
            />
          </div>
        </div>

        <button 
          type="submit" 
          disabled={loading}
          className="relative mt-2 w-full flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2.5 px-4 rounded-lg disabled:opacity-50 disabled:hover:bg-indigo-600 transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Calculating...
            </>
          ) : (
            <>
              <Plus className="w-4 h-4 mr-2" />
              Add & Recalculate
            </>
          )}
        </button>
      </form>
    </div>
  );
}
