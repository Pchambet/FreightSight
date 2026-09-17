# Politique de confidentialité — brouillon

Document de travail pour la page `/politique-de-confidentialite`. Rédigé pour couvrir l'article 13 du
RGPD (information des personnes concernées) et, pour la partie applicative, pour être cohérent avec la
page `/securite` (`frontend/src/app/(marketing)/securite/page.tsx`) dont elle reprend et détaille les
engagements déjà publiés.

**Brouillon rédigé par un outil d'IA, à faire relire par un avocat avant publication.** Chaque
`[À COMPLÉTER : …]` est une information que l'outil ne peut pas connaître. Chaque `[À VÉRIFIER : …]`
est un point de droit ou de fait à confirmer avant que ce document ne devienne opposable.

---

## 0. Deux traitements bien séparés

Ce document couvre deux situations différentes, à ne jamais mélanger dans les réponses à une personne
qui exerce ses droits :

1. **Le site public** (visite, prise de rendez-vous, envoi d'un e-mail de contact) : FreightSight est
   **responsable de traitement**.
2. **L'application** (compte utilisateur, organisation, données métier saisies par le client —
   commandes, conteneurs, factures, coûts) : pour les données de compte (identité de l'utilisateur,
   appartenance à une organisation), FreightSight est **responsable de traitement**. Pour les
   **données métier** que le client importe ou saisit dans l'application (ses commandes, ses
   factures, ses fournisseurs, ses conteneurs), **le client est responsable de traitement et
   FreightSight est sous-traitant** au sens de l'article 28 du RGPD — voir
   `docs/legal/dpa-article-28.md`. Cette distinction est déjà annoncée sur `/securite` (« Vous pouvez
   demander à tout moment un export complet ») et doit être répétée ici sans ambiguïté : ce n'est pas
   FreightSight qui décide de la finalité des données métier de ses clients, c'est le client.

## 1. Qui est responsable de traitement

[À COMPLÉTER : identité complète du responsable de traitement — reprendre l'éditeur des mentions
légales une fois la forme juridique choisie, `docs/legal/mentions-legales.md` §1]

Contact pour toute question relative aux données personnelles : [À COMPLÉTER : adresse dédiée,
aujourd'hui `pierrechambet@gmail.com`, `frontend/src/lib/site.ts:4`]. [À COMPLÉTER : si un délégué à
la protection des données (DPO) est désigné un jour — non obligatoire pour une structure de cette
taille sauf traitement à grande échelle de données sensibles, ce qui n'est pas le cas ici, cf. art. 37
RGPD].

## 2. Données traitées, finalités et bases légales

### 2.1 Site public (visiteur, avant tout compte)

| Donnée | Finalité | Base légale | Source |
|---|---|---|---|
| Adresse e-mail, contenu du message | Répondre à une demande de contact ou de rendez-vous | Intérêt légitime à répondre à une sollicitation commerciale entrante (art. 6.1.f) | Formulaire `mailto:` vers `pierrechambet@gmail.com` — pas de formulaire back-end aujourd'hui, cf. `frontend/src/lib/site.ts` |
| Date, heure, créneau choisi | Organiser un appel de 20 minutes | Exécution de mesures précontractuelles à la demande du prospect (art. 6.1.b) | Cal.com ou équivalent, une fois `NEXT_PUBLIC_BOOKING_URL` configuré (voir §5 sous-traitants) |
| Facture transitaire envoyée pour le test gratuit à 24h | Calculer et renvoyer un coût de revient à titre d'exemple | Exécution de mesures précontractuelles à la demande du prospect (art. 6.1.b) | Pièce jointe au `mailto:` « une facture, un coût rendu sous 24h » |

Aucun cookie de mesure d'audience ni traceur tiers n'est déposé sur le site public : vérifié dans le
code (`frontend/src/app`, aucune trace de Plausible/Umami/PostHog/GA — cohérent avec le constat A4-8
de l'audit du 17/09/2026, qui note l'absence totale d'analytics). Voir §7 « Cookies ».

### 2.2 Application (compte et organisation)

| Donnée | Finalité | Base légale | Sous-traitant impliqué |
|---|---|---|---|
| E-mail, nom, appartenance à une organisation, méthode de connexion | Authentifier l'utilisateur, gérer les invitations et les rôles | Exécution du contrat (art. 6.1.b) | Clerk |
| Identifiant technique de session, adresse IP de connexion | Sécuriser l'accès, détecter un usage anormal | Intérêt légitime à la sécurité du service (art. 6.1.f) | Clerk, Railway (journaux techniques) |
| Traces d'erreur applicative (message d'erreur, identifiant de requête) | Diagnostiquer un incident | Intérêt légitime à la fiabilité du service (art. 6.1.f) | Sentry — « jamais le contenu d'une facture ni d'une commande », `securite/page.tsx:26` |

### 2.3 Données métier du client (FreightSight agit comme sous-traitant)

Commandes, conteneurs, factures, fournisseurs, coûts et tout ce que le client importe ou saisit dans
l'application. FreightSight traite ces données **exclusivement sur instruction du client**, pour
exécuter le service (calcul du coût de revient, suivi des conteneurs, alertes). FreightSight ne
détermine ni les catégories de personnes concernées éventuellement présentes dans ces données (par
exemple un nom de contact fournisseur sur une facture), ni leur finalité : c'est au client, en tant que
responsable de traitement de ses propres données métier, d'informer ses propres interlocuteurs le cas
échéant. Le détail des garanties contractuelles est dans `docs/legal/dpa-article-28.md`.

## 3. Durées de conservation

- **Prospect (site public, sans suite)** : [À VÉRIFIER : la doctrine CNIL usuelle pour la prospection
  commerciale est de 3 ans à compter du dernier contact en l'absence de réaction — cf.
  `docs/plan/gtm-2026-09-17/research/11_outbound_offre_process_de_vente.md` §1.1, qui marque ce
  chiffre lui-même UNVERIFIED faute d'accès à cnil.fr au moment de la rédaction ; à confirmer sur
  cnil.fr avant publication].
- **Compte utilisateur actif** : pendant toute la durée de la relation contractuelle.
- **Données métier d'une organisation après suppression** : « la suppression est exécutée sous 30
  jours et confirmée par écrit » (`securite/page.tsx:84`) — reprendre cet engagement ici tel quel,
  sans le durcir ni l'assouplir, pour que les deux pages restent cohérentes.
- **Sauvegardes chiffrées** : 30 sauvegardes quotidiennes glissantes et 12 mensuelles conservées chez
  Scaleway (`docs/backups-questions.md` §4, `securite/page.tsx:87`) — une donnée supprimée du service
  actif peut donc subsister chiffrée dans une sauvegarde jusqu'à l'expiration de cette rétention avant
  d'être définitivement effacée. [À COMPLÉTER : phrase à valider avec un avocat sur la façon de
  formuler ce délai résiduel dans une politique de confidentialité].
- **Journaux techniques et traces d'erreur (Sentry)** : [À COMPLÉTER : durée de rétention effective
  configurée sur le projet Sentry — non trouvée dans le dépôt, à vérifier dans le dashboard Sentry].

## 4. Destinataires et sous-traitants

Le tableau ci-dessous reprend et détaille celui de `/securite`, en ajoutant le pays de destination et
le mécanisme de transfert (le RGPD encadre tout transfert hors Union européenne, articles 44 à 49).

| Sous-traitant | Rôle | Pays | Mécanisme de transfert | Donnée reçue |
|---|---|---|---|---|
| Railway | API et base de données PostgreSQL | Pays-Bas (UE) | Aucun transfert hors UE | Toutes les données métier |
| Vercel | Rendu de l'interface (fonctions Paris) et CDN | France (fonctions) / mondial (CDN statique) | [À VÉRIFIER : Vercel Inc. est une société américaine ; les fonctions serveur tournent à Paris mais le contrat cadre de Vercel relève-t-il de clauses contractuelles types (SCC) ou du Data Privacy Framework (DPF) ? À confirmer sur la page de conformité de vercel.com avant publication] | Données affichées à l'écran, en transit |
| Clerk | Authentification, organisations, invitations | États-Unis | [À VÉRIFIER : clauses contractuelles types annoncées sur `/securite` (`securite/page.tsx:24`) — à confirmer que Clerk Inc. propose bien des SCC signées ou une adhésion au DPF sur sa page de conformité actuelle] | E-mail, nom, appartenance à une société |
| Scaleway | Sauvegardes chiffrées de la base de données | France (UE) | Aucun transfert hors UE | Copie chiffrée (AES-256-GCM) de la base entière, la clé de chiffrement n'étant pas détenue par Scaleway |
| Sentry | Supervision des erreurs | [À VÉRIFIER : `/securite` indique Francfort, Allemagne (`securite/page.tsx:26`) — Sentry (Functional Software Inc.) propose une région de traitement EU ; confirmer que l'organisation Sentry du projet est bien configurée sur la région EU et pas la région US par défaut] | UE si la région EU est confirmée, sinon SCC | Traces d'erreur, identifiants de requête |
| Frankfurter (taux BCE) | Taux de change publics | Union européenne | Sans objet — lecture seule de données publiques, aucune donnée personnelle envoyée | Aucune |

### À l'activation du suivi automatique et des alertes (pas encore en production)

Ces deux sous-traitants sont construits mais pas encore branchés en production au 17 septembre 2026
(`docs/plan/audit-2026-09-17/F1-verifications-prod.md` §1 : `RESEND_API_KEY`, `SHIPSGO_API_KEY` et les
secrets de webhook sont absents des variables Railway). Ils sont listés ici par avance, pour ne jamais
être découverts après coup par un DPO qui recoupe une alerte reçue avec cette page (c'était le
constat A4-5 de l'audit) :

| Sous-traitant | Rôle | Pays | Mécanisme de transfert | Donnée reçue |
|---|---|---|---|---|
| Resend | Envoi des alertes par e-mail (dernier jour franc, surestaries) | États-Unis | [À VÉRIFIER : clauses contractuelles types — à confirmer sur la page de conformité de resend.com avant l'activation] | Adresse e-mail du destinataire et contenu de l'alerte (référence conteneur ou commande) |
| Shipsgo | Suivi automatique des conteneurs | Turquie | [À VÉRIFIER : la Turquie n'a pas de décision d'adéquation de la Commission européenne au [À VÉRIFIER : date] — un mécanisme de transfert (SCC) doit être en place avant l'activation, à faire confirmer contractuellement avec Shipsgo] | Numéros de conteneur uniquement |

Aujourd'hui, aucun fournisseur d'IA n'est utilisé : la lecture des factures se fait par des règles
déterministes (`backend/app/adapters/extraction/regex_extractor.py`), pas par le lecteur assisté par
IA qui existe dans le code (`backend/app/adapters/extraction/llm_extractor.py`) mais n'est pas activé
en production (`EXTRACTION_API_KEY` absente des deux services Railway au 17/09/2026, confirmé par
`docs/plan/audit-2026-09-17/F1-verifications-prod.md` §2). Si une lecture assistée par IA est activée
un jour, ce sera en option, société par société sur demande, et le fournisseur sera ajouté à cette
politique et à `/securite` avant toute activation — engagement déjà pris sur `/securite`
(`securite/page.tsx:73`), répété ici pour qu'il soit contractuellement lisible.

## 5. Vos droits

Conformément aux articles 15 à 22 du RGPD, vous disposez d'un droit d'accès, de rectification,
d'effacement, de limitation, d'opposition et de portabilité de vos données. Pour l'exercer, écrivez à
[À COMPLÉTER : adresse dédiée]. Une réponse est apportée sous un mois (délai légal, prorogeable de
deux mois pour une demande complexe, art. 12.3 RGPD).

Pour les **données métier d'une organisation cliente**, la demande doit en principe être adressée au
client (responsable de traitement de ses propres données) plutôt qu'à FreightSight (sous-traitant) —
voir §0. FreightSight relaie toute demande reçue par erreur vers le client concerné dans les meilleurs
délais.

Vous pouvez également introduire une réclamation auprès de la Commission nationale de l'informatique
et des libertés (CNIL), 3 Place de Fontenoy, 75007 Paris — https://www.cnil.fr/fr/plaintes.

## 6. Sécurité

Isolation par organisation (RLS PostgreSQL), chiffrement en transit (TLS) et au repos, sauvegardes
chiffrées hors hébergeur principal — voir la page `/securite` pour le détail technique et
`docs/legal/dpa-article-28.md` annexe sécurité pour la version contractuelle.

## 7. Cookies

Le site ne dépose aucun cookie de mesure d'audience, de publicité ou de réseau social. Deux catégories
de cookies strictement nécessaires sont utilisées, dispensées de consentement préalable au titre de
l'article 82 de la loi Informatique et Libertés (cookies strictement nécessaires à la fourniture du
service demandé par l'utilisateur) :

- **Préférence de langue** (`frontend/src/i18n/locale.ts`, cookie nommé selon `LOCALE_COOKIE`) :
  mémorise le choix français/anglais du visiteur, pas de valeur identifiante au-delà de ce choix.
- **Session Clerk** (application uniquement, pas le site public) : cookies techniques nécessaires à
  l'authentification et au maintien de la session — gérés par Clerk, voir sa propre politique pour le
  détail. [À VÉRIFIER : lister les noms exacts des cookies Clerk déposés — consultable dans le
  dashboard Clerk ou la documentation Clerk sur les cookies de session, pour une transparence
  complète].

Cette section devra être revue si un outil d'analytics est un jour ajouté (l'audit A4-8 en recommande
un respectueux du RGPD, type Plausible ou Umami, auto-hébergé) : un tel outil devra soit être
strictement sans cookie et sans identifiant persistant pour rester dispensé de consentement, soit
déclencher un bandeau de consentement conforme.

## 8. Modifications

Cette politique peut être mise à jour ; la date de dernière modification figure en tête de la page
publiée. [À COMPLÉTER : mécanisme de notification aux clients existants en cas de changement matériel,
à définir avec le DPA — `docs/legal/dpa-article-28.md`].

---

**Dépendances avant publication** : ce document ne peut pas être mis en ligne tel quel — il contient
neuf `[À COMPLÉTER]`/`[À VÉRIFIER]` qui doivent être résolus, en particulier l'identité du responsable
de traitement (dépend de `docs/legal/mentions-legales.md`) et les mécanismes de transfert hors UE pour
Clerk, Vercel, Resend et Shipsgo.
