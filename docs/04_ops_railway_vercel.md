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
2. **Sessions → Customize session token** : ajouter l'e-mail, le nom et le nom de l'organisation,
   absents du jeton par défaut (limite 1,2 Ko de claims personnalisés ; lus par
   `backend/app/adapters/auth_clerk.py`) :
   ```json
   { "email": "{{user.primary_email_address}}", "name": "{{user.full_name}}", "org_name": "{{org.name}}" }
   ```
3. Instance de développement : 100 utilisateurs maximum, domaine `*.accounts.dev`, bandeau
   « Development ». Passer en production Clerk demande un domaine propre (CNAME `clerk.<domaine>`) :
   la procédure complète, données existantes comprises, est dans `docs/domaine-bascule.md`.
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
  `/readyz` ne parle que de l'API : base joignable, et rôle applicatif non-superutilisateur (en prod,
  une connexion `rolsuper` ou `rolbypassrls` contourne RLS en silence, donc l'API refuse de servir).
  Il **ne** doit pas échouer quand le worker est mort : c'est précisément le jour où il faut pouvoir
  déployer un correctif. Il expose `worker_seen_at` à titre indicatif, rien de plus.
- **Sonde du worker** : `GET /healthz/worker` (200 / 503). Le worker écrit un battement toutes les
  5 minutes dans `job_runs` ; l'endpoint répond 503 au-delà de 15 minutes de silence. À brancher sur
  une sonde externe gratuite (UptimeRobot, Better Stack), intervalle 5 min, alerte SMS :

  ```
  https://freightsight-production.up.railway.app/healthz/worker
  ```

  C'est le seul maillon qui survit à la mort complète de Railway. Sans lui, un worker tué par l'OOM
  ne se voit nulle part : plus d'alerte surestaries, plus d'extraction de facture, plus de synchro
  Odoo — et l'interface continue d'afficher les chiffres du dernier calcul.
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
curl -s $API/readyz                                   # {"status":"ready","worker_seen_at":"…"}
curl -s $API/healthz/worker                           # {"status":"ok"} — 503 si le worker est mort
curl -s -o /dev/null -w "%{http_code}\n" $API/docs    # 404 en prod
curl -s -H "X-Org-Id: 11111111-1111-4111-8111-111111111111" $API/api/v1/me   # 401
curl -s -H "Authorization: Bearer x" $API/api/v1/me                          # 401 "Invalid token"
```

Puis se connecter sur le front, créer une organisation, importer le CSV d'exemple, et vérifier dans la
console SQL que `SET ROLE freightsight; SELECT count(*) FROM containers;` renvoie 0 sans `app.org_id`.

## 6. Sauvegardes hors fournisseur (Scaleway Paris)

Railway sauvegarde son propre volume ; ça ne protège de rien si le compte Railway est perdu. La copie
souveraine est un service cron Railway qui lance `python -m app.backup` (même image que l'API).

**Variables du service `backup`** — sans l'une d'elles, la commande refuse de tourner et dit laquelle :

| Variable | Rôle |
|---|---|
| `MIGRATIONS_DATABASE_URL` | la base à sauvegarder, **en tant que propriétaire** |
| `BACKUP_ENCRYPTION_KEY` | 32 octets en base64 (`openssl rand -base64 32`) |
| `SCW_ACCESS_KEY`, `SCW_SECRET_KEY` | clé API Scaleway |
| `SCW_BUCKET` | `freightsight-backups` |
| `SCW_REGION`, `SCW_ENDPOINT` | facultatifs (`fr-par`, `https://s3.fr-par.scw.cloud`) |
| `APP_ENV` | sépare les préfixes `backups/prod/`, `backups/preview/`… |

**Pourquoi le rôle propriétaire :** la RLS s'applique au rôle applicatif. Un `pg_dump` fait avec
`freightsight` produirait une sauvegarde **silencieusement partielle** — le pire cas possible, puisqu'elle
se restaure sans erreur.

**Ce que ça écrit :** `backups/<env>/<AAAA-MM-JJ>T<HHMM>.dump.enc`, un `pg_dump --format=custom`
chiffré en AES-256-GCM avant de quitter le processus (le bucket contient les données de tous les
clients ; une ACL mal réglée doit laisser fuir un chiffré, pas une base). Rétention : 30 jours
glissants + la première sauvegarde de chacun des 12 derniers mois. Une ligne de log JSON par exécution
avec la taille, la durée et le sha256 du dump en clair.

**Ce que ça laisse derrière soi :** chaque sauvegarde réussie écrit une ligne `ops.backup` dans
`job_runs` (date, clé, taille, taille de la précédente). Le worker la relit chaque jour à 04:45 UTC
(`ops.check_backup_freshness`) **sans identifiants Scaleway** : plus de 48 h sans sauvegarde, ou une
sauvegarde d'un tiers plus petite que la veille, et c'est une erreur dans Sentry. Le verdict
(`ops.backup_freshness`) est ce que lisent Paramètres → état du service et `python -m app.doctor`. Le
service `backup` a son propre `SENTRY_DSN` (référencé dans `.railway/railway.ts`) : un échec ou une
sauvegarde non enregistrée part en erreur, pas seulement dans un log rouge à 03:00.

**⚠️ La clé de chiffrement ne doit pas vivre uniquement dans Railway.** Si le compte Railway est
perdu, la clé l'est aussi et les sauvegardes ne servent plus à rien. Elle va dans un gestionnaire de
mots de passe, hors du fournisseur.

### Restaurer, en cinq commandes

```bash
# 1. Lister ce qu'on a (depuis n'importe quelle machine ayant les variables)
aws s3 ls s3://freightsight-backups/backups/prod/ --endpoint-url https://s3.fr-par.scw.cloud

# 2. Créer une base cible vide (jamais la base de production directement)
psql "$MIGRATIONS_DATABASE_URL" -c 'CREATE DATABASE restore_check'

# 3. Restaurer la sauvegarde choisie dedans (redonne aussi ses droits à freightsight_app, voir plus bas)
python -m app.restore backups/prod/2026-09-09T0300.dump.enc \
  --to "postgresql://…@…/restore_check" --yes

# 4. Vérifier qu'elle contient quelque chose de crédible, et que l'API pourra la lire
psql "postgresql://…@…/restore_check" -c \
  "SELECT (SELECT count(*) FROM organizations) AS orgs, (SELECT count(*) FROM costs) AS costs"
psql "postgresql://…@…/restore_check" -c \
  "SELECT has_table_privilege('freightsight_app', 'containers', 'SELECT')"   # doit dire t

# 5. Basculer : renommer, ou repointer DATABASE_URL sur la base restaurée
psql "$MIGRATIONS_DATABASE_URL" -c \
  'ALTER DATABASE freightsight RENAME TO freightsight_broken; ALTER DATABASE restore_check RENAME TO freightsight'
```

L'étape 4 n'est pas décorative : **une sauvegarde qu'on n'a jamais restaurée est une rumeur.** À faire
une fois pour de vrai, et à refaire après tout changement de schéma majeur.

**Les droits du rôle applicatif.** Les dumps sont pris sans privilèges (`--no-privileges`) : ils
doivent pouvoir se restaurer dans une base dont les rôles ne sont pas ceux de la source. Une copie
restaurée ainsi n'est lisible que par son propriétaire — l'API y recevrait « permission denied » sur
chaque table — et la fonction `SECURITY DEFINER` `tracking_resolve_subscription` y redeviendrait
exécutable par PUBLIC. `app.restore` rejoue donc, après `pg_restore`, les droits que posent les
migrations (`APP_GRANTS` dans `app/ops/backup.py`) ; le test `test_a_restored_dump_is_readable_by_the_application`
compare la copie à une base migrée, droit par droit, et lit une ligne en `freightsight_app` sous RLS. Il
tourne en CI (il échoue au lieu de s'ignorer quand `CI=true`) avec le client 18 nommé par son chemin.

`pg_dump` et `pg_restore` sont dans l'image (`postgresql-client-18`, la même majeure que le serveur :
`pg_dump` refuse un serveur plus récent que lui, donc cette version suit celle de la base).

## 7. Redémarrer après une coupure

Cas d'octobre 2026 : l'espace Railway est passé inactif (essai terminé, aucun abonnement), tous les
déploiements ont été retirés, le volume Postgres est resté intact. Rien dans le code n'est en cause.

**1. Ce que seul le propriétaire fait.** Tableau de bord Railway → espace « Pierre Chambet's Projects »
→ Settings → Billing → souscrire au plan Hobby (5 $/mois, carte). Vérifier que l'état est « Active ».
Avant de relancer, vérifier aussi qu'un dump récent existe dans le bucket Scaleway et que la clé
`BACKUP_ENCRYPTION_KEY` est bien conservée hors de Railway.

**2. Redéployer dans l'ordre** (CLI `railway` connectée ; ces commandes n'ont pas encore été jouées) :

```bash
cd ~/Desktop/GitHub/FreightSight
P=03daf49e-8715-41ee-ae74-de3e53aa16c7
railway link -p $P -e production
# a. la base d'abord (image et volume intacts) ; attendre SUCCESS
railway redeploy -s PostgresEU -e production --from-source -y
railway deployment list -p $P -e production -s PostgresEU --json | head
# b. l'API au dernier commit de main : le pre-deploy joue alembic, puis /readyz doit passer en 120 s
railway redeploy -s FreightSight -e production --from-source -y
railway logs -s FreightSight -e production          # alembic OK, puis « ready »
# c. le worker, d. la sauvegarde (même image)
railway redeploy -s worker -e production --from-source -y
railway redeploy -s backup -e production --from-source -y
```

Si `--from-source` est refusé : tableau de bord → service → Deploy (dernier commit), ou le prochain push
sur `main`. **Ne jamais lancer `railway config apply`** : appliquer `.railway/railway.ts` (par exemple
le `SENTRY_DSN` du service `backup`) est une décision du propriétaire, à part.

Les migrations ne vont qu'en avant : lire `backend/migrations/versions/` pour les révisions ajoutées
depuis le dernier déploiement réussi (2683c91, le 28 septembre ; aucune nouvelle au 6fba532) avant
l'étape b.

**3. Sonder** (attendus entre parenthèses) :

```bash
B=https://freightsight-production.up.railway.app
curl -s -w ' %{http_code}\n' $B/readyz                           # 200 {"status":"ready",…}
curl -s -w ' %{http_code}\n' $B/healthz/worker                   # 200 quelques minutes après le worker ; 503 avant
curl -s -o /dev/null -w '%{http_code}\n' $B/api/v1/me             # 401 (sans jeton)
curl -s -o /dev/null -w '%{http_code}\n' https://freight-sight-two.vercel.app/   # 200
```

Puis : Sentry sans nouvelle erreur, une connexion Clerk sur le site Vercel qui atteint `/api/v1/me` en
200, `railway run -s FreightSight python -m app.doctor` (lecture seule). Déclencher une sauvegarde à la
main depuis le service `backup` plutôt que d'attendre 03:00 UTC, et vérifier le lendemain que
`ops.backup_freshness` est vert.

**4. Ce que fait le worker au réveil.** Pas de rattrapage en rafale : Procrastinate ne relance que le
dernier tic périodique, s'il a moins de 10 minutes. Le passage surestaries tourne une fois (plus de
20 h depuis le dernier) et chaque conteneur dont l'horloge court reçoit une alerte datée du jour ; les
alertes J-3/J-1 tombées pendant la coupure sont perdues. Il lit les jalons d'avant la coupure : un
conteneur enlevé ou restitué pendant la coupure peut être annoncé « surestaries en cours » dans le
premier récapitulatif. Saisir ces dates avant que le premier passage tourne (06:00 Paris), ou prévenir
les clients que le premier e-mail est un rattrapage. Un job resté `doing` à l'arrêt est relancé (ou
abandonné, et la facture passe en échec) par `ops.recover_stalled_jobs` dans les 10 minutes.

## 8. Postgres local : passage de 17 à 18

`docker-compose.yml` lance `postgres:18`, la majeure de la CI et de la production. Les images 18
rangent les données dans `/var/lib/postgresql/18/docker` et montent le volume sur `/var/lib/postgresql`
(et non plus `…/data`). Un volume `pgdata` créé par l'ancien service 17 ne s'ouvre pas avec 18. Deux
façons de passer :

```bash
# Garder ses données : dump avec l'ancienne image (avant de récupérer ce changement), puis restauration
docker compose exec -T db pg_dump -U fs -Fc fs > ~/fs-local.dump
docker compose down -v                    # supprime le volume 17
docker compose up -d db                   # postgres:18, volume neuf
docker compose exec -T db pg_restore -U fs -d fs --no-owner < ~/fs-local.dump
docker compose up -d --build              # migrate, api, worker

# Ou repartir de zéro (la base locale est jetable) : les migrations recréent tout
docker compose down -v && docker compose up -d --build
```

La restauration se plaint du rôle `freightsight_app`, absent d'un volume neuf, et sort en code 1 :
les données sont bien là, et l'API locale se connecte en `fs`, qui n'en a pas besoin.
