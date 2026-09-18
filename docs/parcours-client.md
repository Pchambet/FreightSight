# Parcours client — cas ultra concret

**Vous n'êtes pas en démo commerciale.** Vous êtes **Marie Dubois**, responsable import chez **RoulezBio SAS**
(import pneus et accessoires auto, ~8 conteneurs/mois, Odoo pour les commandes, Excel pour le « vrai coût »).

**Aujourd'hui.** L'expédition **MEDUSH2604417** (Ningbo → Le Havre, MSCU) vient d'être déchargée. Le
transitaire **Transitex** envoie sa facture par mail. Votre patron vous demande : *« On peut encore vendre
le pneu 205/55 à 20 € ou pas ? »*

Ce document est le **film de votre journée** dans FreightSight. Suivez les encarts **« Prochaine étape »**
— c'est votre fil conducteur. Durée réaliste : **30–45 min** la première fois. Toutes les dates du jeu
d'exemple sont calculées par rapport au jour où vous le chargez, donc « aujourd'hui » est toujours vrai,
quelle que soit la date à laquelle vous suivez ce parcours.

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
| **Fournisseurs** | Zhejiang Kaiyuan Tyre Co. (Chine) · Ningbo Hanwei Housewares (Chine) |
| **PO-2026-014** | 1 950 pneus tourisme `TYR-20555R16-91V` (« Pneu tourisme 205/55 R16 91V ») à **14,00 € FOB** l'unité, droit de douane 4,5 % (HS 4011.10) |
| **PO-2026-015** | 500 tapis EVA `MAT-EVA-6040-GY` (« Tapis de sol EVA 60×40 gris ») à **20,00 € FOB** l'unité, droit de douane 6,5 % (HS 3926.90) |
| **MSCU4821990** | 40' HC — **750 pneus + 500 tapis** (FOB 20 500,00 €) — déchargé, **risque surestaries** |
| **TGHU7245081** | 40' HC — **1 200 pneus** (FOB 16 800,00 €) — déjà sorti du terminal |
| **Barèmes déjà en place** | fret maritime, THC, dédouanement, camionnage (un montant par conteneur) et surestaries (85 €/jour) — Paramètres → Barèmes |
| **Coûts sur les deux conteneurs, avant toute facture** | uniquement des **estimés** issus de ces barèmes — rien de réel encore |
| **Facture à déposer** | `docs/demo/fixtures/facture-transitex-demo.pdf` (Transitex, MSCU4821990 uniquement) |

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
- KPI **FOB en cours** ~37 300 € sur les conteneurs actifs (20 500 € MSCU + 16 800 € TGHU)
- KPI **Ventilé** : les estimés de fret/THC/dédouanement/camionnage/droits sont déjà comptés — ce n'est
  pas 0, mais ce n'est pas encore une facture non plus

### Questions métier (comme un vrai client)
- *« Quel conteneur me coûte cher si je ne le sors pas cette semaine ? »* → MSCU
- *« Est-ce que j'ai déjà intégré la facture Transitex ? »* → pas encore : les chiffres actuels sont des
  estimés par barème, la facture va les remplacer un par un

**Action :** cliquer **Ouvrir MSCU4821990** (encart ou ligne du tableau)

---

## Acte 2 · Le conteneur qui brûle (5 min)

**Écran :** `/container/{id}` — **MSCU4821990**

### En haut de page (sans scroller)
1. Badge **DISCHARGED** + risque surestaries (ambre)
2. **Dernier jour franc** affiché — notez la date
3. Encart **Prochaine étape** (souvent : déposer une facture, ou voir les coûts unitaires)

### Bandeau vert « Coût rendu par ligne »
C'est **la réponse à la question du patron**, avant même la facture Transitex — déjà avec les droits de
douane dedans, puisque ce sont des barèmes, pas juste le fret :

| Ligne | FOB unitaire | Coût rendu unitaire (estimé, avant facture) |
|-------|--------------|----------------------------------------------|
| PO-2026-014 · pneu | **14,00 €** | **~17,72 €** |
| PO-2026-015 · tapis | **20,00 €** | **~25,71 €** |

### Réflexe dirigeant
> « Je croyais acheter le pneu à 14 €. En entrepôt c'est déjà 17,72 € **avant même** la facture Transitex,
> droits de douane compris. À 20 € de vente, ma marge n'est pas 6 € — c'est plutôt **2,15 €**. »

### Explorer (optionnel, 3 min)
- Ouvrir **Ventilation détaillée** → changer la méthode du **fret maritime** (aperçu « et si ») → le coût unitaire bouge
- Replier **Suivi & dates** → vérifier date de déchargement vs dernier jour franc
- Replier **Chargements** → 750 pneus + 500 tapis dans ce conteneur

**Ne pas toucher** à « Ajouter un coût » ni à « Estimer avec les barèmes » pour l'instant — les estimés
existent déjà, et la facture PDF va arriver.

---

## Acte 3 · La commande fournisseur (3 min)

**Écran :** `/purchase-orders` → **PO-2026-014**

### Ce que vous vérifiez
- Fournisseur : Zhejiang Kaiyuan Tyre Co.
- 1 950 pièces à 14 € — FOB total 27 300 €
- Colonne **Conteneurs** : MSCU + TGHU (répartition 750 / 1 200)

**Écran :** fiche PO-2026-014

- Totaux FOB → Ventilé → Coût rendu
- Encart **Prochaine étape** (souvent : facture ou conteneur)

### Question métier
- *« Ma commande est-elle bien répartie sur les bons conteneurs ? »* → oui, visible dans Chargements sur MSCU et TGHU

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
| Fret maritime | 3 915,40 € | MSCU4821990 | **Accepter** |
| THC Le Havre | 268,00 € | MSCU4821990 | **Accepter** |
| Dédouanement | 142,50 € | MSCU4821990 | **Accepter** |
| Camionnage | 396,00 € | MSCU4821990 | **Accepter** |
| Droits de douane | 1 336,89 € | MSCU4821990 | **Accepter** |

> Contrairement à une saisie manuelle, ici **rien ne fait doublon** : le conteneur ne porte que des
> estimés par barème, jamais un coût déjà réel. Vous pouvez valider **toute la facture d'un bloc** — la
> facture remplace chaque estimé un pour un, elle ne s'ajoute pas dessus.

### Étape 4.3 — Confirmation
- Cliquer **Confirmer** (5 lignes acceptées)
- Encart vert → **Coûts unitaires · MSCU4821990**

---

## Acte 5 · La réponse au patron (5 min)

**Écran :** retour fiche **MSCU4821990** → bandeau vert coûts unitaires

### Chiffres attendus (après la facture)

| Référence | FOB | Rendu **estimé** (avant Transitex) | Rendu **réel** (après Transitex) |
|-----------|-----|-------------------------------------|-------------------------------------|
| Pneu PO-2026-014 | 14,00 € | ~17,72 € | **17,98 €** |
| Tapis PO-2026-015 | 20,00 € | ~25,71 € | **26,16 €** |

Jauge **Postes facturés** : **5/5**, 100 % — plus aucun estimé sur ce conteneur.

### Conclusion pour RoulezBio
> « À 20 € de vente, la marge tient tout juste à 1,86 €. Il faudrait plutôt **22 €**, ou renégocier le
> FOB avec Zhejiang Kaiyuan. »

### Suite logique dans l'outil (actes 6 à 10)

| Acte | Écran | Ce que vous vérifiez |
|------|-------|----------------------|
| **6** | `/reports` | Coût rendu par fournisseur · coût unitaire `TYR-20555R16-91V` · section **À risque maintenant** (MSCU) · tarif surestaries 85 €/jour |
| **7** | `/reports/variance` (mois en cours) | Estimé 5 642,50 € → réel 6 058,79 € → écart **+416,29 €**, détaillé par type de coût (camionnage en baisse de 54 €, le reste en hausse) |
| **8** | `/purchase-orders` → PO-2026-014 | Ventilation split MSCU / TGHU · postes facturés 5/5 sur MSCU après Transitex, encore estimés sur TGHU |
| **9** | `/alerts` | Au moins **1 alerte** surestarie MSCU (cloche en haut à droite) |
| **10** | `/audit` | `Facture confirmée` avec n° FA-2026-0912 · statuts traduits · pas d'UUID bruts |

---

## Acte 11 · Le deuxième conteneur (5 min, optionnel)

**Écran :** `/container/{id}` — **TGHU7245081**

- Déjà **sorti du terminal** — risque plus faible
- 1 200 pneus seuls — autre profil de ventilation (mix pneus/tapis différent, fret et droits calculés sur
  ce seul chargement)
- Comparez le **coût unitaire pneu** MSCU (17,98 €, réel) vs TGHU (~18,40 €, encore estimé — cette
  facture ne concerne que MSCU) : même SKU, coût rendu différent selon le conteneur **et** selon que la
  facture est arrivée ou non

### Question métier
- *« Pourquoi le même pneu n'a pas le même coût rendu selon le conteneur ? »* → le mix de la cargaison et
  le fret se répartissent différemment, et TGHU n'a pas encore reçu sa facture réelle

---

## Acte 12 · Paramètres & barèmes (5 min, optionnel)

**Écran :** `/settings`

1. **Société** — devise EUR, jours francs surestaries (7 par défaut sur ce jeu d'exemple)
2. **Barèmes** — ceux du jeu d'exemple sont déjà là (fret, THC, dédouanement, camionnage, surestaries) ;
   montrez comment on en ajouterait un nouveau (ex. assurance) sans avoir besoin de relancer une
   estimation sur MSCU ou TGHU — leurs estimés existent déjà
3. **Ne pas cliquer** « Estimer avec les barèmes » sur MSCU ou TGHU dans cette démo : ça ne changerait
   rien aux estimés déjà en place, mais ajouterait une estimation de surestaries parasite tant que le
   moteur d'estimation ne sait pas exclure ce type de coût — limitation connue du produit, pas de ce jeu
   de données

---

## Acte 13 · Odoo (10 min, org séparée)

Si vous testez l'ERP : suivre `docs/demo-checklist.md` sur une **autre organisation** (pas RoulezBio test)
— le script `odoo_seed.py` crée son propre produit et fournisseur pour cette recette technique.

Sur le conteneur créé pour cette recette, section repliable **Écriture dans l'ERP** → aperçu → brouillon
→ **Ouvrir dans Odoo**.

---

## Checklist « ai-je vraiment utilisé le produit ? »

Cochez mentalement :

- [ ] J'ai chargé les données et compris **quel conteneur est urgent**
- [ ] J'ai vu le **coût unitaire estimé** FOB → rendu sur le pneu, droits de douane compris
- [ ] J'ai déposé une **facture PDF** et attendu l'extraction
- [ ] J'ai **confirmé toute la facture** sans crainte de doublon (tout était estimé)
- [ ] J'ai constaté le **changement** de coût unitaire, estimé → réel, avec un écart non nul
- [ ] J'ai ouvert une **commande** et le rapport d'écarts du mois
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
| Une ligne signalée comme doublon | Un coût réel a été ajouté à la main sur ce conteneur entre-temps | Vérifier l'historique ; sur un conteneur tout juste chargé du jeu d'exemple, ça ne devrait pas arriver |
| Facture **rejetée** par erreur | Statut REJECTED | Bandeau ambre → **Remettre en relecture**, puis revalider les lignes |
| Re-upload bloqué « document déjà existant » | Même PDF déjà déposé | Rouvrir la facture rejetée (pas besoin de re-déposer le fichier) |
| **0 alerte** alors que MSCU est à risque | Org créée avant correctif alertes | Rafraîchir une page (sync auto) ou recharger le jeu sur une **nouvelle org** |
| Page **Écarts** vide | Facture pas confirmée, ou mois affiché ≠ mois en cours | Confirmer la facture (acte 4), puis vérifier que le sélecteur de mois est sur le mois en cours |
| Encart « Prochaine étape » absent | Cache navigateur | Hard refresh |
| Facture fixture datée de longtemps | Fichier statique jamais régénéré | `backend/.venv/bin/python docs/demo/fixtures/generate_invoice.py` |

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

Valide le même scénario sans UI (sample data → facture → hausse coût unitaire). Pour l'exactitude des
chiffres cités dans ce document, voir plutôt `backend/tests/test_demo_story.py`, qui pin chaque montant à
la décimale.
