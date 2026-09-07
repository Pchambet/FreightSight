# FreightSight — Walkthrough technique (état Phase 1)

Dernière mise à jour : 7 septembre 2026. Ce document décrit ce qui existe réellement dans le dépôt. Les
plans détaillés vivent hors du code, dans `docs/plan/` (non versionné).

## Modèle de données

```
Organization (base_currency, default_allocation_method, free days)
 ├─ Shipment (BL / booking)                ← coûts "voyage" : ocean freight, BL fee, assurance
 │   └─ Container (milestone, LFD, risque D&D)   ← coûts "boîte" : drayage, THC, surestaries
 │       └─ ContainerLoad (po_line × container × quantité)   ← la FEUILLE où tout atterrit
 ├─ PurchaseOrder (devise, taux figé)      ← coûts "commande" : inspection, frais bancaires
 │   └─ PurchaseOrderLine (SKU, qté, prix, kg, CBM, HS, taux de droits)
 ├─ Cost (un seul scope, montant en devise + taux figé + montant base, méthode)
 │   └─ CostAllocation (matérialisée, recalculée à chaque écriture)
 ├─ Supplier · FxRate · ImportJob · ImportMapping
 └─ User · Membership
```

Toutes les tables métier portent `org_id`. Une policy Row Level Security (migration 0003) lit la variable
de session `app.org_id` posée par `app/core/tenancy.py` à chaque requête. En production l'API doit se
connecter avec le rôle `freightsight_app` : un superuser contourne la RLS.

## Moteur d'allocation (`app/domain/costing/engine.py`)

Fonction pure, sans I/O. Deux passes : les coûts ordinaires, puis les droits de douane sur la base CIF (la
valeur en douane UE inclut fret et assurance). Méthodes : `BY_VALUE`, `BY_WEIGHT`, `BY_VOLUME`,
`BY_QUANTITY`, `MANUAL` (pourcentages sur les enfants directs du scope, somme = 100,00), `BY_CIF_VALUE` et
`BY_THEORETICAL_DUTY` réservées aux droits. Decimal, plancher au centime, centimes restants aux plus grands
restes, départage par `(container_number, po_number, line_no)`. Un coût non ventilable (base manquante,
scope sans chargement, split invalide) est renvoyé dans `unallocated` avec un code, jamais deviné.

Les neuf cas de référence du plan (T1 à T9) sont dans `tests/test_engine.py`, et le cas T5 est rejoué de
bout en bout par l'API dans `tests/test_api_flow.py`.

## Backend (`backend/app/`)

| Chemin | Rôle |
|---|---|
| `core/settings.py` | Configuration 12-factor (base, CORS, Clerk, URL des taux BCE) |
| `core/auth.py` | Principal : JWT Clerk vérifié par JWKS avec miroir local, ou en-tête `X-Org-Id` hors prod |
| `core/tenancy.py` | `TenantSession` (filtre applicatif) + variable RLS |
| `core/errors.py` | Exceptions domaine → problem+json avec `code` |
| `domain/models.py` | Schéma SQLAlchemy 2 |
| `domain/costing/{engine,service,report}.py` | Moteur pur, matérialisation, rapports |
| `domain/fx/service.py` + `adapters/fx_ecb.py` | Taux figés, BCE via Frankfurter, override manuel |
| `domain/imports/{parsing,service}.py` | Décodage CSV/XLSX, mapping, dry-run sous SAVEPOINT, commit |
| `api/v1/*` | Routes REST v1 |
| `migrations/versions/000{1,2,3}_*.py` | Baseline, schéma Phase 1 avec migration des données Phase 0, RLS |

## Endpoints v1

| Ressource | Routes |
|---|---|
| Identité | `GET /me`, `GET/PATCH /organization` |
| Fournisseurs | `GET/POST /suppliers`, `PATCH/DELETE /suppliers/{id}` |
| Commandes | `GET/POST /purchase-orders`, `GET/PATCH/DELETE /purchase-orders/{id}` (lignes en upsert par `line_no`) |
| Expéditions | `GET/POST /shipments`, `GET/PATCH/DELETE /shipments/{id}` |
| Conteneurs | `GET/POST /containers`, `GET/PATCH/DELETE /containers/{id}`, `GET/PUT /containers/{id}/loads` |
| Coûts | `GET/POST /costs`, `GET/PATCH/DELETE /costs/{id}` |
| Landed costs | `GET /landed-costs/{containers,shipments,purchase-orders}/{id}`, `POST /landed-costs/preview`, `GET /reports/integrity` |
| Imports | `GET/POST /imports`, `GET /imports/{id}`, `POST /imports/{id}/validate`, `POST /imports/{id}/commit` |
| Taux | `GET /fx-rates?quote=&on_date=` |

Montants en chaînes décimales, erreurs RFC 9457 avec un `code` stable (`OVER_ALLOCATED`,
`FX_RATE_UNAVAILABLE`, `METHOD_NOT_ALLOWED`, `MAPPING_INCOMPLETE`, `NO_VALID_ROWS`…).

## Frontend (`frontend/src/`)

| Chemin | Rôle |
|---|---|
| `lib/env.ts`, `lib/api/client.ts` | Env validée par zod, client `openapi-fetch` typé, serveur uniquement |
| `lib/domain.ts`, `lib/format.ts` | Enums miroir, libellés, formatage monétaire |
| `features/actions.ts` | Server Actions : coûts, chargements, tracking manuel, imports, réglages |
| `app/page.tsx` | Board des conteneurs : milestone, last free day, risque, FOB, alloué, coûts présents |
| `app/container/[id]/page.tsx` | Détail : tracking manuel, chargements, ajout de coût, breakdown par ligne avec preview « et si », ledger |
| `app/purchase-orders/*` | Liste et détail (lignes, coûts, breakdown par conteneur) |
| `app/imports/*` + `features/imports/ImportWizard.tsx` | Wizard 4 étapes : upload → mapping → rapport → commit |
| `app/settings/page.tsx` | Devise de base, méthode par défaut, jours francs |

Le navigateur ne parle jamais directement à l'API. Toutes les pages sont rendues à la demande.

## Ce qui reste pour clore la Phase 1

- Brancher Clerk dans le Next (sign-in, org switcher, token dans le client) dès que les clés existent ;
  le backend est prêt (`CLERK_JWKS_URL`, `CLERK_ISSUER`).
- Déploiement Railway EU + Vercel, `pg_dump` nocturne vers Scaleway Paris, Sentry.
- Test Playwright du chemin de démo.
