# Estimé → réel — questions ouvertes

## 1. Ce qu'un estimé remplacé garde, et ce qu'il perd

Demandé : « un estimé remplacé sort de la ventilation courante mais reste en base, **avec son
historique d'allocation** ». Il reste en base, avec son montant, sa méthode et son périmètre. Ses
lignes de `cost_allocations`, elles, **ne sont pas conservées** : cette table est la matérialisation
de la ventilation *courante*, recalculée en entier à chaque écriture, et y laisser les lignes d'un
estimé remplacé casserait l'invariant « la somme des allocations d'un load = son coût de revient
actuel ».

Ce n'est pas une perte : l'écart par ligne est calculé en **rejouant l'estimé remplacé dans le
moteur**, avec son propre périmètre et sa propre méthode (`report.estimate_allocations`). L'écart
d'une ligne est donc la différence de deux vraies ventilations, exacte au centime, et non une
proportion inventée après coup. C'est vérifié : sur un conteneur 600/400 en valeur, un écart de
120,50 se répartit en 72,30 et 48,20, qui se rajoutent bien à 120,50.

→ Si tu veux une trace figée (« voilà ce que l'estimé donnait le jour où il a été remplacé »), il
faut une table d'instantanés. Je ne l'ai pas faite : le rejeu donne le même chiffre tant que les
chargements ne bougent pas, et s'ils bougent, le rejeu est *plus* juste qu'un instantané périmé.

## 2. La jauge de complétude compte des types, pas des montants

`completeness` = part des types de coûts vus sur ce périmètre qui ont une facture réelle. Volontaire :
une PME veut savoir lesquels des six postes attendus sont arrivés, et une grosse facture de fret ne
doit pas faire passer une facture de douane manquante pour une erreur d'arrondi. Un type connu
uniquement par un estimé remplacé compte comme facturé — sa facture est précisément ce qui l'a
remplacé.

Limite assumée : les types « attendus » sont ceux qu'on **voit** (estimé ou réel). Un poste que
personne n'a ni estimé ni facturé n'existe pas pour la jauge. → La vraie liste des postes attendus
serait celle du barème de l'organisation ; à faire quand les barèmes seront remplis pour de vrai.

## 3. Ce que la confirmation de facture décide, et ce qu'elle refuse de décider

Un seul estimé ouvert du même type sur la même cible → il est remplacé. Plusieurs → **aucun** n'est
remplacé, et la réponse le dit en clair (`notes`). Deviner reviendrait à faire disparaître un estimé
réel du coût de revient sans que personne ne l'ait décidé.

→ Question produit : faut-il proposer un choix dans l'écran de relecture (« cette facture solde
laquelle de ces deux estimations ? ») ? Je pense que oui, mais c'est ton écran.

## 4. Les barèmes ne couvrent pas tous les périmètres

`POST /containers/{id}/estimates` applique les barèmes de périmètre CONTAINER et SHIPMENT. Les
barèmes PO et PO_LINE sont acceptés par le schéma mais **pas appliqués** ; l'endpoint le dit dans
`skipped` plutôt que de les ignorer en silence. → À faire si un partenaire facture réellement par
commande.

Autre limite : un barème SHIPMENT appliqué depuis un conteneur crée un coût au niveau expédition, une
seule fois (le deuxième conteneur de la même expédition trouve le coût déjà là). C'est correct mais
non évident : deux clics sur deux conteneurs frères ne donnent pas deux fois le même coût.

## 5. Droits théoriques

Calculés sur la valeur en douane du moteur (FOB + postes dutiables déjà ventilés), avec le taux de
la ligne, sinon le taux d'un barème CUSTOMS_DUTY dont le code SH est un préfixe du code de la ligne
(le plus long gagne, comme se lit un tarif douanier). Aucun taux nulle part → aucun estimé, et
`skipped` dit « no tariff rate on these lines ».

Ce que ça ne fait pas : les droits antidumping, les contingents, les préférences d'origine. Un chiffre
faux serait pire que pas de chiffre. → Sujet à rouvrir avec un vrai déclarant en douane.

## 6. Le désabonnement automatique

Un conteneur livré (DELIVERED ou GATE_IN_EMPTY_RETURN) dont le retour du vide — sinon la sortie du
terminal — date de plus de 7 jours est désabonné, tâche quotidienne à 04:30 UTC. Si le fournisseur
refuse le désabonnement, **l'abonnement reste ouvert** et l'erreur est enregistrée : il continuera
de facturer tant que personne ne s'en occupe, et fermer notre ligne masquerait ça.

## 7. Divers

- `by_cost_type` garde son sens actuel (total ventilé par type) ; le détail estimé/réel est dans un
  nouveau champ `by_cost_type_detail`, pour ne pas casser l'écran existant.
- Le rapport d'écart ne compte **que** les paires (réel, estimé remplacé) du mois. Une facture que
  personne n'avait prévue n'a rien à quoi se comparer, et la compter en dépassement de 100 % serait un
  mensonge par arithmétique. Elle apparaît dans la complétude, pas dans l'écart.
- Supprimer un barème ne touche pas aux estimations qu'il a produites : ce sont des coûts, plus des
  dérivations.
