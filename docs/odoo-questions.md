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
- **Les grosses bases.** Les commandes sont maintenant lues par pages de 200 avec un **curseur sur
  l'id** (jamais un offset : le personnel du client continue de confirmer des commandes pendant la
  synchronisation, et un offset sauterait ce qui s'insère entre deux pages). Les lignes, produits et
  UdM d'une même page restent lus en un appel chacun. Le filtre `write_date >=` existe dans le port
  mais **rien ne s'en sert encore** : chaque synchronisation relit tout. → L'import incrémental est
  le prochain geste, avant le premier client à gros volume.

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
- **Une commande annulée est marquée, jamais supprimée** (`purchase_orders.status = CANCELLED`,
  `cancelled_at`) — décision provisoire prise avec freightsight-fa, à confirmer avec un partenaire.
  Elle peut déjà porter des coûts et des conteneurs, et la supprimer réécrirait un coût de revient en
  silence. Une commande annulée que nous n'avons **jamais vue** n'est pas créée : elle n'a rien à
  nous dire. Le statut ne change rien à la ventilation : les chargements existants continuent de
  recevoir leur part, parce que la marchandise, elle, a bien voyagé.

## 5. Reproduire l'instance de test

```bash
docker network create odoo-test
docker run -d --name odoo-db --network odoo-test \
  -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres postgres:16
docker run -d --name odoo17 --network odoo-test -p 8169:8069 \
  -e HOST=odoo-db -e USER=odoo -e PASSWORD=odoo odoo:17
docker exec odoo17 odoo -d fstest -i purchase,stock_landed_costs --stop-after-init \
  --db_host odoo-db --db_user odoo --db_password odoo
# puis : http://localhost:8169, base fstest, admin / admin
python backend/scripts/odoo_seed.py --url http://localhost:8169 --db fstest
```

`stock_landed_costs` est nécessaire pour l'écriture retour ; `purchase` seul suffit pour la lecture.

`scripts/odoo_seed.py` amène l'instance à l'état exact d'où une landed cost est poussable, en
XML-RPC uniquement (aucun écran) : catégorie `fifo` + `real_time`, produit `TYR-20555R16` avec SKU,
commande confirmée, réception **validée**. Il est idempotent — deux exécutions donnent le même état
et le même résumé — et il imprime le numéro de commande, le SKU et la quantité à recréer côté
FreightSight. Sur une base `fstest` fraîche il redonne les identifiants des fixtures (produit 37,
commande `P00012`, réception `WH/IN/00007`, mouvement 40), ce qui rend les captures rejouables.

Deux pièges qu'il encapsule : la catégorie doit être écrite en `fifo` / `real_time` (tous les
produits de démonstration sont en `standard` / `manual_periodic`, et Odoo ne refuse qu'**à la
validation**, donc après notre écriture) ; et en 17 il faut poser `quantity` **et** `picked` sur
chaque mouvement avant `button_validate`, sinon Odoo répond un assistant « transfert immédiat » —
un dictionnaire là où on attendait un état.

Les tests n'en ont pas besoin : ils rejouent les fixtures capturées.


---

# Écriture retour : la landed cost (9 septembre 2026)

**Vérifié sur un vrai Odoo 17** avec le module `stock_landed_costs`, pas seulement sur des fixtures :
catégorie de produit en FIFO + valorisation automatisée, commande d'achat confirmée, réception
validée (WH/IN/00007), puis `stock.landed.cost` créée par notre code, relue, et vérifiée ligne à
ligne. Les fixtures de test sont les réponses de cette instance.

## 12. La réponse à la question ouverte : on ne peut pas poser les ventilations à la création

`valuation_adjustment_lines` **n'est pas exploitable en création** : Odoo les calcule lui-même (il en
a créé une à la création, puis l'a remplacée au `compute_landed_cost`). En revanche
`additional_landed_cost` sur chacune de ces lignes **est modifiable ensuite**. La séquence qui marche,
mesurée :

1. `create` de la `stock.landed.cost` avec `picking_ids`, `account_journal_id`, `target_model='picking'`
   et une `cost_lines` par coût réel (montant = ce que **notre** moteur a ventilé sur ce conteneur) ;
2. `compute_landed_cost` — Odoo génère ses lignes de ventilation avec **sa** répartition ;
3. `write` de `additional_landed_cost` sur chaque ligne avec **notre** montant exact ;
4. on s'arrête là : l'objet reste en `draft`.

Vérifié en vrai sur deux coûts : `LC` en brouillon à 3 041,67 avec deux lignes de ventilation portant
2 766,67 et 275,00, chacune rattachée au bon `stock.move` et à la bonne `cost_line`.

**L'appariement se fait sur l'`id` de la ligne de coût, pas sur son libellé** : Odoo tronque le nom
qu'il stocke et un utilisateur peut le renommer, donc apparier sur le texte écrirait silencieusement
zéro ligne. C'est le genre de bug qui ne se voit qu'en production, sur les livres de quelqu'un
d'autre.

Conséquence de conception : **une `cost_lines` par coût réel**, avec pour montant la somme de nos
ventilations sur ce conteneur — ainsi `amount_total` de la landed cost égale la somme des
ventilations, et le comptable ne voit pas un total qui ne correspond pas à ses lignes.

## 13. Ce qui bloque, et qu'on refuse avant d'écrire

- **Produit non valorisé en coût réel.** Odoo refuse la landed cost à la validation si la catégorie
  n'est pas en valorisation automatisée avec FIFO ou coût moyen — c'est-à-dire **après** que nous
  aurions écrit. On lit `valuation` et `cost_method` sur le produit et on refuse avant, avec la
  raison. (Les données de démo d'Odoo sont toutes en `standard` / `manual_periodic` : le cas par
  défaut est le cas bloquant.)
- **Aucune réception faite** pour la commande : une landed cost s'accroche à une réception.
- **Plusieurs réceptions** pour les commandes du conteneur (livraison partielle) : on ne devine pas
  laquelle, on le dit. → À trancher avec un partenaire : répartir au prorata des quantités reçues ?
- **Ligne sans correspondance** : l'appariement se fait sur le SKU (`default_code`), seul
  identifiant que les deux systèmes partagent. Une ligne sans SKU des deux côtés n'est pas poussée.
- **Coûts déjà poussés** : un second appel renvoie le premier `erp_pushes`, il n'écrit pas un
  deuxième document dans les livres de quelqu'un.

## 13 bis. La TVA import ne part jamais dans Odoo (audit externe, 10 septembre 2026)

`_allocations` ne filtrait que sur `status is ACTUAL`. Une TVA import facturée — allouée pour la vue
trésorerie mais **récupérable**, donc exclue du coût de revient partout ailleurs — serait donc partie
dans la landed cost et aurait gonflé la valorisation de stock du client d'une taxe qu'il récupère.
Corrigé en réutilisant `engine.EXCLUDED_FROM_LANDED`, la liste du moteur lui-même : une seconde liste
ici aurait dérivé de la première au premier type de coût ajouté. Test : conteneur avec fret + TVA
import → l'aperçu ne montre que le fret, et le total aussi.

## 13 ter. Les bloquants sont traduisibles

Chaque bloquant porte maintenant `params`, les valeurs dynamiques de sa phrase, à côté du `message`
anglais qui ne bouge pas (les clients API le lisent). Un écran écrit donc sa propre phrase dans sa
propre langue au lieu d'afficher la nôtre en dessous d'un titre traduit.

| code | params |
|---|---|
| `no_erp_connection` | — |
| `no_actual_costs` | — |
| `no_receipt` | `po_numbers` |
| `multiple_receipts` | `count`, `receipts` |
| `not_valued` | `products` |
| `unmatched_line` | `po_number`, `line_no`, `sku`, `receipt` |
| `already_pushed` | `existing` |

Deux conventions : les listes sont **déjà jointes par « , »** (une chaîne, pas un tableau), et un SKU
absent vaut `""` — c'est à l'écran de décider si ça se dit « sans SKU » ou « SKU manquant », pas à
nous de lui faire analyser notre anglais.

**`multiple_receipts` est un code nouveau.** Il partageait `no_receipt` avec « aucune réception
trouvée », et aucun écran ne peut écrire deux phrases différentes à partir d'une seule clé de
traduction : « aucune réception pour P00012 » et « 2 réceptions correspondent » ne sont pas la même
information.

## 14. Ce que je n'ai pas vérifié

**Je n'ai pas regardé l'écran Odoo.** Me connecter à l'interface demandait de taper un mot de passe
dans un formulaire, ce que je ne fais pas, même sur un conteneur jetable que je viens de créer. Tout
ce qui est écrit ci-dessus vient de la lecture XML-RPC des enregistrements réellement créés
(`name`, `state`, `amount_total`, `cost_lines`, `valuation_adjustment_lines`, `former_cost`,
`additional_landed_cost`, `final_cost`). → Si tu veux la capture d'écran, l'instance se recrée en
quatre commandes (section 5) et `admin` / `admin` t'y connecte en dix secondes.

**Pas de validation, jamais.** `button_validate` poste des écritures comptables ; c'est la décision
de celui dont ce sont les livres, dans son écran à lui.

**Le produit « landed cost »** est cherché automatiquement (`landed_cost_ok = True`, le premier par
id) et le journal aussi (premier journal `general`). Si le client en a plusieurs, on prend le premier,
ce qui est un choix par défaut discutable. → À rendre configurable sur la connexion ERP le jour où un
partenaire s'en plaint.
