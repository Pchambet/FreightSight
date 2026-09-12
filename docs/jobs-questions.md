# File d'attente et alertes — questions ouvertes

Comme pour le tracking : ce qui n'est pas tranché, et ce que le code fait en attendant.

## 1. Le schéma Procrastinate dans une migration Alembic

Procrastinate livre son schéma en SQL et un outil (`procrastinate schema --apply`) qui l'applique
hors Alembic. Ici, `alembic upgrade head` doit suffire à obtenir une base complète, donc la migration
0005 applique ce SQL — mais en le **lisant dans le paquet installé**, pas en le recopiant dans le
dépôt : mille lignes copiées à la main dérivent au premier changement de version sans que personne ne
le voie.

Le garde-fou est une vérification de version dans la migration : Procrastinate est épinglé
(`>=3.9,<3.10`) et 0005 refuse de tourner contre une autre version mineure, en disant quoi faire —
une nouvelle révision qui applique les fichiers de `procrastinate/sql/migrations/`. → Si tu préfères
le SQL figé dans le dépôt (reproductibilité absolue, au prix de la dérive), c'est un changement d'une
ligne dans 0005.

## 2. Enqueue transactionnel : le point délicat

`defer()` écrit le job par la connexion psycopg **de la session SQLAlchemy** : rollback de la
transaction = pas de job. Conséquence non évidente : un conflit de `queueing_lock` est une violation
d'unicité, et une violation d'unicité empoisonne toute la transaction. Le savepoint qui protège
l'appelant est posé **en SQL** (`SAVEPOINT` / `ROLLBACK TO SAVEPOINT`) et non via
`Session.begin_nested()` : l'instruction qui échoue passe par la connexion brute, hors de la vue de
l'ORM, qui croit alors son savepoint intact et ne le rembobine jamais. Mesuré, pas supposé.

## 3. Fuseau du recalcul quotidien

Le plan dit « 06:00 UTC », la demande dit « 06:00 Europe/Paris ». C'est Europe/Paris qui est
implémenté (les utilisateurs sont français, et un LFD se lit le matin, heure locale) : la tâche
périodique tourne toutes les heures et ne fait le travail que si l'heure de Paris est 6. Procrastinate
ne connaît que l'UTC dans ses crons ; c'est le moyen le plus simple de ne pas se tromper deux fois
par an. → À revoir le jour où il y a des clients hors zone Europe/Paris.

## 4. Destinataires des e-mails

Tous les membres de l'organisation reçoivent tout, il n'y a pas de préférence de notification par
utilisateur ni par type d'alerte. C'est ce qu'on peut faire honnêtement avec le miroir Clerk
actuel (users + memberships, sans réglage). → Dès qu'un partenaire aura trois personnes dont une
seule veut les alertes, il faudra une table de préférences.

## 5. Groupage des e-mails

Un job toutes les 5 minutes ramasse les alertes non notifiées et envoie **un** e-mail par
organisation. Une alerte créée juste après l'envoi attend le tour suivant : au pire 5 minutes de
retard, jamais un e-mail par alerte. Sans clé Resend, le notifieur écrit dans les logs et marque
quand même les alertes comme notifiées — sinon la première vraie clé déclencherait un envoi de tout
l'historique.

## 6. Variables et service worker

Le worker est `python -m app.worker`, même image que l'API. Variables : `DATABASE_URL` (obligatoire,
la même que l'API), `APP_ENV`, et facultativement `WORKER_CONCURRENCY` (défaut 2) et `WORKER_QUEUES`
(défaut : toutes). Pour les alertes par e-mail : `RESEND_API_KEY` et `ALERTS_FROM_EMAIL` — sans les
deux, les digests partent dans les logs. Pour le tracking, le worker a besoin des mêmes clés que
l'API (`TRACKING_WEBHOOK_SECRET_TERMINAL49`, `TERMINAL49_API_KEY`) pour pouvoir rejouer une livraison
ou interroger un abonnement muet.

## 7. Ce qui n'est pas fait

- `process_import` n'est pas encore un job (l'import reste synchrone, il est rapide).
- `extract_invoice` est un job Procrastinate ; en local il tourne via le service `worker` de
  `docker compose` (ou `python -m app.worker` hors Docker).
- Pas de `purge_soft_deleted` hebdomadaire.
- Pas d'écran d'administration de la file : `procrastinate_jobs` se lit en SQL.
