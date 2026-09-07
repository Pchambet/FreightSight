"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { updateContainerStatus } from "@/features/actions";
import { CONTAINER_STATUSES, CONTAINER_STATUS_LABEL } from "@/lib/domain";

export default function StatusSelect({ containerId, status }: { containerId: string; status: string }) {
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  return (
    <label className="inline-flex items-center gap-2 text-xs text-slate-600">
      Status
      <select
        value={status}
        disabled={pending}
        onChange={(e) => {
          const next = e.target.value;
          startTransition(async () => {
            const result = await updateContainerStatus(containerId, next);
            if (!result.ok) toast.error(result.error);
            else router.refresh();
          });
        }}
        className="border border-slate-300 rounded-md px-2 py-1 text-xs bg-white"
      >
        {CONTAINER_STATUSES.map((s) => (
          <option key={s} value={s}>{CONTAINER_STATUS_LABEL[s]}</option>
        ))}
      </select>
      <span className="text-slate-400">(manual until tracking is connected)</span>
    </label>
  );
}
