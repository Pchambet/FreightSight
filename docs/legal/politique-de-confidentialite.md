# Politique de confidentialité — justification de la page publiée

La page est en ligne à `/confidentialite` depuis le 16 octobre 2026 ; son texte est celui de
`frontend/src/app/(marketing)/confidentialite/page.tsx`. Elle répond à l'article 13 du RGPD. Ce
document donne la source de chaque affirmation ; une page et ce document changent ensemble.

**Brouillon rédigé par un outil d'IA, non relu par un avocat.** La page ne contient aucun champ à
compléter : tout ce qu'elle dit est vérifié, et ce qui ne l'est pas a été retiré ou formulé comme un
critère.

## Responsable du traitement

- Aujourd'hui : « Pierre Chambet, fondateur et éditeur de FreightSight », contact
  `pierrechambet@gmail.com` (`site.contactEmail`, déjà affiché sur tout le site).
- Dès que `site.registered` est vrai (nom, forme, SIREN, adresse remplis dans `site.ts`), la page nomme
  l'entité immatriculée à la place. Aucun délégué à la protection des données n'est désigné : non
  obligatoire ici (art. 37 RGPD : ni autorité publique, ni suivi à grande échelle, ni données
  sensibles).

## Deux rôles

Responsable de traitement pour le site, les contacts et les comptes ; **sous-traitant** pour les données
métier des clients (commandes, factures, conteneurs…), régies par le DPA (`dpa-article-28.md`). Une
personne nommée dans les documents d'un client s'adresse au client.

## Traitements, bases légales, durées

| Situation | Données (source) | Base | Durée affichée (source) |
|---|---|---|---|
| E-mail ou rendez-vous | E-mail, nom, message, pièces jointes de l'essai « une facture, un coût rendu sous 24 h » (`site.quickCheckUrl`) ; créneau Cal.com (`NEXT_PUBLIC_BOOKING_URL`, `https://cal.com/pierre-chambet/20min` lu sur la production le 16/10/2026) | Intérêt légitime (6.1.f) | 3 ans après le dernier message du prospect (référentiel CNIL « gestion commerciale », voir README, non vérifié en source primaire) |
| Visite du site | Journaux de Vercel (IP, page, navigateur) ; erreurs navigateur et serveur vers Sentry, `sendDefaultPii: false`, pas de replay (`frontend/src/instrumentation-client.ts`, `frontend/sentry.server.config.ts`) | Intérêt légitime (6.1.f) | Journaux : durée de Vercel (critère, pas de chiffre : non vérifiée pour l'offre souscrite). Erreurs : 90 jours au plus (offres Developer 30 j, Team/Business 90 j) |
| Application | `users` : e-mail, nom, identifiant Clerk ; `memberships` : société et rôle ; `audit_log` : qui a fait quoi et quand (`backend/app/domain/models.py`) ; destinataires des alertes à l'activation de Resend | Intérêt légitime (6.1.f) : le contrat est conclu avec la société, pas avec l'utilisateur | Durée d'utilisation par la société, puis 30 jours (engagement déjà publié sur `/securite`) ; sauvegardes : 30 jours (quotidiennes) et 12 mois (mensuelles), `backend/app/ops/backup.py` `DAILY_KEPT = 30`, `MONTHLY_KEPT = 12` |

Pourquoi l'intérêt légitime et pas le contrat pour les comptes : l'utilisateur est le salarié d'un
client, il n'est pas lui-même partie au contrat. Le choix est prudent et courant en B2B ; il ouvre un
droit d'opposition, que la page mentionne.

Pas de décision automatisée ni de profilage : aucun code ne note ni ne classe des personnes.

## Destinataires et transferts

Une seule liste, `frontend/src/features/marketing/subprocessors.ts`, partagée avec `/securite`. Chaque
mécanisme de transfert est celui que le prestataire affiche (sources dans `README.md`) :

| Prestataire | Où | Mécanisme affiché |
|---|---|---|
| Railway | Amsterdam (société américaine) | Clauses contractuelles types (DPA §9.2) ; DPF seulement si le destinataire est certifié, non vérifié |
| Vercel | Paris / CDN mondial (société américaine) | DPF (certifiée) et clauses contractuelles types |
| Clerk | États-Unis | DPF (auto-certifiée), clauses contractuelles types en secours |
| Scaleway | Paris | Aucun transfert |
| Sentry | Francfort, métadonnées de compte aux États-Unis | DPF, clauses contractuelles types en secours |
| Frankfurter | — | Aucune donnée envoyée |
| Google (Gmail) | Centres de données de Google | DPF et clauses contractuelles types selon Google ; Gmail est un service grand public, sans DPA : la page le dit |
| Cal.com | États-Unis | Clauses contractuelles types (DPA §12) ; listé seulement si le lien de rendez-vous est Cal.com |
| Resend (pas actif) | États-Unis | Clauses contractuelles types (§6.2) et DPF (§11.1) |
| Shipsgo / Terminal49 (pas actifs) | Turquie / États-Unis | Sans objet : seuls des numéros de conteneur, de connaissement ou de réservation, le code transporteur et un identifiant interne partent (`backend/app/adapters/tracking/*.py`) |
| Anthropic (pas actif) | États-Unis | Le paragraphe IA dit qu'il est désactivé et sera listé avec son mécanisme avant activation |

Le DPF repose sur la décision d'adéquation du 10 juillet 2023 ; un recours (C-703/25 P) est pendant
devant la CJUE (diagnostic D7-F4). C'est pourquoi la page cite toujours les clauses contractuelles types
à côté du DPF.

## Cookies

Aucun cookie de mesure d'audience, de publicité ni de réseau social (aucun outil d'analytics dans
`frontend/src`, aucun `Set-Cookie` sur `/` en production — diagnostic D7-F6). Restent les cookies de
Clerk nécessaires à la connexion et le cookie `NEXT_LOCALE` (un an, posé seulement quand l'utilisateur
change de langue dans l'application, `frontend/src/i18n/actions.ts`). Les deux sont strictement
nécessaires, donc sans consentement (https://entreprendre.service-public.gouv.fr/vosdroits/F31228). À
revoir si un outil d'analytics, un widget Cal.com intégré ou un replay de session est ajouté.

## Droits

Accès, rectification, effacement, limitation, portabilité, opposition (art. 15 à 22) ; réponse sous un
mois, prolongeable de deux mois (art. 12.3) ; réclamation à la CNIL (https://www.cnil.fr/fr/plaintes).

## Ce qui reste

- [À VÉRIFIER par Pierre] les points de la section « Non vérifié » du `README.md` qui touchent cette
  page : clé `EXTRACTION_API_KEY` absente en production, DSN Sentry en région UE, offre Sentry, durée
  des journaux Vercel, noms des cookies Clerk.
- [À TENIR par Pierre] la purge des échanges prospects à 3 ans, et la suppression sous 30 jours
  (outillage absent, `README.md` section 4).
- Si la page devait exister en anglais : le site public n'a pas de version anglaise aujourd'hui, la page
  n'en a donc pas non plus.
