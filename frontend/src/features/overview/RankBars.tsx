import Link from "next/link";

export type RankRow = { key: string; label: string; value: number; display: string; sub?: string; href?: string };

/**
 * Who weighs most, one hue, longest first. The categories have no order of their own, so the bars
 * are sorted and share a single colour: length is the only thing encoding the value, and each bar
 * carries its number at the tip.
 */
export default function RankBars({ rows, empty }: { rows: RankRow[]; empty: string }) {
  if (rows.length === 0) return <p className="text-sm text-slate-500">{empty}</p>;
  const max = Math.max(...rows.map((r) => r.value), 0) || 1;
  return (
    <ul className="space-y-3">
      {rows.map((r) => {
        const name = r.href ? (
          <Link href={r.href} className="truncate text-slate-800 hover:text-blue-700 hover:underline">{r.label}</Link>
        ) : (
          <span className="truncate text-slate-800">{r.label}</span>
        );
        return (
          <li key={r.key}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              {name}
              <span className="shrink-0 tabular-nums">
                <span className="font-medium text-slate-900">{r.display}</span>
                {r.sub ? <span className="ml-2 text-xs text-slate-400">{r.sub}</span> : null}
              </span>
            </div>
            <div className="mt-1.5 h-1.5">
              <div className="h-1.5 rounded-r-[4px] bg-viz-freight" style={{ width: `${Math.max((r.value / max) * 100, 1)}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
