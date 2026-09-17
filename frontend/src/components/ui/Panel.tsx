/**
 * The surface a chart or a figure sits on. Unlike `Card` (components/layout/AppShell) it does not
 * clip its content: a chart's tooltip is allowed to rise above the panel's own edge.
 */
export default function Panel({
  title,
  subtitle,
  right,
  children,
  className,
  id,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`bg-white rounded-xl border border-slate-200 shadow-card ${className ?? ""}`}>
      {title ? (
        <div className="px-5 pt-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
            {subtitle ? <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p> : null}
          </div>
          {right ? <div className="shrink-0 text-xs">{right}</div> : null}
        </div>
      ) : null}
      <div className="p-5">{children}</div>
    </section>
  );
}
