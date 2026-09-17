# Démo commerciale — 12 minutes (parcours guidé)

**À distinguer de** `demo-checklist.md` : la checklist A valide le connecteur Odoo (recette technique,
organisation séparée). Ce document est le **parcours vendeur** : montrer pourquoi un importateur de
pneus gagne de l'argent.

Chaque écran affiche un encart **« Prochaine étape »** en haut : suivez-le pendant la démo — c'est le fil
conducteur pour le prospect comme pour vous. Sur `/containers`, la checklist **« Premiers pas »** guide
les orgs sans jeu d'exemple (import → chargement → facture → coût unitaire).

**Tous les chiffres de ce document sont vérifiés par un test automatisé** :
`backend/tests/test_demo_story.py`, qui charge le jeu d'exemple et confirme la facture par l'API réelle
et échoue si l'un d'eux dérive. Si l'écran contredit ce document, c'est soit un bug d'affichage (front),
soit ce document qui n'a pas été régénéré après un changement du moteur — jamais une erreur d'arithmétique
à corriger à la main.

## Avant l'appel (5 min)

1. **Nouvelle organisation Clerk** vide (recommandé — une org déjà remplie n'a pas le bouton
   « données d'exemple »).
2. Vérifier que tout tourne **avant de rejoindre l'appel**, pas en scène 4 en direct :
   ```bash
   docker compose up -d                          # API :8001, Postgres, worker (factures, alertes)
   docker compose ps                             # api, db, worker : Up
   curl -sf http://localhost:8001/healthz && echo OK
   cd frontend && npm run dev                    # http://localhost:3000
   ```
3. Connexion Clerk, création / sélection de l'org de démo.
4. **Conteneurs** → **Charger des données d'exemple** (bouton avec étincelle).
   - 2 conteneurs : `MSCU4821990` (à risque surestaries) + `TGHU7245081` (déjà sorti)
   - 2 commandes RoulezBio : 1 950 pneus tourisme 205/55 R16 (14,00 € FOB), 500 tapis de sol EVA
     (20,00 € FOB)
   - Fret, THC, dédouanement et camionnage sont déjà **estimés** (barèmes) sur les deux conteneurs —
     rien à ajouter avant la facture.
5. Garder sous la main : `docs/demo/fixtures/facture-transitex-demo.pdf` (régénérée il y a peu — si elle
   a plus de ~2 mois, relancez `backend/.venv/bin/python docs/demo/fixtures/generate_invoice.py`).
6. **Ne cliquez pas sur « Estimer avec les barèmes »** pendant la démo : les estimés existent déjà
   (voir 4.). Un second clic ne changerait rien à freight/THC/dédouanement/camionnage/droits (déjà
   présents sur le conteneur), mais ajouterait une estimation de surestaries parasite — un barème
   DEMURRAGE existe pour le rapport « surestaries évitées » (scène 7), et `estimate_container` ne sait
   pas encore que la surestarie n'est pas un coût de revient. Comportement du produit, pas de ce jeu de
   données ; à corriger côté moteur d'estimation un jour.
7. Odoo **optionnel** (scène 6). Pour Odoo, utiliser `demo-checklist.md` sur une **autre organisation**
   (le SKU et le fournisseur que le script Odoo crée reprennent l'histoire RoulezBio, mais l'Odoo
   jetable garde ses propres données de démo mobilier si vous ne l'avez pas réinstallé sans elles).

## Ce que tu vends en une phrase

> « Vous pricez en FOB. Le vrai coût par référence arrive à J+45, avec la douane dedans. FreightSight
> ventile chaque facture sur vos conteneurs et lignes de commande, vous alerte avant les surestaries, et
> prépare l'écriture Odoo — sans Excel, sans double saisie. »

---

## Parcours A → Z (suivre les boutons « Prochaine étape »)

| # | Écran | Bouton à cliquer | Ce que tu montres |
|---|---|---|---|
| 1 | `/containers` | **Ouvrir MSCU4821990** | KPIs, conteneur à risque surestaries |
| 2 | Fiche MSCU | **Voir les coûts unitaires** | FOB 14 € → estimé **~17,85 €** (pneu) — *le chiffre qui fait tilt* |
| 3 | Même fiche, scroll | Bloc **Ventilation détaillée** (repliable, optionnel) | « Et si » : changer la méthode fret → coût unitaire bouge |
| 4 | `/invoices` | **Déposer une facture** | Glisser `facture-transitex-demo.pdf`, **confirmer les 5 lignes** |
| 5 | Après confirmation | **Coûts unitaires · MSCU4821990** | FOB 14 € → **18,14 €** (pneu) — le vrai coût, écart réel affiché |
| 6 | `/reports/variance` | (mois en cours) | Écart réel du mois : +416,29 € sur ce conteneur, poste par poste |
| 7 | `/reports` | **Exports CSV** + carte Surestaries | Export ouvert dans Excel ; tarif journalier 85 €/j affiché |
| 8 | Fiche MSCU (option Odoo) | Section **Écriture dans l'ERP** | Push brouillon → **Ouvrir dans Odoo** |

**Durée cible :** 12 min. **Ne pas tout montrer** : si le prospect accroche sur la marge, restez sur
scènes 1–2–5.

---

## Scène 1 · Vue d'ensemble (1 min) — Conteneurs

**Où :** `/containers`

**Encart « Prochaine étape » :** pointe vers MSCU (surestaries) ou vers les factures à relire.

**Montre :**
- Tuiles **FOB en cours**, **Ventilé**, **À risque**, **Sans coût**
- (Repliable) **À traiter cette semaine**

**Tu dis :**
> « Deux conteneurs de ce même arrivage : celui-ci va me coûter des surestaries si je ne le sors pas
> cette semaine, celui-là est déjà sorti. »

**Valeur :** éviter une journée de surestaries = de l'ordre de 85 €/jour/conteneur sur cette relation
(barème de l'organisation, réglable dans Paramètres).

---

## Scène 2 · Le coût unitaire vrai, avant facture (2 min) — Fiche MSCU4821990

**Où :** clic sur MSCU ou bouton **Coûts unitaires** de l'encart.

**Montre (en haut de page, sans scroller) :**
- Encart **Prochaine étape** → **Voir les coûts unitaires**
- Bandeau vert **Coût rendu par ligne** : pneu PO-2026-014 — FOB **14,00 €** → rendu **~17,85 €**
  (estimé à partir des barèmes fret/THC/dédouanement/camionnage/droits de douane, pas encore de facture)
- Tapis PO-2026-015 — FOB **20,00 €** → rendu **~25,50 €**

**Tu dis :**
> « Ce pneu, vous le croyez à 14 €. Rendu entrepôt, c'est déjà 17,85 € — et ça inclut les 4,5 % de droits
> de douane calculés sur la valeur CIF, comme en douane, pas seulement le fret. Si vous le vendez 20 €,
> votre marge n'est pas 6 € — c'est 2,15 €. »

**Valeur :** **marge / pricing** — le chiffre que le dirigeant comprend en 10 secondes.

**Repli si la question part sur « pourquoi un estimé, pas du réel » :** ce sont des barèmes propres à
l'organisation (Paramètres → Barèmes), remplis une fois ; la facture réelle les remplace un par un dès
qu'elle arrive — c'est justement la scène 4.

---

## Scène 3 · Méthode de ventilation (1 min, optionnel)

**Où :** même fiche, section **Ventilation détaillée** (ouvrir le repliable si besoin).

**Montre :** basculer la méthode **Fret maritime** → le coût unitaire change.

**Tu dis :**
> « Une méthode par type de coût — fret à la valeur, douane à la valeur CIF — et chaque centime est
> retrouvable ligne par ligne. »

---

## Scène 4 · La facture transitaire (4 min) — Factures

**Où :** `/invoices` → encart **Déposer une facture** (ou zone #depot).

**Fais :**
1. Glisser `docs/demo/fixtures/facture-transitex-demo.pdf`
2. Attendre l'extraction (quelques secondes)
3. Ouvrir la facture → encart **Relire les lignes**
4. **Confirmer les 5 lignes** (fret maritime, THC, dédouanement, camionnage, droits de douane) — **aucun
   piège de doublon ici** : le jeu d'exemple ne contient que des estimés, jamais un coût réel qui
   doublonnerait avec la facture. Toute la facture peut être validée d'un bloc.
5. Après confirmation → **Coûts unitaires · MSCU4821990**

**Tu dis :**
> « La facture arrive en PDF. Rien n'entre sans votre validation. Chaque ligne remplace l'estimé du même
> type sur ce conteneur — pas de double comptage — et c'est ce qui fait apparaître le vrai écart, poste
> par poste. Plus de ressaisie dans Excel. »

**Valeur :** **temps ops** — 30–60 min de saisie par facture × N conteneurs/mois.

**Si l'extraction rate :** vérifier `docker compose ps` (le service **worker** doit tourner — c'est le
point de contrôle avant l'appel, pas pendant). En dernier recours : **Ajouter un coût** sur la fiche
conteneur (section repliable) et dire que l'extraction est en bêta, la ventilation fonctionne déjà.

---

## Scène 5 · Après la facture (2 min) — Retour MSCU

**Où :** bouton **Coûts unitaires · MSCU4821990** après confirmation.

**Montre :**
- Pneu : FOB 14 € → rendu **18,14 €** (après facture réelle — était 17,85 € estimé)
- Tapis PO-2026-015 : 20 € → **25,91 €** (était 25,50 € estimé)
- Jauge **Postes facturés** : 5/5, 100 % — plus aucun estimé sur ce conteneur

**Tu dis :**
> « Avant la facture, vous aviez une estimation par barème. Après, le vrai coût par référence, poste par
> poste — c'est ce que vous pricez ou ce que le DAF provisionne. »

**Valeur :** preuve de marge, avec un écart réel et non nul (contrairement à un conteneur qui n'a jamais
été confronté à une facture).

---

## Scène 6 · L'écart du mois, pour le DAF (1 min)

**Où :** `/reports/variance`, mois en cours.

**Montre :** estimé 5 642,50 € · réel 6 058,79 € · écart **+416,29 €** sur MSCU4821990, détaillé par type
de coût (fret +215,40 €, THC +18,00 €, dédouanement +22,50 €, camionnage **-54,00 €**, droits +214,39 €).

**Tu dis :**
> « C'est le tableau que votre comptabilité analytique n'a pas aujourd'hui : pas juste “plus cher”, mais
> quel poste, de combien, sur quelle commande. »

**Si la page est vide :** ça veut dire que la facture n'est pas encore confirmée (scène 4) ou que le mois
affiché n'est pas le mois en cours — changez de mois plutôt que de conclure que la fonctionnalité ne
marche pas.

---

## Scène 7 · Clôture pour le DAF/CFO (2 min)

**Où :** `/reports`.

**Fais :**
1. Carte **Surestaries** : tarif journalier 85 €/jour (barème de l'org), section **à risque
   maintenant** → MSCU4821990. « Évité » affichera 0,00 € sur une organisation tout juste créée — pas
   d'historique d'alerte encore accumulé, c'est honnête, pas un bug ; dites-le si on vous pose la
   question plutôt que de l'éviter.
2. Carte **Exports CSV** → cliquer **Coût rendu par ligne chargée**, ouvrir le fichier dans Excel (BOM
   UTF-8, séparateur `;`, virgule décimale — pensé pour Excel FR).
3. Alerte e-mail : **montrer la capture d'écran préparée à l'avance** (voir ci-dessous), pas un envoi en
   direct — l'envoi réel passe par Resend, une clé serveur de production, absente d'un poste de démo
   local.

**Tu dis :**
> « Ce fichier, c'est ce que votre comptabilité récupère sans ressaisir une ligne. Et le jour où ce
> conteneur dépasse son dernier jour franc, cette alerte part toute seule, avec le montant en jeu. »

**Honnêteté sur ce qui a besoin de clés de prod :** le tracking automatique (Terminal49 / Shipsgo) et
l'envoi d'e-mail (Resend) tournent avec une clé posée côté serveur, pas dans le navigateur du prospect —
en démo locale sans ces clés, on montre la mécanique (barème, aperçu de l'alerte) plutôt qu'un envoi réel.
Préparer à l'avance : capture d'écran d'un e-mail d'alerte reçu sur une organisation où la clé Resend est
active (l'environnement de recette, pas la prod client), datée récemment.

---

## Scène 8 · Odoo (2 min, si prospect Odoo)

**Où :** fiche conteneur → section repliable **Écriture dans l'ERP**.

**Montre :** aperçu → push brouillon → **Ouvrir dans Odoo** (lien direct).

**Tu dis :**
> « Votre comptable valide dans Odoo. On ne touche jamais à vos écritures validées. »

**Prérequis :** `demo-checklist.md`, **organisation séparée** de celle-ci (voir « Avant l'appel », point 7).

---

## Clôture (1 min)

| Question | Ce que ça chiffre |
|---|---|
| Combien de conteneurs / mois ? | Volume |
| Combien d'heures Excel + Odoo / conteneur ? | Gain temps |
| Une journée de surestaries = combien chez vous ? | Gain évité |
| Vous pricez au FOB ou au rendu ? | Urgence produit |

**Phrase de clôture :**
> « Je cherche 5 importateurs Odoo pour affiner ça avec eux. Est-ce que ça vaut 30 minutes pour voir si
> vos chiffres collent ? »

---

## Deux parcours selon le contexte

| | Démo commerciale (ce doc) | Recette Odoo (`demo-checklist.md`) |
|---|---|---|
| **Org** | Nouvelle org + données d'exemple | Org connectée Odoo fstest, séparée |
| **Focus** | Marge, factures, écart réel, surestaries | Push landed cost brouillon |
| **Fil conducteur** | Encarts « Prochaine étape » | Checklist A1–A9 |

Enchaînement possible sur un même appel : **commercial d'abord**, **Odoo ensuite** (deux organisations).

---

## Dépannage rapide

| Problème | Solution |
|---|---|
| Pas de bouton « données d'exemple » | Org déjà remplie → nouvelle org Clerk |
| Pas d'encart « Prochaine étape » | Recharger la page (déploiement frontend) |
| Facture 0 ligne | Vérifier `docker compose ps` **avant** l'appel — le service `worker` doit tourner |
| Une ligne de la facture signalée en doublon | Ne devrait pas arriver avec le jeu d'exemple (tout est estimé, jamais réel) — si ça arrive, un coût réel a été ajouté à la main entre-temps sur ce conteneur |
| `/reports/variance` vide | Facture pas encore confirmée, ou mauvais mois sélectionné (utiliser le mois en cours) |
| Surestaries « Évité » à 0,00 € | Normal sur une org neuve, expliquer pourquoi (scène 7) plutôt que l'éviter |
| Pas de carte ERP | Paramètres → connecter Odoo |
| Facture datée de longtemps | Régénérer : `backend/.venv/bin/python docs/demo/fixtures/generate_invoice.py` |
