# Passer sur un vrai domaine : la bascule en une heure

Préparé le 18 septembre 2026. Rien de ceci n'est fait : acheter le domaine et toucher aux comptes
(Vercel, Clerk, Railway, Resend) sont des décisions de Pierre. Ce document permet de le faire le jour
dit, dans l'ordre, sans rien oublier.

## Pourquoi maintenant

La production tourne sur l'instance Clerk de **développement**, parce que Clerk refuse les clés de
production sur une adresse `*.vercel.app`. Cela a quatre conséquences :

- **Le site n'est ni indexable ni prévisualisable.** Mesuré le 18/09 en production, avec l'agent
  Googlebot :
  - `/`, `/securite` et `/design-partner` renvoient des redirections 307 en boucle vers la poignée
    de main de Clerk ;
  - `/robots.txt`, `/sitemap.xml` et les images `opengraph-image` aussi, dès que la requête accepte
    du HTML.

  Le correctif du middleware (commit 81858bb, étendu aux routes de métadonnées) contourne le problème.
  Seule une instance de production le supprime.
- **Limites de l'instance de développement** : 100 utilisateurs au plus et un bandeau
  « Development » sur les pages de connexion. Pas sérieux devant un prospect.
- **Pas d'e-mails d'alerte.** Resend exige un domaine vérifié (SPF, DKIM). Aujourd'hui, les alertes
  surestaries partent dans les journaux, pas chez le client (`/service-status` le dit).
- **La prospection par e-mail n'a pas d'adresse d'envoi crédible.**

## Le nom

État relevé le 18/09 (DNS et `whois`) :

| Nom | État |
|---|---|
| `freightsight.fr` | **libre** (AFNIC : « NOT FOUND ») |
| `freightsight.com` | pris, parqué chez Afternic (revente, prix inconnu) |
| `freightsight.eu`, `.io`, `.app` | aucune délégation DNS, probablement libres (à confirmer chez le registraire) |
| `getfreightsight.com` | pris |

Recommandation : **`freightsight.fr`**. Clientèle française, une dizaine d'euros par an, et un
registraire français accrédité AFNIC (OVHcloud, Gandi…) qui héberge aussi la zone DNS. Ajouter
`freightsight.eu` pour protéger le nom. Le `.com` peut attendre.

Dans la suite, `<domaine>` désigne le nom retenu.

## La bascule, dans l'ordre

Compter une heure de manipulations, plus le temps de propagation DNS (quelques minutes à quelques
heures). À faire à un moment creux : entre les étapes 2 et 3, la connexion est coupée quelques
minutes.

### 1. Le site sur le domaine (Vercel)

1. Vercel → projet → *Settings → Domains* : ajouter `<domaine>` et `www.<domaine>`. Poser dans la
   zone DNS les enregistrements que Vercel affiche. D'ordinaire, c'est un `A` sur l'apex et un
   `CNAME www` ; recopier les valeurs du tableau de bord, ne pas les inventer.
2. Choisir l'adresse principale (l'apex) : `www` et `freight-sight-two.vercel.app` y redirigent.
3. Variable Vercel `NEXT_PUBLIC_SITE_URL=https://<domaine>` (Production). Elle alimente le sitemap
   et les URL Open Graph (`frontend/src/lib/site.ts`).

### 2. L'instance Clerk de production

1. Tableau de bord Clerk : *Create production instance*, en clonant les réglages de développement.
   Domaine de l'application : `<domaine>`.
2. Poser dans la zone DNS les enregistrements que Clerk affiche. Ce sont d'ordinaire cinq `CNAME` :
   - `clerk.` (l'API frontale) ;
   - `accounts.` ;
   - `clkmail.` ;
   - `clk._domainkey.` et `clk2._domainkey.`.

   Attendre que Clerk les déclare vérifiés et que les certificats soient émis.
3. Vérifier sur l'instance de production ce que le clonage est censé avoir repris :
   - Organizations activées, *membership required* (choix forcé d'une organisation) ;
   - jeton de session avec les trois claims personnalisés que l'API lit
     (`backend/app/adapters/auth_clerk.py`) :
     `{"email": "{{user.primary_email_address}}", "name": "{{user.full_name}}", "org_name": "{{org.name}}"}`.
     Sans `org_name`, une société créée à la première connexion s'appelle « New organization » ;
   - origines autorisées : `https://<domaine>` ;
   - méthodes de connexion. **Une connexion Google en production exige ses propres identifiants
     OAuth** (l'instance de développement prête les siens).
4. Récupérer les clés `pk_live_…` / `sk_live_…`.

### 3. Les clés, des deux côtés en même temps

- **Vercel (Production seulement ; Preview garde `pk_test_`)** : `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
  et `CLERK_SECRET_KEY`, puis redéployer.
- **Railway, service `FreightSight`** (l'API). Ces variables sont en `preserve()` dans
  `.railway/railway.ts` : on les change dans le tableau de bord ou avec `railway variables --set`,
  **sans** `railway config apply`.

| Variable | Nouvelle valeur |
|---|---|
| `CLERK_ISSUER` | `https://clerk.<domaine>` |
| `CLERK_JWKS_URL` | `https://clerk.<domaine>/.well-known/jwks.json` |
| `CLERK_AUTHORIZED_PARTIES` | `["https://<domaine>"]` |
| `CORS_ORIGINS` | `["https://<domaine>"]` |

**Noter les anciennes valeurs avant de les remplacer** : ce sont celles du retour arrière.

### 4. Les données existantes

L'API relie une société à Clerk par `organizations.external_id`, un utilisateur par
`users.external_id` (`backend/app/core/auth.py`, `_mirror_and_resolve`). Une instance de production
émet de **nouveaux** identifiants (`org_…`, `user_…`). À la première connexion, l'API crée donc une
société vide ; les données de l'ancienne restent en base, invisibles.

- **Recommandé aujourd'hui (aucune donnée client réelle)** : repartir à neuf. Créer la société de
  démonstration dans l'instance de production, s'y connecter, charger l'échantillon « six mois »
  depuis l'application. Les anciennes lignes ne gênent rien et peuvent être supprimées plus tard.
- **Pour garder une société précise** : la créer, avec son utilisateur, dans l'instance de
  production **avant toute connexion**. Puis ré-associer les identifiants en tant que propriétaire
  de la base (`railway connect PostgresEU`) :

  ```sql
  -- retrouver les anciens identifiants
  SELECT id, name, external_id, created_at FROM organizations ORDER BY created_at;
  SELECT id, email, external_id FROM users ORDER BY created_at;
  -- les remplacer par ceux de l'instance de production (visibles dans le tableau de bord Clerk)
  UPDATE organizations SET external_id = 'org_NOUVEAU' WHERE external_id = 'org_ANCIEN';
  UPDATE users SET external_id = 'user_NOUVEAU' WHERE external_id = 'user_ANCIEN';
  ```

  Faite après une première connexion, l'opération bute sur la contrainte d'unicité : la société
  vide créée à cette connexion porte déjà le nouvel identifiant.

### 5. Les e-mails d'alerte (Resend)

1. Resend → *Domains* : ajouter un sous-domaine d'envoi, par exemple `notifications.<domaine>`.
   Poser les enregistrements affichés (SPF, DKIM, MX de retour), plus un DMARC sur le domaine :
   `_dmarc.<domaine>` en `TXT`, `v=DMARC1; p=none; rua=mailto:<boîte de Pierre>`.
2. Créer une clé d'API limitée à l'envoi, et à ce domaine.
3. Sur le service API : `RESEND_API_KEY` et `ALERTS_FROM_EMAIL=alertes@notifications.<domaine>`.
   Le worker les lit depuis l'API (`${{FreightSight.RESEND_API_KEY}}`) ; les deux services se
   redéploient.
4. Contrôle : `GET /service-status` doit dire que les e-mails d'alerte partent.

### 6. Recevoir du courrier

`contact@<domaine>` : la redirection gratuite du registraire (ou Cloudflare Email Routing) vers la
boîte de Pierre suffit. Ensuite, `CONTACT_EMAIL` dans `frontend/src/lib/site.ts` passe sur cette
adresse (voie du front).

### 7. La prospection : jamais depuis ce domaine

Les e-mails de prospection partent d'un domaine **distinct** (un second nom), avec son propre
SPF/DKIM/DMARC et une montée en charge progressive. Une plainte pour spam sur ce domaine-là ne doit
jamais empêcher une alerte surestaries d'arriver chez un client.

### 8. Moteurs de recherche et aperçus

- Google Search Console : vérifier le domaine (TXT DNS), soumettre `https://<domaine>/sitemap.xml`.
- LinkedIn Post Inspector sur l'accueil, pour rafraîchir l'aperçu avant de partager le lien.

### 9. Plus tard, facultatif

`api.<domaine>` sur Railway (CNAME) puis `API_URL` sur Vercel. Utile quand les webhooks des
fournisseurs de suivi seront branchés ; inutile pour la bascule.

## Vérifier

```bash
D=https://<domaine>
GB="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
ACC="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
for p in / /securite /design-partner /robots.txt /sitemap.xml; do
  curl -s -o /dev/null -w "$p %{http_code}\n" -A "$GB" -H "Accept: $ACC" "$D$p"   # 200 partout, aucun 307
done
curl -s https://freightsight-production.up.railway.app/readyz                     # ready
curl -s -H "Authorization: Bearer x" https://freightsight-production.up.railway.app/api/v1/me   # 401
```

Puis, dans un navigateur privé :
1. s'inscrire sur `<domaine>` (plus de bandeau « Development ») ;
2. choisir ou créer une organisation ;
3. vérifier que `/overview` s'ouvre ;
4. charger l'échantillon « six mois » ;
5. vérifier que `/cost-audit` sort l'audit.

## Retour arrière

Remettre les anciennes valeurs, notées à l'étape 3 : clés `pk_test_`/`sk_test_` sur Vercel,
`CLERK_*` et `CORS_ORIGINS` sur l'API, puis redéployer les deux. Les enregistrements DNS peuvent
rester : ils ne font rien tant que les clés de production ne sont pas utilisées.
