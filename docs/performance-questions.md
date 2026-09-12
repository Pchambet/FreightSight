# Requêtes SQL par écran — mesures et questions ouvertes

Mesuré le 12 septembre 2026. La méthode est dans `backend/tests/test_query_counts.py` : un écouteur
`before_cursor_execute` compte **toutes** les instructions envoyées pendant un appel HTTP, sur une
organisation chargée comme une vraie (6 puis 18 conteneurs, 2 fournisseurs, des commandes scindées,
des coûts au conteneur et à l'expédition, des alertes, des factures lues).

Le critère n'est pas « combien », c'est « est-ce que ça grandit ». Un N+1 est invisible sur le jeu de
démonstration à deux conteneurs et fatal sur les trois cents d'un importateur réel : la page marche
toujours, elle met huit secondes, et rien dans la suite de tests ne le dit.

## Ce que coûte chaque écran

| Écran | 6 conteneurs | 18 | 42 | Verdict |
|---|---|---|---|---|
| `GET /containers` (board) | 14 | 14 | 14 | constant |
| `GET /containers/{id}` | 6 | 6 | 6 | constant |
| `GET /containers/{id}/loads` | 6 | 6 | 6 | constant |
| `GET /landed-costs/containers/{id}` | 8 | 8 | 8 | constant |
| `GET /costs` | 3 | 3 | 3 | constant |
| `GET /alerts` | 3 | 3 | 3 | constant |
| `GET /invoices` | 4 | 4 | 4 | constant |
| `GET /invoices/{id}` | 5 | 5 | 5 | constant |
| `GET /reports/variance` | 7 | 7 | 7 | constant |
| `GET /reports/dnd` | 6 | 6 | 6 | constant |
| **`GET /reports/landed-cost`** | **8** | **9** | **10** | **N+1** |

## Le seul N+1 : un appel par fournisseur

`_bucket_key` regroupe par fournisseur en écrivant `row.po_line.purchase_order.supplier`.
`compute()` chargeait bien le lot, sa ligne de commande et la commande, mais **pas** le fournisseur
au bout : chaque fournisseur distinct coûtait donc un aller-retour, découvert bucket par bucket.
Trois fournisseurs, trois requêtes ; un importateur qui travaille avec quarante usines, quarante.

Corrigé en ajoutant `selectinload(PurchaseOrder.supplier)` à la chaîne déjà présente dans
`_load_rows`. Après :

| Écran | 6 | 18 | 42 |
|---|---|---|---|
| `GET /reports/landed-cost` | 8 | 8 | 8 |

Le prix payé, et il est assumé : cette chaîne est celle de `compute()`, que trois autres écrans
appellent, donc ils gagnent **une** requête constante (board 14 → 15, variance 7 → 8,
landed-cost d'un conteneur 8 → 9). Une requête fixe contre une requête par fournisseur. L'autre
solution — charger les fournisseurs seulement dans le rapport — laissait `.supplier` accessible en
chargement paresseux pour le prochain appelant, c'est-à-dire le prochain N+1.

## Deux tests, pas un

- `test_no_endpoint_queries_once_per_row` : on triple les données et **aucun** compteur ne doit
  bouger. C'est celui qui a trouvé le bug.
- `test_hot_endpoints_stay_within_their_query_budget` : plat n'est pas synonyme de bon marché. Un
  écran qui passait de 4 à 20 allers-retours resterait constant tout en étant une régression. Le
  budget est « ce que ça coûte aujourd'hui, plus deux » — une marge pour une requête légitime
  ajoutée, pas pour une boucle.

## Ce qui reste ouvert

- **Le board fait deux passes sur les mêmes tables.** La réponse charge conteneurs + lots + lignes +
  commandes, puis `compute()` recharge lots + lignes + conteneurs + commandes + coûts pour la
  ventilation. Cinq requêtes en double, constantes. Les partager demanderait de passer la
  computation à la sérialisation ou l'inverse ; ce n'est pas un N+1, c'est un facteur deux sur un
  écran déjà à quinze requêtes. À reprendre si le board devient lent avant que le reste ne le
  devienne.
- **`compute()` charge toute l'organisation à chaque appel**, quel que soit l'écran. C'est ce qui
  garde les chiffres cohérents (une seule ventilation fait foi) et c'est aussi le plafond de montée
  en charge de toute la brique. Le jour où une organisation dépasse quelques milliers de lots, la
  question n'est plus le nombre de requêtes mais leur taille. Rien ne le mesure encore.
- **Rien ne mesure le temps**, seulement le nombre d'allers-retours. Un compte constant peut cacher
  une requête qui balaie la table entière. Il faudrait un `EXPLAIN` sur les requêtes du board et des
  rapports, avec des données d'une taille réaliste — et il faudrait de vraies données pour que ça
  veuille dire quelque chose.
