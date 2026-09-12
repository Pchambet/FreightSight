# Démo commerciale — 15 minutes (parcours guidé)

**À distinguer de** `demo-checklist.md` : la checklist A valide le connecteur Odoo (recette technique).
Ce document est le **parcours vendeur** : montrer pourquoi un importateur gagne de l'argent.

Chaque écran affiche un encart **« Prochaine étape »** en haut : suivez-le pendant la démo — c'est le fil
conducteur pour le prospect comme pour vous. Sur `/containers`, la checklist **« Premiers pas »** guide
les orgs sans jeu d'exemple (import → chargement → facture → coût unitaire).

## Avant l'appel (5 min)

1. **Nouvelle organisation Clerk** vide (recommandé).
2. `docker compose up -d` (API `:8001`, Postgres, **worker** pour les factures) + `cd frontend && npm run dev` → http://localhost:3000
3. Connexion Clerk, création / sélection de l'org de démo.
4. **Conteneurs** → **Charger des données d'exemple** (bouton avec étincelle).
   - 2 conteneurs : `MSCU4821990` (à risque surestaries) + `TGHU7245081`
   - 2 commandes, fret ventilé au poids, camionnage par conteneur
5. Garder sous la main : `docs/demo/fixtures/facture-transitex-demo.pdf`
6. Odoo **optionnel** (scène 6). Pour Odoo, utiliser `demo-checklist.md` sur une autre org.

## Ce que tu vends en une phrase

> « Vous pricez en FOB. Le vrai coût par référence arrive à J+45. FreightSight ventile chaque facture sur
> vos conteneurs et lignes de commande, et prépare l'écriture Odoo — sans Excel, sans double saisie. »

---

## Parcours A → Z (suivre les boutons « Prochaine étape »)

| # | Écran | Bouton à cliquer | Ce que tu montres |
|---|---|---|---|
| 1 | `/containers` | **Ouvrir MSCU4821990** (ou « Coûts unitaires · MSCU… ») | KPIs, conteneur à risque surestaries |
| 2 | Fiche MSCU | **Voir les coûts unitaires** | FOB 10 € → rendu ~11,65 € (pneu) — *le chiffre qui fait tilt* |
| 3 | Même fiche, scroll | Bloc **Ventilation détaillée** (repliable) | « Et si » : changer la méthode fret → coût unitaire bouge |
| 4 | `/invoices` | **Déposer une facture** | Glisser `facture-transitex-demo.pdf` |
| 5 | Facture extraite | **Relire les lignes** | Vérifier fret, THC, dédouanement, camionnage sur MSCU |
| 6 | Après confirmation | **Coûts unitaires · MSCU4821990** | FOB 10 € → **13,91 €** (pneu) — impact facture réelle |
| 7 | `/reports` | **Coûts unitaires · MSCU…** ou **Écarts** | Vue agrégée ; page Écarts souvent vide (normal sans estimés) |
| 8 | Fiche MSCU (option Odoo) | Section **Écriture dans l'ERP** | Push brouillon → **Ouvrir dans Odoo** |

**Durée cible :** 12–15 min. **Ne pas tout montrer** : si le prospect accroche sur la marge, restez sur scènes 1–2–6.

---

## Scène 1 · Vue d'ensemble (1 min) — Conteneurs

**Où :** `/containers`

**Encart « Prochaine étape » :** pointe vers MSCU (surestaries) ou vers les factures à relire.

**Montre :**
- Tuiles **FOB en cours**, **Ventilé**, **À risque**, **Sans coût**
- (Repliable) **À traiter cette semaine**

**Tu dis :**
> « Dix conteneurs actifs : je vois tout de suite lequel va me coûter des surestaries et lequel n'a pas
> encore ses factures ventilées. »

**Valeur :** éviter une journée de demurrage = souvent **150–400 €/jour/conteneur**.

---

## Scène 2 · Le coût unitaire vrai (2 min) — Fiche MSCU4821990

**Où :** clic sur MSCU ou bouton **Coûts unitaires** de l'encart.

**Montre (en haut de page, sans scroller) :**
- Encart **Prochaine étape** → **Voir les coûts unitaires**
- Bandeau vert **Coût rendu par ligne** : pneu PO-2026-014 — FOB **10 €** → rendu **~11,65 €** (sample data)

**Tu dis :**
> « Ce pneu, vous le croyez à 10 €. Rendu entrepôt, c'est 11,65 €. Si vous le vendez 13 €, votre marge
> n'est pas 3 € — c'est 1,35 €. C'est ça que vous n'avez pas dans Odoo seul. »

**Valeur :** **marge / pricing** — le chiffre que le dirigeant comprend en 10 secondes.

---

## Scène 3 · Méthode de ventilation (1 min, optionnel)

**Où :** même fiche, section **Ventilation détaillée** (ouvrir le repliable si besoin).

**Montre :** basculer la méthode **Fret maritime** → le coût unitaire change.

**Tu dis :**
> « Une méthode par type de coût — fret au poids, douane à la valeur — et chaque centime est retrouvable
> ligne par ligne. »

---

## Scène 4 · La facture transitaire (4 min) — Factures

**Où :** `/invoices` → encart **Déposer une facture** (ou zone #depot).

**Fais :**
1. Glisser `docs/demo/fixtures/facture-transitex-demo.pdf`
2. Attendre l'extraction (quelques secondes)
3. Ouvrir la facture → encart **Relire les lignes**
4. Confirmer **THC + dédouanement** (évite les doublons avec le sample data sur fret/camionnage)
5. Après confirmation → **Coûts unitaires · MSCU4821990**

**Tu dis :**
> « La facture arrive en PDF. Rien n'entre sans votre validation. Chaque ligne est rattachée au conteneur.
> Plus de ressaisie dans Excel. »

**Valeur :** **temps ops** — 30–60 min de saisie par facture × N conteneurs/mois.

**Si l'extraction rate :** **Ajouter un coût** sur la fiche conteneur (section repliable) et dire que
l'extraction est en bêta, la ventilation fonctionne déjà.

---

## Scène 5 · Après la facture (2 min) — Retour MSCU

**Où :** bouton **Coûts unitaires · MSCU4821990** après confirmation.

**Montre :**
- Pneu : FOB 10 € → rendu **13,91 €** (après facture réelle)
- Tapis PO-2026-015 : 20 € → **28,50 €**
- Jauge **Postes facturés** sur la fiche (estimé → réel)

**Tu dis :**
> « Avant la facture, vous aviez une estimation au poids. Après, le vrai coût par référence — c'est ce que
> vous pricez ou ce que le DAF provisionne. »

**Page `/reports/variance` :** souvent vide sans estimés remplacés — le dire explicitement ; montrer plutôt
la jauge sur la fiche conteneur.

---

## Scène 6 · Odoo (2 min, si prospect Odoo)

**Où :** fiche conteneur → section repliable **Écriture dans l'ERP**.

**Montre :** aperçu → push brouillon → **Ouvrir dans Odoo** (lien direct).

**Tu dis :**
> « Votre comptable valide dans Odoo. On ne touche jamais à vos écritures validées. »

**Prérequis :** `demo-checklist.md` (org technique séparée si besoin).

---

## Scène 7 · Clôture (1 min)

| Question | Ce que ça chiffre |
|---|---|
| Combien de conteneurs / mois ? | Volume |
| Combien d'heures Excel + Odoo / conteneur ? | Gain temps |
| Une journée de surestaries = combien ? | Gain évité |
| Vous pricez au FOB ou au rendu ? | Urgence produit |

**Phrase de clôture :**
> « Je cherche 5 importateurs Odoo pour affiner ça avec eux. Est-ce que ça vaut 30 minutes pour voir si
> vos chiffres collent ? »

---

## Deux parcours selon le contexte

| | Démo commerciale (ce doc) | Recette Odoo (`demo-checklist.md`) |
|---|---|---|
| **Org** | Nouvelle org + données d'exemple | Org connectée Odoo fstest |
| **Focus** | Marge, factures, surestaries | Push landed cost brouillon |
| **Fil conducteur** | Encarts « Prochaine étape » | Checklist A1–A9 |

Enchaînement possible sur un même appel : **commercial d'abord**, **Odoo ensuite**.

---

## Dépannage rapide

| Problème | Solution |
|---|---|
| Pas de bouton « données d'exemple » | Org déjà remplie → nouvelle org Clerk |
| Pas d'encart « Prochaine étape » | Recharger la page (déploiement frontend) |
| Facture 0 ligne | Vérifier `docker compose ps` — le service `worker` doit tourner |
| Doublons fret/camionnage | Confirmer seulement THC + dédouanement sur la facture démo |
| Page Écarts vide | Normal sans estimés → montrer coûts unitaires sur MSCU |
| Pas de carte ERP | Paramètres → connecter Odoo |
