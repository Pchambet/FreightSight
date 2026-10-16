# Réponses au questionnaire sécurité — brouillon

30 réponses courtes et littérales aux questions qu'un DPO ou un responsable informatique de PME envoie
avant de signer avec un fournisseur SaaS B2B. Sert de brouillon de réponse au questionnaire annoncé sur
`/securite` (« Envoyez votre questionnaire DPO ou DSI : réponse point par point sous cinq jours
ouvrés », `securite/page.tsx:90`) et de check-list interne avant de répondre à un vrai questionnaire.

Chaque réponse est marquée **VRAI AUJOURD'HUI** (vérifié dans le code ou la configuration en
production au 17/09/2026) ou **PRÉVU** (construit mais pas encore activé, ou pas encore fait), avec la
preuve. Rien n'est marqué VRAI AUJOURD'HUI sans une source vérifiable dans le dépôt. Questions 3, 13,
16, 19, 20, 22, 23 et 24 mises à jour le 16 octobre 2026 ; les sources des prestataires sont dans
`docs/legal/README.md`.

---

## Hébergement

**1. Où sont hébergées les données ?**
API et base de données PostgreSQL à Amsterdam, Pays-Bas (Railway, région
`europe-west4-drams3a`). Interface rendue depuis la région de Paris (Vercel, fonctions serveur `cdg1`).
**VRAI AUJOURD'HUI** — `docs/04_ops_railway_vercel.md` §4, `securite/page.tsx:46`.

**2. Les données quittent-elles l'Union européenne pour l'hébergement principal ?**
Non pour Railway (Pays-Bas) et Scaleway (France). Le rendu de l'interface passe par un CDN mondial pour
les seuls fichiers statiques (pas de données métier). **VRAI AUJOURD'HUI** —
`docs/04_ops_railway_vercel.md` §4, `securite/page.tsx:23`.

**3. Quel hébergeur, quelle certification ?**
Railway (API, base) : attestation SOC 2 Type II, rapport sur son Trust Center
(https://docs.railway.com/enterprise/compliance) ; pas d'ISO 27001 annoncé. Vercel (interface) :
SOC 2 Type 2 et ISO 27001 (https://vercel.com/security). **VRAI AUJOURD'HUI** d'après les pages des
hébergeurs, lues le 16/10/2026 ; demander les rapports eux-mêmes avant de les citer à un DPO.

**4. Les connexions sont-elles chiffrées ?**
Oui, TLS de bout en bout entre le navigateur, l'interface et l'API. **VRAI AUJOURD'HUI** —
`securite/page.tsx:46`.

**5. Le stockage est-il chiffré au repos ?**
Oui, chiffrement au repos assuré par l'hébergeur pour la base de données de production, plus un
chiffrement applicatif indépendant (AES-256-GCM) pour les sauvegardes. **VRAI AUJOURD'HUI** —
`securite/page.tsx:46`, `securite/page.tsx:87`, `docs/backups-questions.md` §1.

## Isolation multi-clients

**6. Comment les données d'un client sont-elles isolées de celles des autres ?**
Double barrière : l'application filtre chaque requête par l'identifiant de l'organisation, et
PostgreSQL l'impose une seconde fois par des règles de sécurité au niveau des lignes (Row Level
Security). L'utilisateur technique de l'application n'a pas le droit de contourner cette règle.
**VRAI AUJOURD'HUI** — `securite/page.tsx:49`, `docs/04_ops_railway_vercel.md` §1 (procédure de
vérification du rôle limité).

**7. Cette isolation est-elle testée ?**
Oui, un test automatisé vérifie à chaque déploiement qu'une requête sans filtre explicite ne renvoie
aucune ligne d'une autre organisation. **VRAI AUJOURD'HUI** — `securite/page.tsx:49`.

**8. La base de données est-elle partagée entre clients (mono-instance) ou dédiée par client ?**
Base partagée avec isolation logique par Row Level Security (voir question 6), pas une base dédiée par
client. **VRAI AUJOURD'HUI** — architecture actuelle, cf. question 6.

## Sauvegardes et continuité

**9. À quelle fréquence les données sont-elles sauvegardées ?**
Chaque nuit, sauvegarde complète chiffrée déposée hors de l'hébergeur principal, chez Scaleway à Paris.
**VRAI AUJOURD'HUI** — `securite/page.tsx:87`, `docs/04_ops_railway_vercel.md` §6.

**10. Combien de temps les sauvegardes sont-elles conservées ?**
30 sauvegardes quotidiennes glissantes, plus la première sauvegarde de chacun des 12 derniers mois.
**VRAI AUJOURD'HUI** — `securite/page.tsx:87`, `docs/backups-questions.md` §4.

**11. Les sauvegardes sont-elles chiffrées, et la clé est-elle séparée de l'hébergeur des
sauvegardes ?**
Oui, AES-256-GCM, clé détenue par FreightSight et non par Scaleway. **VRAI AUJOURD'HUI** —
`securite/page.tsx:87`. [À VÉRIFIER avant de répondre à un vrai questionnaire : que la clé
(`BACKUP_ENCRYPTION_KEY`) est bien copiée hors de Railway dans un gestionnaire de mots de passe —
`docs/backups-questions.md` §2 signale que ça reste une action humaine à faire, pas encore confirmée
faite dans ce dépôt].

**12. Une restauration a-t-elle déjà été testée avec succès ?**
[À VÉRIFIER avant tout envoi : aucune restauration n'a encore été prouvée sur la production elle-même.]
L'intégration continue rejoue l'aller-retour complet (dump, chiffrement, déchiffrement, restauration
dans une base neuve, relecture des données sous le rôle applicatif soumis à la RLS) sur PostgreSQL 18,
la majeure de la production, à chaque changement du back-end et chaque semaine ; un échec y fait
échouer la CI au lieu d'être sauté. Depuis le 16/10/2026, une copie restaurée redonne ses droits au
rôle applicatif (diagnostic D2-F1). **PRÉVU pour la production** — restaurer la dernière sauvegarde de
production dans une base séparée au redémarrage (`docs/04_ops_railway_vercel.md` §6 et §7).
`docs/backups-questions.md` §3, confirmé par `docs/plan/audit-2026-09-17/F1-verifications-prod.md` §3
(« reste vrai : aucune restauration n'a été prouvée sur la prod »).

**13. Quel est l'objectif de temps de reprise (RTO) et de perte de données maximale tolérée (RPO) ?**
Perte maximale (RPO) : la sauvegarde hors hébergeur est quotidienne (cron `0 3 * * *`,
`.railway/railway.ts`) ; si la base Railway et ses propres copies étaient perdues, on perdrait au plus
ce qui a été saisi depuis la dernière sauvegarde de 3 h (UTC), soit 24 h au pire. **VRAI AUJOURD'HUI**
pour la fréquence. Délai de reprise (RTO) : [DÉCISION de Pierre : aucun chiffre tant qu'une
restauration complète n'a pas été chronométrée].

## Accès et authentification

**14. Comment les utilisateurs s'authentifient-ils ?**
Par e-mail ou Google, via Clerk ; double authentification disponible ; organisations avec invitations
et rôles. **VRAI AUJOURD'HUI** — `securite/page.tsx:52`.

**15. Le compte technique de l'API peut-il accéder à toutes les données sans restriction ?**
Non : le rôle de connexion de l'API n'est ni superutilisateur ni `BYPASSRLS`, vérifié explicitement à
la mise en place. **VRAI AUJOURD'HUI** — `docs/04_ops_railway_vercel.md` §1, requête de vérification
`SELECT rolname, rolsuper, rolbypassrls, rolinherit`.

**16. Qui, chez FreightSight, a accès aux données de production ?**
Le fondateur seul. [À CONFIRMER par Pierre au moment de répondre ; formaliser une liste nominative et
une procédure d'habilitation avant que l'équipe grandisse.]

**17. Existe-t-il un contrôle d'accès par rôle côté client (utilisateur standard vs administrateur) ?**
Oui, quatre rôles vérifiés par l'API à chaque requête : *VIEWER* lit ; *MEMBER* lit et écrit (coûts,
factures, conteneurs, partages) ; *ADMIN* fait en plus les actes comptables — clôturer un mois, le
rouvrir, marquer un écart comme comptabilisé ; *OWNER* a les mêmes droits qu'ADMIN. Les rôles viennent
de l'organisation Clerk (`org:admin` → ADMIN, `org:member` → MEMBER). Un refus répond 403
`FORBIDDEN_ROLE`. **VRAI AUJOURD'HUI** — `backend/app/core/auth.py`, `backend/app/api/v1/deps.py`,
`backend/tests/test_periods.py` (test des rôles).

**17 bis. Des données peuvent-elles être consultées sans compte ?**
Une seule chose, et seulement si un utilisateur le décide : un **rapport partagé par lien** — le coût de
revient d'un conteneur ou d'une commande, ou l'**audit d'une période** (synthèse, marges par référence,
constats sur les factures, surestaries, coefficients d'approche, complétude des chiffres). Ce que ce lien
est, exactement :
- un **instantané figé** du rapport, pris au moment du partage — il ne permet pas de suivre l'évolution
  des chiffres d'une société, et n'ouvre rien d'autre que ce qu'il contient. Un lien d'audit contient
  les chiffres de toute la période choisie : valeurs d'achat, prix de vente et marges par référence,
  conteneurs, factures en cause ; l'écran de partage le dit avant l'envoi ;
- un jeton aléatoire de 256 bits, **dont seule l'empreinte SHA-256 est conservée** : une copie de la
  base ne permet pas de reconstituer un lien ; le jeton voyage dans le corps de la requête vers l'API,
  jamais dans une URL d'API, et n'est écrit dans aucun journal applicatif ni rapport d'erreur ;
- une durée de vie choisie (30 jours par défaut, 365 au plus) et une **révocation immédiate** ; inconnu,
  expiré ou révoqué reçoivent la même réponse ;
- en base, l'accès par jeton est un droit de **lecture d'une ligne** (politique RLS dédiée) ; il ne
  permet ni de modifier, ni de prolonger, ni de supprimer quoi que ce soit ; chaque ouverture est
  comptée et visible de l'émetteur ;
- les notes internes ne quittent jamais la société ; l'émetteur peut en plus **exclure de l'instantané**
  les noms des prestataires et les numéros de facture — et, pour un audit, les noms des fournisseurs
  (ils ne sont alors pas stockés dans le lien ; pour un audit, seule une liste fermée de valeurs qui ne
  nomment personne est conservée dans le détail des constats). Les prix, marges, références et numéros
  de conteneur restent : ce sont les chiffres du document ;
- la page est servie `noindex`, `no-store`, `Referrer-Policy: no-referrer`, et l'ouverture est limitée
  en débit.
Limite connue, commune à tout produit à lien de partage : l'adresse de la page (`/r/<jeton>`) figure
dans les journaux d'accès de l'hébergeur du site (Vercel) ; la réponse est l'expiration et la
révocation. **VRAI AUJOURD'HUI** — `backend/migrations/versions/0025_shared_reports.py`,
`backend/app/domain/shares/service.py`, `backend/app/api/v1/shares.py`, `backend/tests/test_shares.py`
(dont deux tests exécutés sous le rôle applicatif restreint), `backend/tests/test_audit.py` (instantané
masqué vérifié dans la base), relectures de sécurité indépendantes du 18 septembre 2026 (partage de
rapport, puis partage d'audit).

## Journalisation et supervision

**18. Les erreurs applicatives sont-elles supervisées ?**
Oui, via Sentry, sans le contenu d'une facture ni d'une commande dans les traces. **VRAI AUJOURD'HUI**
— `securite/page.tsx:26`.

**19. Existe-t-il un journal d'audit (qui a fait quoi, quand) au-delà des traces d'erreur ?**
Oui pour les modifications : un journal d'audit horodaté enregistre qui a créé, validé, modifié ou
annulé quoi (coûts, factures, imports, clôtures de période, partages, envois vers l'ERP), avec l'état
avant et après. Il est en ajout seul : le rôle applicatif n'a que `SELECT` et `INSERT`, et un
déclencheur refuse `UPDATE` et `DELETE` à tous, propriétaire compris. Les simples consultations ne sont
pas journalisées. **VRAI AUJOURD'HUI** — `backend/migrations/versions/0008_audit_log.py`,
`backend/app/domain/audit/service.py`, `backend/tests/test_audit_log.py`.

## Incidents

**20. Sous quel délai une violation de données affectant le client serait-elle notifiée ?**
48 heures après en avoir pris connaissance, dans le DPA proposé (`docs/legal/dpa-article-28.md`
article g). **PRÉVU** : engagement contractuel à la signature du DPA [DÉCISION de Pierre sur le délai].

**21. Existe-t-il un plan de réponse à incident écrit ?**
[À COMPLÉTER : non trouvé dans ce dépôt sous cette forme — le runbook de restauration
(`docs/04_ops_railway_vercel.md` §6 « Restaurer, en cinq commandes ») en couvre une partie technique,
mais un plan de réponse à incident (qui prévenir, dans quel ordre, avec quel modèle de communication)
reste à écrire].

## Sous-traitants

**22. Quels sous-traitants reçoivent des données, et où sont-ils situés ?**
Railway (Amsterdam ; société américaine, clauses contractuelles types), Vercel (Paris pour les
fonctions, CDN mondial ; DPF et clauses contractuelles types), Clerk (États-Unis ; DPF, clauses
contractuelles types en secours), Scaleway (Paris), Sentry (Francfort, métadonnées de compte aux
États-Unis ; DPF, clauses en secours), Frankfurter (aucune donnée transmise). **VRAI AUJOURD'HUI** —
liste publiée sur `/securite` et `/confidentialite`, tirée de
`frontend/src/features/marketing/subprocessors.ts`.

**23. Cette liste est-elle tenue à jour et communiquée avant tout changement ?**
Les sous-traitants à venir (Resend, Shipsgo ou Terminal49) sont déjà listés par avance sur `/securite` et
dans la politique de confidentialité, alors qu'ils ne sont pas encore activés en production — pour ne
jamais être découverts après coup. **VRAI AUJOURD'HUI** comme pratique ; **PRÉVU** comme sous-traitants
eux-mêmes tant qu'ils ne sont pas activés — `securite/page.tsx:33`,
`docs/plan/audit-2026-09-17/F1-verifications-prod.md` §1.

**24. Un fournisseur d'intelligence artificielle traite-t-il les données du client ?**
Non. La lecture des factures se fait par des règles déterministes. Un lecteur assisté par IA existe
dans le code (il enverrait le texte des factures à Anthropic, aux États-Unis) ; il ne s'active qu'avec
une clé d'API, absente de la production, et s'appliquerait alors à tous les clients à la fois. `/securite`
le dit, et Anthropic y sera listé avec son mécanisme de transfert avant toute activation. **VRAI
AUJOURD'HUI** au 17/09/2026 (variables de production lues), [À VÉRIFIER dans Railway avant d'envoyer :
la production n'a pas été relue depuis] — `backend/app/domain/invoices/registry.py`.

## Réversibilité, export, suppression

**25. Le client peut-il exporter l'intégralité de ses données à tout moment ?**
Oui, à tout moment et pas seulement en fin de contrat — en partie en libre-service, le reste sur
demande. Depuis l'application, sans intervention de FreightSight : commandes et leurs lignes,
conteneurs, coûts (estimés et facturés), coût de revient par ligne, clôtures mensuelles (écarts,
factures non parvenues), coût par référence et constats d'audit, en CSV français ou anglais. Le reste
— factures PDF déposées, fiches produits, barèmes, événements de suivi, journal d'audit — est exporté
sur demande, par des requêtes limitées à l'organisation ; cette procédure n'est pas encore outillée.
**VRAI AUJOURD'HUI** pour les exports en libre-service — `backend/app/api/v1/exports.py`,
`securite/page.tsx:84` ; **PRÉVU** : l'export complet en un seul fichier, en libre-service.

**26. Que se passe-t-il si le client résilie ?**
Suppression définitive de l'organisation exécutée sous 30 jours et confirmée par écrit ; les
sauvegardes chiffrées résiduelles suivent leur propre cycle de rétention (30 jours glissants,
12 mensuelles) avant expiration complète. **VRAI AUJOURD'HUI** — `securite/page.tsx:84`,
`docs/backups-questions.md` §4.

**27. Les fichiers de factures sont-ils sauvegardés séparément des autres données ?**
Aujourd'hui les documents sont en base, donc inclus dans la sauvegarde de la base. Si les fichiers
passent un jour sur un stockage objet séparé (S3/Scaleway), rien ne les sauvegarde automatiquement à ce
jour — point ouvert, pas encore un risque puisque ce stockage séparé n'existe pas.
**VRAI AUJOURD'HUI** pour l'architecture actuelle (tout en base) — `docs/backups-questions.md` §6.

## Continuité de l'activité (fondateur solo)

**28. FreightSight est aujourd'hui piloté par une seule personne. Que se passe-t-il en cas
d'indisponibilité prolongée du fondateur ?**
Trois mesures documentées atténuent ce risque : (a) l'essentiel des données s'exporte depuis
l'application sans aucune action du fondateur, le reste sur demande (question 25) ; (b) les sauvegardes
chiffrées sont hors du fournisseur d'hébergement principal, avec une clé qui doit être conservée en
dehors de Railway (question 11) ; (c) un runbook de restauration écrit, reproductible par un tiers
technique, existe déjà (`docs/04_ops_railway_vercel.md` §6, « Restaurer, en cinq commandes »).
**PRÉVU comme garantie complète** — les trois mesures existent, mais aucune procédure formelle de
passation (qui contacter, comment, avec quels accès) n'est écrite à ce jour ; à formaliser avant de
répondre « oui » sans réserve sur ce point à un DPO.

**29. Existe-t-il une assurance responsabilité civile professionnelle ?**
[À COMPLÉTER : aucune mention trouvée dans ce dépôt — à souscrire avant la première signature
commerciale réelle si ce n'est pas déjà fait, et à ne jamais affirmer sans l'avoir vérifié].

**30. Quelle est la forme juridique de FreightSight, et depuis quand l'entreprise existe-t-elle ?**
[À COMPLÉTER : aucune entité juridique déclarée trouvée dans ce dépôt à ce jour — voir
`docs/legal/mentions-legales.md` §1. Ne pas répondre à cette question dans un vrai questionnaire tant
que ce point n'est pas réglé : c'est précisément le type d'écart qu'un DPO de PME sérieuse relève en
premier, d'après `docs/plan/audit-2026-09-17/A4-site-commercial-prod.md` finding A4-6].

---

**Avant d'envoyer une vraie réponse à un questionnaire**, relire chaque ligne marquée `[À COMPLÉTER]`
ou `[À VÉRIFIER]` ci-dessus : ce brouillon ne doit jamais être transmis tel quel à un prospect.
