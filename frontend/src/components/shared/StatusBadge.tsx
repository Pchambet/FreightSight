import { CONTAINER_STATUS_LABEL, isContainerStatus } from "@/lib/domain";

const STYLES: Record<string, string> = {
  PENDING: "bg-slate-100 text-slate-700 ring-slate-500/20",
  IN_TRANSIT: "bg-blue-50 text-blue-700 ring-blue-600/20",
  DISCHARGED: "bg-amber-50 text-amber-700 ring-amber-600/20",
  DELIVERED: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
};

export function StatusBadge({ status }: { status: string }) {
  const known = isContainerStatus(status);
  const label = known ? CONTAINER_STATUS_LABEL[status] : "Unknown";
  const style = known ? STYLES[status] : "bg-slate-100 text-slate-500 ring-slate-500/20";
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}>
      {label}
    </span>
  );
}
