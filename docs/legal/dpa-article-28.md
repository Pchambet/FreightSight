# Accord de traitement des données (DPA) — article 28 RGPD

Trame du DPA annoncé sur `/securite` : « Un accord de traitement des données (DPA) reprenant cette
page et la liste des sous-traitants est fourni à la signature du programme design partner »
(`securite/page.tsx:84`). Ce document doit exister avant la première signature réelle — c'était le
constat A4-7 de l'audit du 17/09/2026 (« il faut qu'il existe réellement au moment T »).

**Brouillon rédigé par un outil d'IA, à faire relire par un avocat avant la première signature.** Les
clauses ci-dessous suivent l'ordre de l'article 28§3 du RGPD, qui liste ce qu'un contrat de
sous-traitance doit obligatoirement contenir. Rien dans les annexes n'a été inventé : chaque
affirmation technique est sourcée sur le code ou la documentation ops existante.

---

## Préambule

Le présent accord régit le traitement, par **[À COMPLÉTER : raison sociale de FreightSight]**
(« le Sous-traitant »), des données à caractère personnel que **[À COMPLÉTER : raison sociale du
Client]** (« le Responsable de traitement ») lui confie dans le cadre de l'utilisation du service
FreightSight, conformément à l'article 28 du RGPD. Il s'applique aux données métier saisies ou
importées par le Client dans l'application (commandes, conteneurs, factures, fournisseurs, coûts) —
voir `docs/legal/politique-de-confidentialite.md` §0 pour la répartition des rôles entre les deux
documents.

## Article 28§3 — clauses obligatoires

### a) Objet, durée, nature et finalité du traitement, catégories de données et de personnes concernées

- **Objet** : calcul du coût de revient par ligne de commande, suivi de conteneurs, extraction de
  données de factures, alertes.
- **Durée** : la durée du contrat d'abonnement ou de pilote entre les parties, plus la durée de
  conservation décrite à l'article e) ci-dessous.
- **Nature des opérations** : collecte (import), stockage, consultation, extraction automatisée,
  calcul, transmission aux fournisseurs listés en annexe 1, suppression.
- **Finalité** : exécuter le service demandé par le Responsable de traitement, rien d'autre —
  cohérent avec l'engagement « Créer un coût sans qu'un humain l'ait validé » listé comme ce que le
  service ne fait pas (`securite/page.tsx:80`, à lire en creux : le service ne décide jamais seul,
  n'utilise jamais les données à une fin étrangère au calcul demandé).
- **Catégories de données** : références de commande, numéros de conteneur, montants et lignes de
  facture, noms de fournisseurs, [À COMPLÉTER : le Client peut-il faire apparaître des données
  personnelles dans ces documents, par exemple le nom d'un contact fournisseur sur une facture ? à
  documenter au cas par cas, le service n'exige aucune donnée personnelle pour fonctionner].
- **Catégories de personnes concernées** : les utilisateurs du Client ayant un compte dans
  l'application (nom, e-mail professionnel) ; ponctuellement, des personnes physiques mentionnées dans
  les documents importés par le Client (ex. signataire d'une facture), sans que le service ne les
  traite pour elles-mêmes.

### b) Instructions documentées

Le Sous-traitant ne traite les données que sur instruction documentée du Responsable de traitement,
matérialisée par la configuration de son compte et l'usage normal du service. Le Sous-traitant informe
immédiatement le Responsable de traitement si une instruction lui semble contraire au RGPD ou à toute
autre disposition relative à la protection des données.

### c) Confidentialité du personnel

Le Sous-traitant s'assure que les personnes autorisées à traiter les données (à ce jour :
**[À COMPLÉTER : le fondateur seul, ou une équipe — à préciser selon l'effectif réel au moment de la
signature]**) sont soumises à une obligation de confidentialité, contractuelle ou légale.

### d) Sécurité (article 32)

Voir annexe 2 « Mesures de sécurité ». Reprend et détaille ce qui est publié sur `/securite`.

### e) Recours à un sous-traitant ultérieur (sous-traitance en cascade)

Le Sous-traitant ne recourt à un sous-traitant ultérieur qu'avec l'autorisation écrite, générale ou
spécifique, du Responsable de traitement. L'autorisation générale ci-dessous couvre la liste actuelle
de l'annexe 1 ; le Sous-traitant informe le Responsable de traitement de tout ajout ou remplacement
avant qu'il ne prenne effet, lui laissant la possibilité de s'y opposer — engagement déjà pris
publiquement sur `/securite` (« le fournisseur sera ajouté à cette page avant toute activation »,
`securite/page.tsx:73`, au sujet d'un éventuel fournisseur d'IA), étendu ici contractuellement à tout
sous-traitant ultérieur.

☐ Le Responsable de traitement donne son autorisation générale préalable pour l'annexe 1 telle qu'elle
existe à la signature, et pour ses mises à jour notifiées conformément à ce paragraphe.

### f) Assistance au responsable de traitement (droits des personnes)

Le Sous-traitant assiste le Responsable de traitement, dans la mesure du possible, pour répondre aux
demandes d'exercice des droits des personnes concernées portant sur les données métier — en pratique,
par l'export CSV complet et la suppression accessibles à tout moment (`securite/page.tsx:84`).

### g) Assistance (sécurité, notification de violation, analyse d'impact)

- Le Sous-traitant notifie le Responsable de traitement de toute violation de données concernant ses
  données dans les meilleurs délais après en avoir pris connaissance, et au plus tard
  **[À COMPLÉTER : délai contractuel — 48h ou 72h sont des valeurs usuelles ; l'article 33 RGPD impose
  au Responsable de traitement de notifier la CNIL sous 72h après en avoir pris connaissance lui-même,
  ce qui pousse à retenir un délai contractuel plus court côté Sous-traitant, par exemple 24h ou 48h]**
  heures, avec les éléments connus au moment de la notification (nature, catégories et nombre
  approximatif de personnes et d'enregistrements concernés, conséquences probables, mesures prises ou
  proposées).
- Le Sous-traitant fournit au Responsable de traitement les informations nécessaires à une analyse
  d'impact relative à la protection des données (AIPD) si celui-ci en réalise une — improbable au
  regard du volume et de la nature des données traitées, mais l'engagement reste disponible sur
  demande.

### h) Suppression ou restitution des données en fin de contrat

Au choix du Responsable de traitement, en fin de contrat : restitution d'un export complet (CSV) puis
suppression définitive des données, exécutée sous **30 jours** et confirmée par écrit
(`securite/page.tsx:84`) ; les sauvegardes chiffrées résiduelles expirent ensuite selon le cycle de
rétention décrit en annexe 2 (30 jours glissants, 12 mensuelles). Le Sous-traitant met à disposition du
Responsable de traitement tout élément nécessaire pour démontrer le respect de cette clause.

### i) Audit

Le Responsable de traitement peut demander au Sous-traitant les informations nécessaires pour
démontrer le respect des obligations du présent article, et faire réaliser un audit, y compris une
inspection, par lui-même ou un tiers mandaté qu'il choisit, [À COMPLÉTER avec un avocat : conditions
raisonnables — préavis, fréquence, prise en charge des coûts pour un fondateur solo qui ne peut pas
absorber un audit sur site sans limite].

---

## Annexe 1 — Sous-traitants ultérieurs

Reprend le tableau détaillé de `docs/legal/politique-de-confidentialite.md` §4, à la date de
signature :

| Sous-traitant | Rôle | Pays | Statut |
|---|---|---|---|
| Railway | API et base de données PostgreSQL | Pays-Bas (UE) | Actif |
| Vercel | Rendu de l'interface | France (fonctions) / mondial (CDN statique) | Actif |
| Clerk | Authentification | États-Unis | Actif |
| Scaleway | Sauvegardes chiffrées | France (UE) | Actif |
| Sentry | Supervision des erreurs | [À VÉRIFIER : région EU, cf. politique de confidentialité §4] | Actif |
| Frankfurter (taux BCE) | Taux de change publics, lecture seule | UE | Actif — aucune donnée transmise |
| Shipsgo | Suivi automatique des conteneurs | Turquie | Construit, pas encore activé en production au 17/09/2026 |
| Resend | Envoi des alertes e-mail | États-Unis | Construit, pas encore activé en production au 17/09/2026 |

Aucun fournisseur d'IA n'est utilisé aujourd'hui pour la lecture des factures (voir
`docs/legal/politique-de-confidentialite.md` §4 pour le détail et la source).

## Annexe 2 — Mesures de sécurité (article 32)

- **Isolation par organisation** : chaque enregistrement porte l'identifiant de l'organisation du
  Client ; l'application filtre chaque requête par cet identifiant, et PostgreSQL l'impose une seconde
  fois par des règles de sécurité au niveau des lignes (Row Level Security) — l'utilisateur technique
  de l'application n'a pas le droit de les contourner. Un test automatisé vérifie à chaque déploiement
  qu'une requête sans filtre ne renvoie aucune ligne d'une autre organisation (`securite/page.tsx:49`).
- **Chiffrement en transit** : connexions TLS de bout en bout (`securite/page.tsx:46`).
- **Chiffrement au repos** : stockage chiffré par l'hébergeur (`securite/page.tsx:46`) et sauvegardes
  chiffrées en AES-256-GCM séparément, avec une clé de chiffrement détenue par FreightSight et non par
  l'hébergeur des sauvegardes (`securite/page.tsx:87`, format de fichier documenté dans
  `docs/backups-questions.md` §1).
- **Sauvegardes hors hébergeur principal** : une copie chiffrée complète chaque nuit chez Scaleway à
  Paris, hors de Railway ; 30 sauvegardes quotidiennes et 12 mensuelles conservées
  (`securite/page.tsx:87`, `docs/04_ops_railway_vercel.md` §6). La restauration est testée en
  intégration continue à chaque changement de code (`securite/page.tsx:87`) — [À VÉRIFIER : au moment
  de la signature, confirmer que le job CI qui installe `postgresql-client-17` a bien été ajouté,
  cf. `docs/backups-questions.md` §3, pour que ce test tourne réellement et pas seulement en local].
- **Contrôle d'accès** : authentification confiée à Clerk (connexion par e-mail ou Google, double
  authentification disponible, organisations avec rôles) ; l'API ne fait confiance qu'à un jeton de
  session signé, vérifié contre les clés publiques de Clerk, restreint au domaine de l'application
  (`securite/page.tsx:52`).
- **Journalisation** : traces d'erreur envoyées à Sentry, sans le contenu d'une facture ni d'une
  commande (`securite/page.tsx:26`). [À COMPLÉTER : si un journal d'audit applicatif dédié (qui a
  consulté/modifié quoi, horodaté) existe ou est prévu au-delà des traces d'erreur — à vérifier dans
  le code applicatif avant de l'affirmer dans un DPA signé].
- **Hébergement dans l'Union européenne** : API et base de données à Amsterdam, Pays-Bas
  (`docs/04_ops_railway_vercel.md` §4) ; rendu de l'interface dans la région de Paris
  (`securite/page.tsx:46`).
- **Continuité de service côté fondateur solo** : voir
  `docs/legal/reponses-questionnaire-securite.md`, question sur le facteur bus, pour les mesures qui
  atténuent spécifiquement ce risque (export à tout moment, sauvegardes chiffrées hors fournisseur,
  runbook documenté).

---

## Signatures

| Le Sous-traitant (FreightSight) | Le Responsable de traitement (Client) |
|---|---|
| Nom : [À COMPLÉTER] | Nom : [À COMPLÉTER] |
| Fonction : [À COMPLÉTER] | Fonction : [À COMPLÉTER] |
| Date : | Date : |
| Signature : | Signature : |

---

**Avant la première signature réelle**, résoudre en priorité : le délai de notification de violation
(article g), les conditions d'audit (article i), et confirmer la région Sentry et le statut du test de
restauration en CI (annexe 2) — ce sont les trois points qu'un DPO sérieux vérifie en premier d'après
`docs/legal/reponses-questionnaire-securite.md`.
