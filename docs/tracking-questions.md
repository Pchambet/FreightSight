# Suivi conteneur — questions ouvertes

Ce que la documentation publique de Terminal49 (et le plan) ne tranchent pas, et ce que le code fait
en attendant. Rien ici n'est inventé côté code : chaque point est isolé dans une seule fonction ou
une seule table, pour être corrigé en une ligne quand on aura la réponse.

Sources consultées le 9 septembre 2026 : `terminal49.com/docs/api-docs/in-depth-guides/webhooks`,
`/webhooks/payloads`, `/webhooks/event-catalog`, `/api-reference/containers/get-a-containers-transport-events`,
`/api-reference/tracking-requests/create-a-tracking-request`.

## 1. Fraîcheur d'une livraison (TTL)

Terminal49 signe le corps brut (HMAC-SHA256, hex, en-tête `X-T49-Webhook-Signature`) mais **ne publie
aucun en-tête d'horodatage**. Une signature seule ne dit pas si le corps est d'aujourd'hui : un corps
capturé et rejoué plus tard reste valablement signé.

En attendant : la fraîcheur est jugée sur le `created_at` de la notification elle-même, fenêtre par
défaut 15 minutes (`TRACKING_WEBHOOK_MAX_AGE_SECONDS`). Une notification sans `created_at` passe sur
la seule signature. → À confirmer avec leur support : existe-t-il un en-tête d'horodatage, et
recommandent-ils une allowlist d'IP ?

## 2. Quel « last free day » fait foi

Le conteneur expose `pickup_lfd`, `pickup_lfd_line`, `pickup_lfd_rail`, `pickup_lfd_terminal`, et il
existe des événements `container.pickup_lfd*.changed`.

En attendant : **on ne lit aucun de ces champs**. Le LFD affiché est le nôtre,
`déchargement + jours francs − 1`, jours calendaires, les jours francs venant du conteneur, sinon du
réglage par armateur de l'organisation, sinon de son défaut. → À trancher avec un design partner :
quand le terminal annonce un LFD différent du nôtre, lequel affiche-t-on, et lequel déclenche
l'alerte ? (Mon avis : afficher les deux, alerter sur le plus proche.)

## 3. Routage d'une livraison vers un conteneur

Une livraison arrive sans locataire. Deux chemins : la référence du fournisseur
(`tracking_subscriptions.provider_ref`, l'id de conteneur Terminal49), ou le numéro de boîte quand le
déploiement est en mode webhook seul (pas de clé API, donc pas d'abonnement créé par nous).

Le numéro de conteneur n'est pas unique dans le temps ni entre clients : deux organisations peuvent
suivre la même boîte. Dans ce cas la fonction `tracking_resolve_subscription` ne renvoie rien et la
livraison est enregistrée `unroutable` plutôt que rattachée au hasard. → Si le cas se produit en vrai,
il faudra une clé API par organisation, ou un secret de webhook par organisation.

## 4. Événements sans correspondance

Le catalogue liste une trentaine d'événements ; la table de correspondance est dans
`app/adapters/tracking/terminal49.py` (`EVENT_MILESTONES`). Tout ce qui n'y figure pas est stocké en
`UNKNOWN`, avec sa description d'origine : visible dans la timeline, sans effet sur le jalon du
conteneur. C'est ce qui permettra d'enrichir la table sur des cas réels.

Choix discutables déjà faits :
- `vessel_berthed` → `VESSEL_ARRIVED` (à quai, c'est arrivé).
- `feeder_*` → les jalons de transbordement (un feeder est une jambe intermédiaire).
- `arrived_at_inland_destination` → `DELIVERED`.
- `container.transport.available` → `AVAILABLE_FOR_PICKUP`.

## 5. Clé de dédoublonnage

Un événement est identifié par `(id de transport_event, nom, timestamp, estimé ou non)` haché. L'id
seul ne suffit pas : la documentation ne dit pas si Terminal49 réémet le même id quand un jalon est
corrigé. La conséquence du choix actuel est sûre dans le bon sens : au pire une correction crée une
ligne de plus, jamais une ligne écrasée. → À vérifier sur des vraies données.

## 6. Détention (retour du vide)

`detention_deadline = sortie du terminal + jours francs de détention − 1` est dans le plan mais n'a
pas encore de colonne : seul le LFD de surestaries est calculé. → À faire quand un partenaire aura un
vrai litige de détention, avec sa règle de comptage.

## 7. Ce qui manque encore côté file d'attente

Le traitement d'une livraison est synchrone : on répond 200 dès qu'elle est stockée, puis on traite
dans la foulée. Tant qu'il n'y a pas de charge, c'est la version la plus simple qui soit juste. La
reprise (rejouer une livraison `failed`), la relance périodique (`fetch` sur un abonnement muet depuis
48 h) et le recalcul quotidien du risque à 06:00 viendront avec Procrastinate, en même temps que
l'extraction de factures.
