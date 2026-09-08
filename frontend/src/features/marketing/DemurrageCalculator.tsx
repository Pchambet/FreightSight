"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, Link2 } from "lucide-react";

/**
 * Order-of-magnitude demurrage for a 40' dry container, calendar days after free time,
 * from the 2026 public tariffs of the main carriers for BE / FR / NL. Detention (the
 * container not returned to the depot) and terminal storage come on top.
 */
const PORTS = {
  ANR: { label: "Anvers", tiers: [60, 95, 145] },
  LEH: { label: "Le Havre", tiers: [55, 85, 130] },
  RTM: { label: "Rotterdam", tiers: [65, 100, 150] },
  MRS: { label: "Marseille-Fos", tiers: [55, 85, 130] },
} as const;
type PortCode = keyof typeof PORTS;

function perContainer(days: number, tiers: readonly number[]): number {
  let total = 0;
  for (let d = 1; d <= days; d++) total += d <= 5 ? tiers[0] : d <= 10 ? tiers[1] : tiers[2];
  return total;
}

const eur = (n: number) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

export default function DemurrageCalculator() {
  // Shareable state: /?port=ANR&c=3&d=6#calculateur (read once, at first render)
  const q = useSearchParams();
  const qp = q.get("port");
  const qc = Number(q.get("c"));
  const qd = Number(q.get("d"));
  const [port, setPort] = useState<PortCode>(qp && qp in PORTS ? (qp as PortCode) : "ANR");
  const [containers, setContainers] = useState(qc >= 1 && qc <= 200 ? qc : 3);
  const [days, setDays] = useState(qd >= 1 && qd <= 60 ? qd : 6);
  const [copied, setCopied] = useState(false);

  const tiers = PORTS[port].tiers;
  const one = useMemo(() => perContainer(days, tiers), [days, tiers]);
  const total = one * containers;

  async function share() {
    const url = new URL(window.location.href);
    url.search = new URLSearchParams({ port, c: String(containers), d: String(days) }).toString();
    url.hash = "calculateur";
    window.history.replaceState(null, "", url.toString());
    try { await navigator.clipboard.writeText(url.toString()); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* clipboard blocked: the URL bar already holds the link */ }
  }

  const field = "w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500 outline-none";
  const label = "block text-xs font-medium text-slate-400 mb-1";

  return (
    <div className="grid gap-8 md:grid-cols-5 items-start">
      <div className="md:col-span-2 grid gap-4">
        <div>
          <label className={label} htmlFor="dd-port">Port de déchargement</label>
          <select id="dd-port" className={field} value={port} onChange={(e) => setPort(e.target.value as PortCode)}>
            {Object.entries(PORTS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={label} htmlFor="dd-c">Conteneurs</label>
            <input id="dd-c" type="number" min={1} max={200} inputMode="numeric" className={field} value={containers} onChange={(e) => setContainers(Math.max(1, Math.min(200, Number(e.target.value) || 1)))} />
          </div>
          <div>
            <label className={label} htmlFor="dd-d">Jours au-delà du free time</label>
            <input id="dd-d" type="number" min={1} max={60} inputMode="numeric" className={field} value={days} onChange={(e) => setDays(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} />
          </div>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          Ordre de grandeur pour un 40&apos; dry, jours calendaires après le free time (souvent 7 jours), barèmes publics 2026 des compagnies :
          {" "}{tiers[0]} € les 5 premiers jours, {tiers[1]} € du 6<sup>e</sup> au 10<sup>e</sup>, {tiers[2]} € au-delà. Hors détention et stockage terminal, qui s&apos;ajoutent.
        </p>
      </div>
      <div className="md:col-span-3 bg-slate-800/60 border border-slate-700 rounded-lg p-6">
        <div className="text-xs font-medium uppercase tracking-wider text-slate-400">Surestaries estimées</div>
        <div className="mt-1 text-5xl font-semibold tracking-tight text-white tabular-nums">{eur(total)}</div>
        <div className="mt-2 text-sm text-slate-300">
          soit {eur(one)} par conteneur, {days} jour{days > 1 ? "s" : ""} de trop à {PORTS[port].label}. Découvert, en général, sur la facture du transitaire six semaines plus tard.
        </div>
        <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
          <div className="bg-slate-900/60 rounded-md p-3"><div className="text-slate-400 text-xs">Par jour, au tarif du jour {days}</div><div className="text-white tabular-nums font-medium">{eur((days <= 5 ? tiers[0] : days <= 10 ? tiers[1] : tiers[2]) * containers)}</div></div>
          <div className="bg-slate-900/60 rounded-md p-3"><div className="text-slate-400 text-xs">Si vous l&apos;aviez su à J-3</div><div className="text-white tabular-nums font-medium">{eur(perContainer(Math.max(0, days - 3), tiers) * containers)}</div></div>
          <div className="bg-slate-900/60 rounded-md p-3"><div className="text-slate-400 text-xs">Évitable</div><div className="text-emerald-400 tabular-nums font-medium">{eur(total - perContainer(Math.max(0, days - 3), tiers) * containers)}</div></div>
        </div>
        <button type="button" onClick={share} className="mt-5 inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white">
          {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Link2 className="w-4 h-4" />}{copied ? "Lien copié" : "Copier le lien vers cette simulation"}
        </button>
      </div>
    </div>
  );
}
