import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { ArrowRight, Check, FileSpreadsheet, Receipt, Sigma } from "lucide-react";
import DemurrageCalculator from "@/features/marketing/DemurrageCalculator";
import { site } from "@/lib/site";

export const metadata: Metadata = {
  title: { absolute: "FreightSight · Coût de revient rendu pour les PME importatrices" },
  description:
    "FreightSight ventile le fret, la douane et les frais de terminal sur chaque ligne de commande, conteneur par conteneur, à partir de vos factures. Estimé à l'embarquement, exact à la facture.",
};

const btnPrimary = "inline-flex items-center gap-2 bg-slate-900 hover:bg-slate-800 text-white text-sm font-medium py-2.5 px-5 rounded-md";
const btnGhost = "inline-flex items-center gap-2 text-sm font-medium py-2.5 px-5 rounded-md border border-slate-300 hover:bg-slate-50";

export default async function LandingPage({ searchParams }: { searchParams: Promise<{ preview?: string }> }) {
  const [a, sp] = await Promise.all([auth(), searchParams]);
  if (a.isAuthenticated && a.orgId && !sp.preview) redirect(site.appHome);

  return (
    <main>
      {/* Hero */}
      <section className="max-w-6xl mx-auto px-5 pt-16 pb-12 grid gap-10 lg:grid-cols-12 items-center">
        <div className="lg:col-span-6">
          <div className="text-xs font-medium uppercase tracking-wider text-blue-700">Pour les PME importatrices · 5 à 60 conteneurs par mois</div>
          <h1 className="mt-4 text-4xl md:text-5xl font-semibold tracking-tight leading-[1.05] text-balance">
            Le coût de revient rendu de vos importations, par commande et par SKU.
          </h1>
          <p className="mt-5 text-lg text-slate-600 leading-relaxed max-w-xl">
            FreightSight ventile le fret, la douane et les frais de terminal sur chaque ligne de commande, conteneur par conteneur, à partir de vos factures. Estimé à l&apos;embarquement, exact à la facture, écart affiché. Sans changer d&apos;ERP.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <a href={site.bookingUrl} className={btnPrimary}>Réserver 20 minutes <ArrowRight className="w-4 h-4" /></a>
            <Link href="#produit" className={btnGhost}>Voir comment ça marche</Link>
          </div>
          <ul className="mt-7 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-500">
            {["Hébergé en Europe", "Données isolées par société", "Aucun modèle entraîné sur vos données"].map((t) => (
              <li key={t} className="inline-flex items-center gap-1.5"><Check className="w-4 h-4 text-emerald-600" />{t}</li>
            ))}
          </ul>
        </div>
        <div className="lg:col-span-6">
          <figure className="rounded-xl border border-slate-200 shadow-[0_20px_60px_-20px_rgba(15,23,42,.25)] overflow-hidden bg-white">
            <Image src="/landing/ventilation.jpg" alt="Tableau FreightSight : coût rendu par ligne de commande pour un conteneur, avec le coût unitaire et la part de fret maritime" width={800} height={380} priority />
            <figcaption className="px-4 py-2.5 text-xs text-slate-500 border-t border-slate-100">Un conteneur, trois commandes, 3 000 € de fret ventilés au poids. Capture de l&apos;application, données d&apos;exemple.</figcaption>
          </figure>
        </div>
      </section>

      {/* Problem */}
      <section className="border-y border-slate-200 bg-slate-50">
        <div className="max-w-6xl mx-auto px-5 py-12 grid gap-8 md:grid-cols-3">
          {[
            ["J+30 à J+60", "C'est quand arrivent les factures du transitaire et les surestaries. Le prix de vente, lui, a été fixé sur le FOB."],
            ["70 à 150 € par jour", "Surestaries par conteneur après le free time à Anvers ou au Havre. Trois conteneurs oubliés une semaine coûtent le prix d'une palette."],
            ["2 à 3 jours par mois", "Passés à recoller factures transitaire, DAU et bons de commande dans Excel, avec un prorata à la valeur qui est faux pour tout ce qui est lourd ou volumineux."],
          ].map(([n, t]) => (
            <div key={n}>
              <div className="text-3xl font-semibold tracking-tight tabular-nums">{n}</div>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed">{t}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Product */}
      <section id="produit" className="max-w-6xl mx-auto px-5 py-20 scroll-mt-20">
        <h2 className="text-3xl font-semibold tracking-tight text-balance max-w-2xl">Une facture, trois conteneurs, cinq commandes : ventilée au centime, et auditable.</h2>
        <p className="mt-4 text-slate-600 max-w-2xl leading-relaxed">Chaque coût est rattaché à un seul périmètre, expédition, conteneur, commande ou ligne, et redescend jusqu&apos;aux lignes chargées selon la méthode que vous choisissez. Les droits sont calculés en seconde passe sur la valeur CIF, comme en douane. Ce qui ne peut pas être ventilé est signalé, jamais deviné.</p>

        <div className="mt-12 grid gap-10 lg:grid-cols-2 items-start">
          <figure>
            <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
              <Image src="/landing/signale.jpg" alt="Avertissement : base manquante sur une ligne, 1 200 € non ventilés, avec les totaux FOB, alloué, TVA import, rendu et non alloué" width={900} height={113} />
            </div>
            <figcaption className="mt-3 text-sm text-slate-600"><span className="font-medium text-slate-900">Ce qui ne peut pas être ventilé est signalé, jamais deviné.</span> Ici une ligne sans taux de droits : les 1 200 € de douane restent visibles en « non alloué » au lieu d&apos;être répartis au hasard.</figcaption>
          </figure>
          <figure>
            <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
              <Image src="/landing/cout-unitaire.jpg" alt="Coût unitaire par ligne de commande, la commande étant répartie sur deux conteneurs" width={800} height={318} />
            </div>
            <figcaption className="mt-3 text-sm text-slate-600"><span className="font-medium text-slate-900">Le coût unitaire par SKU, même quand la commande est répartie sur deux conteneurs.</span> Prêt pour l&apos;écriture landed cost de l&apos;ERP et pour la marge par référence.</figcaption>
          </figure>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {[
            [FileSpreadsheet, "1 · Importez vos commandes", "CSV ou Excel, export Sage, EBP ou Odoo. Les accents, les points-virgules et les « 12 500,50 » passent. Le mapping des colonnes est mémorisé, chaque ligne en erreur est expliquée avant d'écrire quoi que ce soit."],
            [Receipt, "2 · Enregistrez les coûts", "Fret, THC, droits, drayage, surestaries, en euros ou en dollars au taux BCE du jour de facture. Un coût, un périmètre, une méthode. Bientôt : la facture PDF lue pour vous, avec validation avant écriture."],
            [Sigma, "3 · Lisez le coût rendu", "Par conteneur, par commande, par ligne, avec le coût unitaire et la part de chaque type de frais. La TVA import est suivie pour la trésorerie et exclue du coût de revient."],
          ].map(([Icon, h, t]) => {
            const I = Icon as typeof FileSpreadsheet;
            return (
              <div key={h as string} className="rounded-lg border border-slate-200 p-5">
                <I className="w-5 h-5 text-blue-700" />
                <h3 className="mt-3 font-semibold">{h as string}</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">{t as string}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Calculator */}
      <section id="calculateur" className="bg-slate-900 text-white scroll-mt-20">
        <div className="max-w-6xl mx-auto px-5 py-20">
          <h2 className="text-3xl font-semibold tracking-tight text-balance max-w-2xl">Combien coûte un conteneur oublié à Anvers&nbsp;?</h2>
          <p className="mt-4 text-slate-300 max-w-2xl leading-relaxed">Le suivi de conteneurs ne vaut que par les euros qu&apos;il évite. FreightSight calcule le dernier jour franc de chaque conteneur et vous prévient à J-3, avec le montant en jeu.</p>
          <div className="mt-10"><Suspense fallback={null}><DemurrageCalculator /></Suspense></div>
        </div>
      </section>

      {/* Honesty */}
      <section className="max-w-6xl mx-auto px-5 py-20">
        <div className="grid gap-10 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Ce qui est disponible aujourd&apos;hui</h2>
            <ul className="mt-5 space-y-2.5 text-sm text-slate-700">
              {[
                "Import CSV et Excel avec validation ligne par ligne",
                "Commandes réparties sur plusieurs conteneurs, conteneurs multi-commandes",
                "Cinq méthodes de ventilation, droits en seconde passe sur la base CIF",
                "Multi-devises au taux BCE figé à la date de facture",
                "Coût rendu et coût unitaire par ligne, par conteneur, par commande",
                "Suivi manuel des conteneurs avec dernier jour franc et niveau de risque",
                "Comptes par société, isolation des données garantie en base",
              ].map((t) => <li key={t} className="flex gap-2.5"><Check className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" />{t}</li>)}
            </ul>
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Ce qui se construit avec les design partners</h2>
            <ul className="mt-5 space-y-2.5 text-sm text-slate-700">
              {[
                "Suivi automatique des conteneurs (événements, ETA, dernier jour franc) et alertes par e-mail",
                "Lecture des factures transitaire PDF, chaque ligne validée par vous avant d'entrer dans les coûts",
                "Estimé à l'embarquement, recalé à la facture, écart par commande",
                "Connecteur Odoo, export Pennylane, interface en français",
              ].map((t) => <li key={t} className="flex gap-2.5"><span className="w-4 h-4 mt-0.5 rounded-full border border-slate-300 shrink-0" />{t}</li>)}
            </ul>
            <p className="mt-5 text-sm text-slate-500">Pas de « temps réel » : les factures arrivent à J+30, les surestaries à J+60. Le produit vend un chiffre estimé tout de suite, exact à la facture, et l&apos;écart entre les deux.</p>
          </div>
        </div>
      </section>

      {/* Design partner */}
      <section id="design-partner" className="border-y border-slate-200 bg-slate-50 scroll-mt-20">
        <div className="max-w-6xl mx-auto px-5 py-16 grid gap-10 lg:grid-cols-12 items-center">
          <div className="lg:col-span-7">
            <div className="text-xs font-medium uppercase tracking-wider text-blue-700">Programme design partner · 5 places</div>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-balance">Huit semaines gratuites sur vos vrais dossiers, puis −50 % pendant douze mois.</h2>
            <div className="mt-6 grid gap-6 sm:grid-cols-2 text-sm">
              <div>
                <div className="font-semibold">Ce qu&apos;on vous demande</div>
                <ul className="mt-2 space-y-1.5 text-slate-600">
                  <li>Une heure par semaine avec le fondateur</li>
                  <li>Dix factures transitaire et cinq commandes, anonymisées si besoin</li>
                  <li>Un retour franc sur ce qui est juste et ce qui ne l&apos;est pas</li>
                </ul>
              </div>
              <div>
                <div className="font-semibold">Ce que vous recevez</div>
                <ul className="mt-2 space-y-1.5 text-slate-600">
                  <li>Votre coût rendu par SKU, réconcilié avec votre Excel</li>
                  <li>Un accès fondateur et votre mot sur la feuille de route</li>
                  <li>Le tarif partenaire, figé, quand la facturation démarre</li>
                </ul>
              </div>
            </div>
          </div>
          <div className="lg:col-span-5 flex flex-col gap-3">
            <a href={site.bookingUrl} className={btnPrimary + " justify-center"}>Réserver 20 minutes <ArrowRight className="w-4 h-4" /></a>
            <Link href="/design-partner" className={btnGhost + " justify-center"}>Lire le one-pager</Link>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="tarifs" className="max-w-6xl mx-auto px-5 py-20 scroll-mt-20">
        <h2 className="text-3xl font-semibold tracking-tight">Tarifs</h2>
        <p className="mt-3 text-slate-600 max-w-2xl">Par conteneur suivi et par mois. La lecture de factures est dans tous les plans. Tarifs indicatifs, figés avec les premiers clients.</p>
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          {[
            ["Starter", "299 €", "10 conteneurs par mois", ["Import CSV / XLSX", "Ventilation et coût par SKU", "Lecture de factures", "Alertes dernier jour franc"]],
            ["Growth", "499 €", "40 conteneurs par mois", ["Tout Starter", "Connecteur Odoo", "5 utilisateurs", "Estimé → réel par commande"]],
            ["Scale", "999 €", "150 conteneurs par mois", ["Tout Growth", "Multi-entité", "API et webhooks", "Pennylane / Cegid"]],
          ].map(([name, price, vol, feats]) => (
            <div key={name as string} className={`rounded-lg border p-6 ${name === "Growth" ? "border-slate-900" : "border-slate-200"}`}>
              <div className="font-semibold">{name as string}</div>
              <div className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">{price as string}<span className="text-sm font-normal text-slate-500"> / mois</span></div>
              <div className="text-sm text-slate-500">{vol as string}</div>
              <ul className="mt-4 space-y-1.5 text-sm text-slate-700">
                {(feats as string[]).map((f) => <li key={f} className="flex gap-2"><Check className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" />{f}</li>)}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-slate-500">Dépassement : 8 à 12 € par conteneur suivi au-delà du plan. Un incident de surestaries évité vaut 2 à 5 k€ ; un point de marge retrouvé sur 5 M€ d&apos;achats vaut 50 k€ par an.</p>
      </section>
    </main>
  );
}
