# Parcours client — cas ultra concret

**Vous n'êtes pas en démo commerciale.** Vous êtes **Marie Dubois**, responsable import chez **RoulezBio SAS**
(import pneus et accessoires auto, ~8 conteneurs/mois, Odoo pour les commandes, Excel pour le « vrai coût »).

**Aujourd'hui, mardi 12 mars 2026.** L'expédition **MEDUSH2604417** (Ningbo → Le Havre, MSCU) est arrivée. Le transitaire
**Transitex** vient d'envoyer sa facture par mail. Votre patron vous demande : *« On peut encore vendre le pneu
205/55 à 13 € ou pas ? »*

Ce document est le **film de votre journée** dans FreightSight. Suivez les encarts **« Prochaine étape »** — c'est
votre fil conducteur. Durée réaliste : **30–45 min** la première fois.

---

## Préparer l'environnement (10 min, une seule fois)

```bash
cd /Users/pierre/Desktop/FreightSight
docker compose up -d --build          # API :8001 + Postgres + worker
cd frontend && npm run dev            # http://localhost:3000
docker compose ps                     # worker doit être « Up »
```

1. Ouvrir http://localhost:3000
2. **Créer une nouvelle organisation Clerk** (ex. `RoulezBio — test Marie`) — obligatoire pour avoir le bouton données d'exemple
3. Vous arrivez sur **Conteneurs**

---

## Le cast (ce que contient le jeu d'exemple)

| Élément | Détail |
|---------|--------|
| **Fournisseurs** | Zhejiang Kaiyuan Tyre (Chine) · Ningbo Hanwei Housewares |
| **PO-2026-014** | 1 000 pneus `TYR-20555R16-91V` à **10,00 € FOB** l'unité |
| **PO-2026-015** | 500 tapis EVA `MAT-EVA-6040-GY` à **20,00 € FOB** l'unité |
| **MSCU4821990** | 40' HC — **600 pneus + 500 tapis** — déchargé, **risque surestaries** |
| **TGHU7245081** | 40' HC — **400 pneus** — déjà sorti du terminal |
| **Coûts déjà saisis** | Fret maritime 3 000 € (expédition, au poids) · Camionnage 300 + 200 € |
| **Facture à déposer** | `docs/demo/fixtures/facture-transitex-demo.pdf` (Transitex, MSCU4821990) |

---

## Acte 1 · Le tableau de bord (5 min)

**Écran :** `/containers`

### Ce que vous faites
1. Cliquer **Charger des données d'exemple** (icône étincelle)
2. Lire la checklist **« Premiers pas »** (5 étapes — après le jeu d'exemple, 4 sont déjà cochées ; la 5ᵉ
   « Confirmer une facture » se valide à l'acte 4)
3. Lire l'encart bleu **« Prochaine étape »**

### Ce que vous devez voir
- **MSCU4821990** dans « À risque » ou dans **À traiter cette semaine** (dernier jour franc proche)
- KPI **FOB en cours** ~16 000 € sur les conteneurs actifs (MSCU seul porte l'essentiel)
- KPI **Ventilé** ~2 767 € sur MSCU (fret + camionnage déjà ventilés)

### Questions métier (comme un vrai client)
- *« Quel conteneur me coûte cher si je ne le sors pas cette semaine ? »* → MSCU
- *« Est-ce que j'ai déjà intégré la facture Transitex ? »* → pas encore (il manque THC, dédouanement…)

**Action :** cliquer **Ouvrir MSCU4821990** (encart ou ligne du tableau)

---

## Acte 2 · Le conteneur qui brûle (5 min)

**Écran :** `/container/{id}` — **MSCU4821990**

### En haut de page (sans scroller)
1. Badge **DISCHARGED** + risque surestaries (ambre)
2. **Dernier jour franc** affiché — notez la date
3. Encart **Prochaine étape** (souvent : déposer une facture, ou voir les coûts unitaires)

### Bandeau vert « Coût rendu par ligne »
C'est **la réponse à la question du patron**, avant même la facture Transitex :

| Ligne | FOB unitaire | Coût rendu unitaire (maintenant) |
|-------|--------------|----------------------------------|
| PO-2026-014 · pneu | **10,00 €** | **~11,52 €** |
| PO-2026-015 · tapis | **20,00 €** | **~23,71 €** |

### Réflexe dirigeant
> « Je croyais acheter le pneu à 10 €. En entrepôt c'est déjà 11,52 € **sans** la facture Transitex.
> À 13 € de vente, ma marge n'est pas 3 € — c'est plutôt **1,48 €**. »

### Explorer (optionnel, 3 min)
- Ouvrir **Ventilation détaillée** → changer la méthode du **fret maritime** (aperçu « et si ») → le coût unitaire bouge
- Replier **Suivi & dates** → vérifier date de déchargement vs dernier jour franc
- Replier **Chargements** → 600 pneus + 500 tapis dans ce conteneur

**Ne pas toucher** à « Ajouter un coût » pour l'instant — la facture PDF va arriver.

---

## Acte 3 · La commande fournisseur (3 min)

**Écran :** `/purchase-orders` → **PO-2026-014**

### Ce que vous vérifiez
- Fournisseur : Zhejiang Kaiyuan Tyre
- 1 000 pièces à 10 € — FOB total 10 000 €
- Colonne **Conteneurs** : MSCU + TGHU (répartition 600 / 400)

**Écran :** fiche PO-2026-014

- Totaux FOB → Ventilé → Coût rendu
- Encart **Prochaine étape** (souvent : facture ou conteneur)

### Question métier
- *« Ma commande est-elle bien répartie sur les bons conteneurs ? »* → oui, visible dans Chargements sur MSCU

---

## Acte 4 · La facture Transitex arrive (10 min)

**Écran :** `/invoices`

### Étape 4.1 — Dépôt
1. Encart **Déposer une facture**
2. Glisser `docs/demo/fixtures/facture-transitex-demo.pdf`
3. Attendre 3–10 s (le **worker** lit le PDF — page se rafraîchit)

### Étape 4.2 — Relecture
Ouvrir la facture → encart **Relire les lignes**

| Ligne extraite | Montant | Cible | Votre décision |
|----------------|---------|-------|----------------|
| Fret maritime | 3 000 € | MSCU4821990 | **Refuser** — déjà saisi (facture KN) |
| THC Le Havre | 275 € | MSCU4821990 | **Accepter** |
| Dédouanement | 130 € | MSCU4821990 | **Accepter** |
| Camionnage | 425 € | MSCU4821990 | **Refuser** — déjà saisi (Delcourt) |

> En vrai métier : on ne double pas un coût. FreightSight vous laisse **valider ligne par ligne**.

### Étape 4.3 — Confirmation
- Cliquer **Confirmer** (2 lignes acceptées)
- Encart vert → **Coûts unitaires · MSCU4821990**

---

## Acte 5 · La réponse au patron (5 min)

**Écran :** retour fiche **MSCU4821990** → bandeau vert coûts unitaires

### Chiffres attendus (après THC + dédouanement)

| Référence | FOB | Rendu **avant** Transitex | Rendu **après** Transitex |
|-----------|-----|---------------------------|---------------------------|
| Pneu PO-2026-014 | 10,00 € | ~11,52 € | **~11,77 €** (hausse modeste) |
| Tapis PO-2026-015 | 20,00 € | ~23,71 € | légère hausse aussi |

### Conclusion pour RoulezBio
> « Non, 13 € de vente ne tient plus si on veut 20 % de marge. Il faudrait plutôt **14,50 €** ou renégocier le FOB. »

### Suite logique dans l'outil (actes 6 à 10)

| Acte | Écran | Ce que vous vérifiez |
|------|-------|----------------------|
| **6** | `/reports` | Coût rendu par fournisseur · coût unitaire `TYR-20555R16-91V` · section **À risque maintenant** (MSCU) |
| **7** | `/reports/variance` | Souvent vide tant qu'aucun **estimé barème** n'a été remplacé par une facture — normal |
| **8** | `/purchase-orders` → PO-2026-014 | Ventilation split MSCU / TGHU · postes facturés 4/4 après Transitex |
| **9** | `/alerts` | Au moins **1 alerte** surestarie MSCU (cloche en haut à droite) |
| **10** | `/audit` | `Facture confirmée` avec n° FA-2026-0912 · statuts traduits · pas d'UUID bruts |

---

## Acte 11 · Le deuxième conteneur (5 min, optionnel)

**Écran :** `/container/{id}` — **TGHU7245081**

- Déjà **sorti du terminal** — risque faible
- 400 pneus seuls — autre profil de ventilation (part du fret maritime au poids)
- Comparez le **coût unitaire pneu** MSCU vs TGHU : même SKU, coût rendu différent selon ce qu'il y a dans le conteneur

**Question métier :**
- *« Pourquoi le même pneu n'a pas le même coût rendu selon le conteneur ? »* → le fret au poids se partage différemment

---

## Acte 12 · Paramètres & estimés (5 min, optionnel)

**Écran :** `/settings`

1. **Société** — devise EUR, jours francs surestaries (7 par défaut)
2. **Barèmes** — ajouter un barème FRET pour estimer *avant* la facture
3. Revenir sur MSCU → **Estimer avec les barèmes** → jauge « Postes facturés »

**Écran :** `/reports/variance` — souvent vide tant qu'aucun estimé n'a été **remplacé** par une facture. Normal.

---

## Acte 13 · Odoo (10 min, org séparée)

Si vous testez l'ERP : suivre `docs/demo-checklist.md` sur une **autre organisation** (pas RoulezBio test).

Sur MSCU, section repliable **Écriture dans l'ERP** → aperçu → brouillon → **Ouvrir dans Odoo**.

---

## Checklist « ai-je vraiment utilisé le produit ? »

Cochez mentalement :

- [ ] J'ai chargé les données et compris **quel conteneur est urgent**
- [ ] J'ai vu le **coût unitaire** FOB → rendu sur le pneu
- [ ] J'ai déposé une **facture PDF** et attendu l'extraction
- [ ] J'ai **refusé** des lignes en doublon et **confirmé** les bonnes
- [ ] J'ai constaté le **changement** de coût unitaire après confirmation
- [ ] J'ai ouvert une **commande** et un **rapport**
- [ ] J'ai vu une **alerte surestarie** sur MSCU (acte 9)
- [ ] J'ai consulté l'**historique** après confirmation (acte 10)
- [ ] (Optionnel) **Paramètres** / barèmes / Odoo

---

## Dépannage « comme un client bloqué »

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| Pas de bouton données d'exemple | Org déjà utilisée | Nouvelle org Clerk |
| Facture bloquée « Déposée » | Worker arrêté | `docker compose up -d worker` puis `docker compose logs -f worker` |
| 0 ligne extraite | PDF illisible ou worker down | Relancer worker ; réessayer le PDF démo |
| Coût unitaire inchangé après facture | Lignes refusées ou doublons seulement | Accepter au moins THC + dédouanement |
| Facture **rejetée** par erreur | Statut REJECTED | Bandeau ambre → **Remettre en relecture**, puis revalider les lignes |
| Re-upload bloqué « document déjà existant » | Même PDF déjà déposé | Rouvrir la facture rejetée (pas besoin de re-déposer le fichier) |
| **0 alerte** alors que MSCU est à risque | Org créée avant correctif alertes | Rafraîchir une page (sync auto) ou recharger le jeu sur une **nouvelle org** |
| Page **Écarts** vide | Pas d'estimé remplacé par facture | Normal — utiliser « Estimer avec les barèmes » puis confirmer une facture |
| Encart « Prochaine étape » absent | Cache navigateur | Hard refresh |

---

## Variante « client sans jeu d'exemple »

Si vous voulez vivre **l'import depuis zéro** (plus long, plus réaliste) :

1. Nouvelle org vide → checklist **Premiers pas** sur Conteneurs
2. `/imports/new` → fichier `backend/tests/fixtures/legacy_po_container.csv`
3. Créer conteneur, charger lignes, saisir un coût manuel
4. Puis facture Transitex

Durée : **1 h**. Le jeu d'exemple est là pour aller **droit au coût unitaire** en 30 min.

---

## Rejouer le parcours automatiquement (API)

```bash
cd backend && uv run python ../scripts/e2e_live_demo.py
```

Valide le même scénario sans UI (sample data → facture → hausse coût unitaire).
