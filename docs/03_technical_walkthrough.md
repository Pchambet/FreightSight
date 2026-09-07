# FreightSight — Walkthrough technique (état Phase 0)

Dernière mise à jour : 7 septembre 2026. Ce document décrit ce qui existe réellement dans le dépôt. Les
plans détaillés (schéma cible, moteur complet, tracking, extraction de factures, infra) vivent hors du
code, dans `docs/plan/` (non versionné).

## Ce que fait le produit aujourd'hui

1. Import CSV de bons de commande, avec liaison optionnelle à un conteneur.
2. Saisie manuelle de coûts logistiques sur un conteneur, dans la devise de base de l'organisation.
3. Calcul du landed cost par bon de commande : répartition au prorata de la valeur, arrondi au centime par
   la méthode du plus fort reste. Les pourcentages hérités de l'ancien format ne sont honorés que s'ils
   totalisent exactement 100 %.
4. Statut de conteneur modifiable à la main (aucun fournisseur de tracking branché).

L'extraction de factures renvoie `501 NOT_IMPLEMENTED`. Il n'y a ni authentification ni utilisateurs :
l'organisation est choisie par l'en-tête `X-Org-Id`.

## Backend (`backend/`)

| Fichier | Rôle |
|---|---|
| `app/main.py` | Application FastAPI, CORS explicite, erreurs au format problem+json, `/healthz`, `/readyz` |
| `app/config.py` | Configuration 12-factor via pydantic-settings (`DATABASE_URL`, `CORS_ORIGINS`, `APP_ENV`) |
| `app/db.py` | Engine, sessions, vérification que la base est à la dernière migration au démarrage |
| `app/models.py` | Organization, PurchaseOrder, Container, ContainerPurchaseOrder, Cost (SQLAlchemy 2, `Numeric`) |
| `app/schemas.py` | Schémas Pydantic ; montants `Decimal` en entrée, chaînes en sortie |
| `app/costing.py` | Moteur d'allocation pur : `split_largest_remainder`, `allocate_container` |
| `app/imports.py` | Décodage CSV (BOM, cp1252, `;`, nombres FR), validation ligne à ligne |
| `app/deps.py` | Dépendance `get_org` (en-tête `X-Org-Id`) |
| `app/api/containers.py` | Conteneurs, coûts, landed costs, upload facture (501) |
| `app/api/purchase_orders.py` | Import CSV en une transaction |
| `migrations/` | Alembic, migration `0001_baseline` |
| `tests/` | 28 tests : moteur, import, API bout en bout sur un vrai Postgres, garde anti-float |

## Endpoints

| Méthode | Route | Notes |
|---|---|---|
| GET | `/healthz`, `/readyz` | liveness / readiness (SELECT 1) |
| GET | `/api/containers` | liste scopée par organisation |
| POST | `/api/containers` | numéro ISO 6346 validé, 409 si doublon |
| PATCH | `/api/containers/{id}` | statut et transporteur (tracking manuel) |
| POST | `/api/containers/{id}/costs` | montant `Decimal` > 0, devise = devise de base sinon 422 |
| POST | `/api/containers/{id}/upload-invoice` | 501 NOT_IMPLEMENTED |
| GET | `/api/containers/{id}/landed-costs` | breakdown par PO, méthode, `unallocated`, `warnings` |
| POST | `/api/purchase-orders/upload` | CSV ; 422 `NO_VALID_ROWS` si aucune ligne valide |

Exemple de calcul avec le fichier `backend/tests/fixtures/legacy_po_container.csv` et 1 800,00 EUR de
coûts sur MSCU1234567 (Michelin 12 500,50 et Pirelli 8 400,00) : Michelin reçoit 1 076,57, Pirelli
723,43. La somme fait 1 800,00. Les pourcentages du fichier (100 % et 50 %) sont ignorés avec un
avertissement `DEPRECATED_ALLOCATION_PCT`, là où l'ancien code allouait 150 % des coûts.

## Frontend (`frontend/`)

| Fichier | Rôle |
|---|---|
| `src/lib/env.ts` | Variables d'environnement validées par zod (`API_URL`, `ORG_ID`), serveur uniquement |
| `src/lib/api/client.ts` | Client `openapi-fetch` typé à partir de `schema.d.ts` (généré par `npm run api:types`) |
| `src/lib/domain.ts` | Enums miroir du backend et libellés |
| `src/lib/format.ts`, `components/shared/Money.tsx` | Formatage monétaire unique |
| `src/features/actions.ts` | Server Actions : import CSV, ajout de coût, changement de statut |
| `src/app/page.tsx` | Liste des conteneurs |
| `src/app/container/[id]/page.tsx` | Landed cost par PO, avertissements, coûts |

Le navigateur ne parle jamais directement à l'API : lectures en Server Components, écritures en Server
Actions. Aucune URL en dur, aucun `any`.

## Infra

- `docker-compose.yml` : Postgres 17, service `migrate` (alembic upgrade head), API en rechargement.
- `backend/Dockerfile` : image `uv`, utilisateur non-root, healthcheck, `CMD` uvicorn.
- `.github/workflows/ci.yml` : ruff, mypy, alembic upgrade + check, pytest sur Postgres 17 ; lint, tsc,
  build Next ; gitleaks.
- `.pre-commit-config.yaml` : gitleaks, ruff, hooks de base.

## Prochaines étapes

Voir le plan de route (Phase 1 : authentification, tenancy avec RLS, schéma cible avec lignes de commande
par conteneur, méthodes d'allocation par valeur / poids / volume / quantité, import avec mapping de
colonnes ; Phase 2 : tracking réel, extraction de factures avec revue humaine, alertes).
