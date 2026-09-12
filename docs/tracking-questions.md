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


---

# Shipsgo (ajouté le 9 septembre 2026)

## 8. J'ai écrit l'adapter sur leur API v2, pas sur la v1.2 demandée

La v1.2 est un PDF (crédit par conteneur, `POST .../ContainerService/PostContainerInfo`, puis
`GET .../GetContainerInfo?authCode=&requestId=`, données rafraîchies trois fois par jour). Elle ne
documente **aucun webhook** ni aucune signature — la page marketing en promet, le document n'en parle
pas. Suivre cette version voulait dire soit un endpoint non authentifié, soit un secret dans l'URL,
c'est-à-dire un secret dans les logs de tous les intermédiaires.

La **v2** (`https://api.shipsgo.com/v2`) est publiée en OpenAPI lisible par une machine, avec
authentification par en-tête `X-Shipsgo-User-Token`, et **des webhooks signés en HMAC-SHA256** dans
`X-Shipsgo-Webhook-Signature`. Mieux : leur documentation publie un **vecteur de test** (secret,
charge utile, signature attendue). Notre implémentation est vérifiée contre **leur** valeur, pas
contre ma lecture de leur prose — c'est le test `test_the_signature_matches_the_vendors_own_published_vector`.

Les fixtures de test sont **leurs propres exemples de réponse**, extraits de la spécification.

→ Si Pierre a un compte v1.2 (crédits déjà achetés) et pas de v2, il faudra un second adapter. À
vérifier au moment de créer le compte : la v2 est-elle incluse dans la même offre ?

## 9. Ce que la v2 ne documente pas

**La forme de la charge utile d'un webhook.** Le schéma `WebhookEvent` ne décrit que l'enveloppe
(`id`, `name`, `triggered_by`) ; ce qui accompagne l'événement n'est pas spécifié. L'adapter accepte
donc l'expédition là où elle se trouve (racine, `shipment`, ou `data`) plutôt que de parier sur une
forme et de casser sur l'autre. → À confirmer sur une vraie livraison.

**Les noms d'événements** auxquels on peut s'abonner ne sont pas listés dans la spécification (ils
sont dans le tableau de bord). → À noter au moment de configurer le webhook.

## 10. Choix de correspondance

Leurs huit codes de mouvement ont tous un équivalent chez nous : `EMSH → GATE_OUT_EMPTY_ORIGIN`,
`GTIN → GATE_IN_FULL_ORIGIN`, `LOAD → LOADED`, `DEPA → VESSEL_DEPARTED`, `ARRV → VESSEL_ARRIVED`,
`DISC → DISCHARGED`, `GTOT → GATE_OUT_FULL`, `EMRT → GATE_IN_EMPTY_RETURN`. Leur champ `status`
(`EST` / `ACT`) donne notre `is_estimate` — le lire à l'envers daterait une arrivée qui n'a pas eu
lieu, et c'est exactement ce sur quoi l'horloge des surestaries se déclenche.

Une expédition **sans mouvement** (Shipsgo n'a pas encore apparié la boîte avec l'armateur) produit
un seul événement dérivé de son statut, daté de `checked_at` et **marqué comme estimation** : un
statut n'est pas un mouvement daté, et lui donner une date réelle inventerait un fait.

## 11. Interrogation plutôt que webhook, pour l'instant

Le job `fetch` existant suffit : Shipsgo facture le crédit à la création du suivi, pas à la lecture,
donc interroger un abonnement déjà payé ne coûte rien de plus. Leurs données bougent trois fois par
jour en v1.2 ; la v2 ne le dit pas, mais notre interrogation toutes les 4 heures est du même ordre.
Le webhook est prêt côté vérification et pourra être branché sans changer le reste.

---

# Durcissement du worker de suivi (12 septembre 2026)

## Une panne de fournisseur n'est pas une panne de conteneur

Le défaut le plus coûteux de cette brique, et il était silencieux. `_poll_one` traitait « le
fournisseur a répondu, il n'a rien » et « je n'ai pas pu joindre le fournisseur » de la même façon :
les deux levaient une alerte `TRACKING_DATA_MISSING` disant *« Check the container on the carrier's
own site »* et passaient le conteneur en `TrackingState.FAILED`.

Conséquence d'une heure de Shipsgo indisponible : **tous** les conteneurs de **tous** les clients
passent au rouge, et chaque client reçoit une alerte par boîte lui disant d'aller vérifier sur le
site de son transporteur — une accusation adressée au mauvais acteur, pour une panne qui est la
nôtre et celle de notre fournisseur.

`_poll_one` renvoie maintenant `ingested` / `quiet` / `unreachable`. Seul `quiet` est une nouvelle
qui concerne la marchandise du client. `unreachable` enregistre la raison dans
`subscription.last_error`, ne touche pas à `tracking_state`, et ne lève rien au niveau du conteneur.

Nouveau `AlertKind.TRACKING_PROVIDER_DOWN` (migration 0018), **une** alerte par fournisseur et par
jour, sans `container_id`, et dont le texte dit explicitement qu'il n'y a rien à faire et rien
d'anormal du côté des conteneurs. Réutiliser `TRACKING_DATA_MISSING` aurait été plus simple et
aurait annulé tout l'intérêt du changement.

## Le coût d'insister

Depuis l'audit des délais d'attente, un appel est borné (30 s pour Shipsgo). Mais **borné par appel
et multiplié par le nombre de conteneurs suivis** : cent boîtes et un fournisseur muet font une
heure de worker — qui tient un `queueing_lock` — passée à apprendre cent fois la même chose.

`ProviderCircuit` arrête d'interroger un fournisseur après **trois échecs d'affilée** (un est un
mauvais conteneur, deux est une coïncidence). *D'affilée* : un fournisseur qui répond à propos d'une
boîte n'est pas en panne, quoi qu'il ait répondu. Le compteur vit le temps d'un balayage et pas
plus : la plupart des pannes durent quelques minutes, et le tour suivant doit réessayer. Même garde
sur `end_delivered_subscriptions`, où l'enjeu est différent — un fournisseur qui continue de
facturer des conteneurs livrés — mais le coût d'insister est le même.

## Un bug sur un conteneur ne coûte plus sa tournée à tous les autres

`_poll_one` n'attrapait que `ProviderNotConfigured` et `ProviderUnavailable`. Un `KeyError` dans un
parseur devant une charge utile inattendue remontait donc jusqu'en haut : le `db.commit()` de fin
de boucle n'avait jamais lieu, et **toutes les organisations suivantes n'étaient pas traitées du
tout**. Chaque conteneur est maintenant dans son propre `try`, avec `rollback` et on continue.

Même chose pour `retry_failed_deliveries` : `provider_factory(...)` était appelé hors de toute
protection, donc une clé retirée de l'environnement ou un nom de fournisseur disparu du registre
bloquait la reprise des livraisons **des autres** fournisseurs. Le corps reste en table, on y
reviendra ; ce qu'il ne doit pas faire, c'est arrêter la file.

## Ce qui reste ouvert

- Le disjoncteur est **par balayage**, pas persistant. Une panne de plusieurs jours refait trois
  appels par tour. C'est peu, et ça garde la reprise automatique ; si ça devient gênant, la forme
  à copier est celle de l'ERP (`retry_after` en base, `odoo-questions.md` §17).
- Rien ne mesure la *durée* d'une panne côté fournisseur : l'alerte est quotidienne, pas
  « injoignable depuis 6 heures ».
