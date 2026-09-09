# Connecteur Odoo — ce que j'ai vu sur un vrai Odoo, et ce qui reste ouvert

**Vérifié pour de vrai**, pas seulement sur des fixtures : `odoo:17` + `postgres:16` en local,
base `fstest` initialisée avec le module `purchase` et ses données de démonstration, authentification
XML-RPC et lecture réelles (`17.0-20260908`, 10 commandes, uid 2). Les fixtures de test
(`backend/tests/fixtures/odoo/purchase_orders.json`) sont **des réponses capturées de cette instance**,
pas des inventions.

## 1. Trois choses que le vrai Odoo m'a apprises

**La quantité d'une ligne est dans l'unité de la ligne, pas dans celle du produit.** Les données de
démonstration commandent « 20 Dozens » d'un produit dont le poids est au *pièce*. Importer 20 là où
le client veut dire 240 sous-estimerait toutes les ventilations au poids — c'est-à-dire une erreur
silencieuse sur le coût de revient. L'adapter convertit avec le rapport d'UdM et divise le prix
unitaire d'autant.

Reste un résidu assumé : 500 par douzaine devient 41,6667 par pièce (la précision de notre colonne),
soit un total de 10 000,008 au lieu de 10 000. Huit millièmes sur dix mille, visibles dans un test,
invisibles dans un coût de revient. → Si ça gêne un jour, il faudra stocker le prix à plus de quatre
décimales, ou garder l'UdM d'origine et convertir au moment de la ventilation.

**`hs_code` n'existe pas sur `product.product` en Odoo 17 Community.** Il arrive avec des modules de
localisation ou l'Enterprise. L'adapter demande à `fields_get` ce que l'instance possède et ne lit le
champ que s'il est là, au lieu d'échouer chez un client qui ne l'a pas. Les codes SH resteront donc
souvent vides à l'import ; c'est le barème douanier de l'organisation qui prendra le relais.

**Un mauvais mot de passe n'est pas une exception** : `authenticate` renvoie `False`. Un appelant qui
ne teste pas se retrouve avec `uid = False` et un échec incompréhensible trois appels plus loin. Un
mauvais *champ*, lui, lève un `Fault` contenant une trace Python complète, dont seule la dernière
ligne est montrable à un humain — c'est ce que fait `_fault_reason`.

## 2. Ce que je n'ai pas pu vérifier

- **Une clé API Odoo** (Préférences → Sécurité du compte → Clés API) plutôt que le mot de passe
  administrateur : le principe est le même côté XML-RPC (la clé se passe à la place du mot de passe),
  mais je n'en ai pas créé une sur l'instance de test. → À confirmer chez le premier client.
- **Odoo Online (odoo.com)** : XML-RPC y est ouvert, mais avec des limites de débit dont je n'ai pas
  la valeur. → À surveiller au premier client hébergé chez eux.
- **Les grosses bases.** La lecture fait quatre appels (commandes, lignes, produits, UdM) sans
  pagination. Sur 50 000 commandes, `search_read` sans limite est une mauvaise idée. Le filtre
  `write_date >=` existe déjà dans le port ; ce qui manque, c'est de s'en servir pour un import
  incrémental et de paginer. → À faire avant le premier client à gros volume, pas avant.

## 3. Choix de conception

- **L'import passe par le pipeline existant.** Les lignes Odoo sont écrites en CSV dans nos colonnes
  canoniques et données au même code qu'un tableur déposé à la main : mêmes clés naturelles, même
  idempotence, même rapport ligne à ligne, même `ImportJob` consultable. Un second chemin d'écriture
  serait un second endroit où les règles dérivent.
- **Le test de connexion précède l'enregistrement.** Une connexion enregistrée qui n'a jamais réussi
  à s'authentifier est une promesse que la prochaine synchronisation va rompre, et l'erreur d'Odoo
  est bien plus utile pendant que la personne a encore les identifiants sous les yeux.
- **La clé API est scellée** (AES-GCM, `ERP_ENCRYPTION_KEY`, magie `FSERP1`) et n'est jamais renvoyée
  par l'API, sous aucune forme. C'est un identifiant vers la comptabilité d'un client : la chose la
  plus sensible que cette application détiendra.
- **Une seule connexion par organisation** pour l'instant. Un groupe avec deux sociétés Odoo devra
  attendre ; la contrainte est explicite plutôt qu'implicite.
- **Rien n'est écrit vers Odoo.** La `stock.landed.cost` est une autre brique, et écrire dans la
  compta d'un client a un prix de l'échec bien plus élevé que lire.

## 4. Sur la synchronisation

- `POST /erp/sync` est **synchrone** : quelqu'un vient de connecter son Odoo et regarde le bouton. Le
  rafraîchissement quotidien (05:15 UTC) est le job.
- Une synchronisation qui échoue laisse une ligne `erp_sync_runs` qui dit pourquoi, et le message est
  aussi posé sur la connexion (`last_error`). Une synchronisation qui échoue en silence, c'est un
  client qui croit ses commandes à jour.
- Le job traite chaque organisation dans sa propre transaction : l'Odoo cassé d'un client n'empêche
  pas les autres de se synchroniser.
- **Pas de suppression.** Une commande annulée dans Odoo n'est pas retirée de chez nous : elle a
  peut-être déjà des coûts et des conteneurs. → À trancher avec un partenaire : ignorer, marquer, ou
  supprimer si rien n'y est rattaché ?

## 5. Reproduire l'instance de test

```bash
docker network create odoo-test
docker run -d --name odoo-db --network odoo-test \
  -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres postgres:16
docker run -d --name odoo17 --network odoo-test -p 8169:8069 \
  -e HOST=odoo-db -e USER=odoo -e PASSWORD=odoo odoo:17
docker exec odoo17 odoo -d fstest -i purchase --stop-after-init \
  --db_host odoo-db --db_user odoo --db_password odoo
# puis : http://localhost:8169, base fstest, admin / admin
```

Les tests n'en ont pas besoin : ils rejouent les fixtures capturées.
