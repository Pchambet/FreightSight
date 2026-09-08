# Ops — Railway (API) et Vercel (front)

Dernière mise à jour : 8 septembre 2026. État : appliqué en production (rôle limité, Clerk, Amsterdam).

## 1. Rôle Postgres à privilèges limités (obligatoire pour la RLS)

Un superuser contourne la Row Level Security. La migration `0003` crée le rôle `freightsight_app`
(NOLOGIN) avec SELECT/INSERT/UPDATE/DELETE sur toutes les tables et des privilèges par défaut pour les
tables futures. Il reste à créer un rôle de connexion qui en hérite. Ouvre une console SQL sur le
service Postgres (`railway connect Postgres` depuis le CLI, ou l'onglet Data → Query du dashboard) en
tant que `postgres` :

```sql
-- 1. Vérifier que les migrations ont créé le rôle applicatif
SELECT rolname FROM pg_roles WHERE rolname = 'freightsight_app';   -- doit renvoyer 1 ligne

-- 2. Créer le rôle de connexion de l'API (mot de passe fort, 32+ caractères, sans caractères réservés d'URL)
CREATE ROLE freightsight LOGIN PASSWORD 'REMPLACER_PAR_UN_MOT_DE_PASSE_FORT';
GRANT freightsight_app TO freightsight;

-- 3. Vérifier qu'il n'est ni superuser ni BYPASSRLS
SELECT rolname, rolsuper, rolbypassrls, rolinherit FROM pg_roles WHERE rolname = 'freightsight';
-- attendu : freightsight | f | f | t

-- 4. Test d'isolation : sans variable de session, aucune ligne
SET ROLE freightsight;
SELECT count(*) FROM containers;              -- 0 même si la table est pleine
SELECT set_config('app.org_id', (SELECT id::text FROM organizations LIMIT 1), false);
SELECT count(*) FROM containers;              -- les lignes de cette organisation seulement
RESET ROLE;
```

Puis, sur le service API dans Railway (Variables), en gardant les références `${{Postgres.*}}` :

| Variable | Valeur |
|---|---|
| `APP_DB_PASSWORD` | le mot de passe choisi ci-dessus (variable « sealed ») |
| `DATABASE_URL` | `postgresql+psycopg://freightsight:${{APP_DB_PASSWORD}}@${{PostgresEU.PGHOST}}:${{PostgresEU.PGPORT}}/${{PostgresEU.PGDATABASE}}` |
| `MIGRATIONS_DATABASE_URL` | `postgresql+psycopg://${{PostgresEU.PGUSER}}:${{PostgresEU.PGPASSWORD}}@${{PostgresEU.PGHOST}}:${{PostgresEU.PGPORT}}/${{PostgresEU.PGDATABASE}}` |

Les migrations tournent avec `MIGRATIONS_DATABASE_URL` (propriétaire des tables), l'API avec
`DATABASE_URL` (rôle limité). Sans `MIGRATIONS_DATABASE_URL`, Alembic retombe sur `DATABASE_URL`, ce
qui échouera dès qu'une migration modifie une table appartenant à `postgres`.

## 2. Variables d'environnement

### Railway (service API)

| Variable | Valeur | Rôle |
|---|---|---|
| `APP_ENV` | `prod` | Refuse l'en-tête `X-Org-Id`, désactive Swagger, exige Clerk au démarrage |
| `CLERK_ISSUER` | `https://<instance>.clerk.accounts.dev` | Émetteur attendu dans les JWT |
| `CLERK_JWKS_URL` | `https://<instance>.clerk.accounts.dev/.well-known/jwks.json` | Clés publiques de signature |
| `CLERK_AUTHORIZED_PARTIES` | `["https://freight-sight-two.vercel.app"]` | Origines autorisées (`azp`). Les previews Vercel ont chacune une origine : les lister ou laisser vide sur un service de preview |
| `CORS_ORIGINS` | `["https://freight-sight-two.vercel.app"]` | Sans effet tant que le navigateur ne parle pas à l'API, mais explicite |
| `DEFAULT_BASE_CURRENCY` | `EUR` | Devise des organisations créées à la première connexion |
| `DATABASE_URL`, `MIGRATIONS_DATABASE_URL`, `APP_DB_PASSWORD` | voir §1 | |

Le démarrage échoue volontairement si `APP_ENV=prod` sans `CLERK_ISSUER` et `CLERK_JWKS_URL`.

### Vercel (projet front)

| Variable | Rôle |
|---|---|
| `API_URL` | `https://freightsight-production.up.railway.app` |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | Clés Clerk. Instance de développement (`pk_test_`) sur Preview **et** Production tant qu'il n'y a pas de domaine propre : Clerk refuse les clés `pk_live_` sur `*.vercel.app` |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in`, `NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up` | Routes des pages Clerk |
| `ORG_ID` | **à supprimer** : l'organisation vient du JWT. Cette variable n'a de sens qu'en local contre un backend sans Clerk |

## 3. Clerk (dashboard)

1. **Organizations → Enable → Membership required.** Un utilisateur sans organisation est en session
   `pending` ; le front l'envoie sur `/choose-organization` (composant `TaskChooseOrganization`), le
   backend refuse le jeton (401) tant que l'organisation n'est pas choisie.
2. **Sessions → Customize session token** : ajouter l'e-mail et le nom, absents du jeton par défaut
   (limite 1,2 Ko de claims personnalisés) :
   ```json
   { "email": "{{user.primary_email_address}}", "name": "{{user.full_name}}" }
   ```
3. Instance de développement : 100 utilisateurs maximum, domaine `*.accounts.dev`, bandeau
   « Development ». Passer en production Clerk demande un domaine propre (CNAME `clerk.<domaine>`).
4. Après le merge de la PR de sécurisation : **faire tourner la clé secrète** qui a circulé dans un chat.

## 4. Déploiement

### Railway

- Le service construit `backend/Dockerfile` (détection automatique). Les fichiers `railway.json` /
  `railway.toml` sont dépréciés (arrêt le 1er décembre 2026) : tout se règle dans le dashboard.
- **Settings → Deploy → Pre-deploy command** : `alembic upgrade head`. Il tourne une fois par
  déploiement, dans un conteneur séparé, avant que la nouvelle version reçoive du trafic ; un échec
  annule le déploiement et l'ancienne version continue de servir. La commande de démarrage de l'image
  exécute aussi `alembic upgrade head` par sécurité ; c'est redondant mais idempotent, et à retirer de
  l'image quand tu passes à plusieurs répliques (chaque réplique la relancerait).
- **Settings → Deploy → Healthcheck path** : `/readyz`. Railway ignore le `HEALTHCHECK` du Dockerfile.
- **Région** : API et Postgres (`PostgresEU`, endpoint privé `postgreseu.railway.internal`) tournent à
  Amsterdam (`europe-west4-drams3a`) depuis le 8 septembre 2026. La configuration est dans
  `.railway/railway.ts` (`npm install railway --no-save` à la racine, puis `railway config plan|apply`).
- **Draining seconds** : 10, pour laisser finir les requêtes en cours au redéploiement.
- Sauvegardes : les backups de volume Railway sont quotidiens ; le PITR existe. Ajouter un service
  cron (`0 3 * * *`) qui fait `pg_dump --format=custom` vers Scaleway Object Storage Paris
  (`aws s3 cp --endpoint-url https://s3.fr-par.scw.cloud`) pour la copie souveraine.

### Vercel

- Le projet construit `frontend/`. Toutes les pages sont rendues à la demande ; le navigateur ne parle
  jamais à l'API, seules les Server Actions et les Server Components le font avec le JWT de session.
- Déploiements de preview : `CLERK_AUTHORIZED_PARTIES` sur l'API ne connaît pas leurs origines ; soit
  les previews pointent sur un service API de preview sans liste, soit on accepte que le front de preview
  ne puisse pas appeler l'API de production.

## 5. Vérification après déploiement

```bash
API=https://freightsight-production.up.railway.app
curl -s $API/readyz                                   # {"status":"ready"}
curl -s -o /dev/null -w "%{http_code}\n" $API/docs    # 404 en prod
curl -s -H "X-Org-Id: 11111111-1111-4111-8111-111111111111" $API/api/v1/me   # 401
curl -s -H "Authorization: Bearer x" $API/api/v1/me                          # 401 "Invalid token"
```

Puis se connecter sur le front, créer une organisation, importer le CSV d'exemple, et vérifier dans la
console SQL que `SET ROLE freightsight; SELECT count(*) FROM containers;` renvoie 0 sans `app.org_id`.
