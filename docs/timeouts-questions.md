# Délais d'attente sortants — l'audit du 12 septembre 2026

Toutes les briques de cette application qui parlent à quelqu'un d'autre, passées en revue après la
découverte que le connecteur Odoo n'avait **aucun** délai d'attente (voir `odoo-questions.md`
section 17). Le but n'est pas d'éviter une mauvaise valeur : c'est d'éviter un fil d'exécution garé
sur une socket. Le worker prend des `queueing_lock`, donc un tiers injoignable arrête du travail qui
n'a rien à voir avec lui.

## Ce que l'audit a trouvé

**Bonne nouvelle d'abord : tout le reste était borné.** Odoo était le seul cas de blocage infini.
Les six autres adaptateurs avaient bien un délai. Le défaut était ailleurs, et il est réel.

**`httpx.Client(timeout=300.0)` pose 300 secondes sur les *quatre* phases** : connexion, lecture,
écriture, attente du pool. Or **se connecter et attendre une réponse ne sont pas la même question**.
Une connexion TCP vers une machine qui répond prend des millisecondes ; cinq secondes de connexion
veulent dire que personne n'écoute. Lire une sauvegarde de deux cents mégaoctets ou une complétion de
modèle prend légitimement des minutes. En leur donnant un seul nombre, on rend un hôte **mort**
indiscernable d'un hôte **lent** : on paie le budget du cas lent pour découvrir que l'hôte n'existe
plus. Concrètement, avant ce commit :

| adaptateur | budget unique | ce que coûtait un hôte disparu |
|---|---|---|
| S3 (sauvegardes) | 300 s | 5 minutes par tentative, la nuit |
| extraction LLM | 120 s | 2 minutes de worker **par facture** |
| S3 (documents) | 30 s | 30 s dans une requête, devant un humain |
| Shipsgo | 30 s | 30 s par conteneur interrogé |
| Terminal49 | 20 s | idem |
| Resend | 15 s | 15 s par organisation dans l'envoi du digest |
| FX (Frankfurter) | 5 s | acceptable |

`app/core/http.py` sépare les deux : `timeout(read)` garde le budget de lecture que le travail
demande honnêtement et fixe la connexion (et le pool) à **5 secondes**.

## Le JWKS de Clerk

Cas à part, et le plus exposé : il est sur le chemin de **chaque requête authentifiée**. PyJWT borne
déjà `PyJWKClient` à 30 secondes par défaut — donc pas de blocage infini, contrairement à ce que je
craignais avant de vérifier — mais 30 secondes est très long pour un document de quelques kilooctets
servi par un CDN, et un défaut de cache (rotation de clé, worker froid) le met devant quelqu'un qui
attend. Posé explicitement à 5 s (`JWKS_TIMEOUT_SECONDS`).

## Une valeur par appel, et pas une constante globale

Chaque adaptateur déclare son `TIMEOUT_SECONDS` à côté du code qui s'en sert, avec la raison. Un
seul nombre pour tout le monde serait faux dans les deux sens : trop court pour l'envoi d'une
sauvegarde, absurdement long pour un POST à Resend. Seul Odoo est réglable par variable
d'environnement (`ERP_TIMEOUT_SECONDS`) parce que les clients hébergent eux-mêmes des instances de
tailles très différentes ; les autres visent des services que nous connaissons.

**Limite assumée pour Odoo** : XML-RPC passe par `http.client`, qui n'a **qu'un** bouton — la même
valeur sert à la connexion et à la lecture. Les 60 secondes sont donc le budget de lecture, et un
hôte disparu coûte 60 secondes au lieu de 5. Séparer les deux demanderait de réécrire `connect()`,
ce qui n'en vaut pas le prix tant que l'appelant est un job nocturne.

## La garde qui reste

`tests/test_outbound_timeouts.py` ne teste pas un adaptateur, il garde la règle :

- chaque client construit a bien 5 s de connexion et une lecture finie ;
- chaque adaptateur utilise réellement le `TIMEOUT_SECONDS` écrit à côté de lui (pas un littéral qui
  a dérivé du commentaire qui l'explique) ;
- aucun budget n'est absurde dans un sens ou dans l'autre ;
- un hôte qui **jette** les paquets (198.51.100.7, TEST-NET-2 — le comportement d'un pare-feu de
  client qui change, pas un refus de connexion) est abandonné sur le budget de connexion et pas sur
  celui de lecture ;
- et un balayage du source qui **échoue** si un `httpx.Client(` / `httpx.get(` / … part sans
  `timeout`. C'est celui qui attrapera l'adaptateur écrit l'an prochain. Vérifié en retirant un
  délai exprès : il l'attrape.

## Ce qui reste ouvert

- **Pas de disjoncteur.** Le backoff existe pour l'ERP seulement (`odoo-questions.md` §17). Un
  Shipsgo en panne sera réinterrogé à chaque tour de `poll_stale_subscriptions`, sans pénalité —
  borné à 30 s par conteneur, mais multiplié par le nombre de conteneurs. → C'est le sujet suivant,
  avec les chemins d'erreur du worker de tracking.
- **Pas de nouvelle tentative** sur une coupure passagère : un appel qui expire échoue, et c'est le
  tour suivant qui réessaie. Volontaire pour l'instant — réessayer tout de suite le même hôte muet
  ne fait que payer le délai deux fois.
