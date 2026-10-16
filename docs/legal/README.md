# docs/legal — pages légales, contrats, et ce qui reste à Pierre

Mis à jour le 16 octobre 2026. Ce dossier tient les brouillons des contrats et la justification de chaque
phrase des pages légales du site. **Le texte publié engage Pierre** : chaque affirmation des pages est
vérifiée dans le code, la configuration ou la page officielle du prestataire (sources en fin de
document) ; ce qui n'a pas pu l'être est listé à la fin, pas affirmé.

Rien ici n'a été relu par un avocat. Une relecture est conseillée avant la première signature payante
(CGV, DPA, accord de pilote).

## Ce qui est en ligne, et ce qui attend

| Page | Source du texte | Brouillon et justification | État |
|---|---|---|---|
| `/confidentialite` | `frontend/src/app/(marketing)/confidentialite/page.tsx` | `politique-de-confidentialite.md` | Publiée, lien en pied de page, dans le sitemap |
| `/securite` | `frontend/src/app/(marketing)/securite/page.tsx` | `reponses-questionnaire-securite.md` | Publiée ; sous-traitants alignés sur le code le 16/10/2026 |
| `/mentions-legales` | `frontend/src/app/(marketing)/mentions-legales/page.tsx` | `mentions-legales.md` | **404** tant que l'identité n'est pas complète |
| `/cgv` | `frontend/src/app/(marketing)/cgv/page.tsx` | `cgv.md` | **404** tant que l'identité n'est pas complète **et** que les CGV ne sont pas datées |
| — | — | `dpa-article-28.md` | Prêt à signer après les deux décisions marquées |
| — | — | `accord-de-pilote.md` | Prêt après les décisions commerciales marquées |

Les sous-traitants affichés sur `/securite` et `/confidentialite` viennent d'une seule liste,
`frontend/src/features/marketing/subprocessors.ts` : un changement de prestataire se fait là, puis dans
l'annexe 1 du DPA.

Les pages `/mentions-legales` et `/cgv` se publient seules : dès que les champs ci-dessous sont remplis
dans `frontend/src/lib/site.ts`, la page répond 200, le lien apparaît dans le pied de page et l'URL entre
dans le sitemap. Champ vide = 404, pas de lien. Il n'y a rien d'autre à toucher.

## 1. À remplir (dans `frontend/src/lib/site.ts`)

| Champ | Ce qu'il faut y mettre | D'où ça vient |
|---|---|---|
| `publisher.legalName` | « Pierre Chambet » pour un entrepreneur individuel, la dénomination pour une société | Immatriculation (guichet unique INPI) |
| `publisher.legalForm` | Tel qu'il doit se lire : « Entrepreneur individuel (micro-entreprise) » ou « SASU au capital de 1 000 € » | Statuts / immatriculation |
| `publisher.siren` | Les 9 chiffres | Avis de situation INSEE |
| `publisher.registry` | « RCS Paris » pour une société ; vide pour un EI | Extrait Kbis |
| `publisher.vatNumber` | Numéro de TVA intracommunautaire ; **vide** en franchise en base (art. 293 B du CGI) | Service des impôts des entreprises |
| `publisher.address` | Adresse du domicile (EI) ou du siège (société), ou de la domiciliation | — |
| `publisher.phone` | Un numéro où l'on peut joindre l'éditeur (exigé par l'art. 6-III de la LCEN) | — |
| `publisher.publicationDirector` | En pratique « Pierre Chambet » | — |
| `hosts[0].phone` (Vercel) | Vercel ne publie aucun numéro sur ses pages légales : le demander au support | Support Vercel |
| `hosts[1].phone` (Railway) | Même chose pour Railway | Support Railway |
| `termsEffectiveDate` | La date d'entrée en vigueur des CGV (« 1er décembre 2026 »), **seulement après avoir lu `cgv.md` et tranché la section 2 ci-dessous** | Décision de Pierre |

Une fois l'entité immatriculée, `/confidentialite` nomme automatiquement l'entité comme responsable du
traitement (au lieu de « Pierre Chambet, fondateur »). Si l'entité est une société, c'est bien elle le
responsable : rien d'autre à changer.

Dans les brouillons de contrats, les seuls `[À COMPLÉTER]` d'identité restants sont ceux de l'éditeur
(mêmes valeurs que ci-dessus) et ceux du client.

## 2. À décider

1. **Forme juridique** (micro-entreprise ou SASU) — et, avant tout, relire son contrat de travail
   (clause d'exclusivité, non-concurrence) : diagnostic D7, points F8 et F9. Rien ne se publie ni ne se
   facture sans SIREN.
2. **CGV** (`cgv.md`) : plafond de responsabilité (proposé : 12 mois de sommes payées), délai de
   paiement (proposé : 30 jours date de facture), abonnement mensuel résiliable en fin de mois,
   suspension 15 jours après mise en demeure. Ce sont des propositions prudentes, pas des obligations.
3. **Prix HT** : la grille de la page d'accueil (299 / 499 / 999 € par mois) n'indique pas « HT ». Pour
   une vente B2B, l'écrire (diagnostic D7-F10).
4. **DPA** (`dpa-article-28.md`) : délai de notification d'une violation (proposé : 48 h) et conditions
   d'audit (proposées : préavis 30 jours, une fois par an, aux frais du client).
5. **Accord de pilote** : prix de l'audit (490 à 990 € HT), seuils de succès, prix cible après pilote.
6. **RTO** (délai de remise en service promis) : pas de chiffre aujourd'hui, à ne pas inventer.
   Un **plan de réponse à incident** (qui prévenir, dans quel ordre, avec quel message) reste aussi à
   écrire (questionnaire, question 21).
7. **Plan Vercel** : l'offre Hobby interdit l'usage commercial (D7-F7) ; passer en Pro avant de vendre.
8. **Adresse e-mail sur domaine propre** pour remplacer le Gmail, quand le domaine existe (elle change
   aussi la ligne « Google (Gmail) » de `/confidentialite`).
9. **Assurance RC Pro + cyber** avant le premier contrat payant (D7-F12), **plateforme de facturation
   électronique** pour la réception (D7-F11).

## 3. À signer ou accepter

- L'accord de traitement (DPA) de chaque prestataire, côté compte de Pierre : Vercel, Railway, Clerk,
  Sentry, Scaleway, Cal.com ; Resend et le fournisseur de suivi **avant** leur activation. La plupart
  s'acceptent avec les conditions du service ; vérifier dans chaque tableau de bord que c'est fait et
  garder une copie (PDF daté) — un DPO peut la demander.
- Le DPA client (`dpa-article-28.md`) avec chaque design partner et chaque client payant : `/securite`
  promet qu'il est fourni à la signature.
- L'accord de pilote avec chaque audit payant.

## 4. Engagements désormais publiés, à tenir

- **Supprimer une société sous 30 jours** sur demande et le confirmer par écrit (`/securite`,
  `/confidentialite`, CGV art. 6). Aucun outil ne le fait aujourd'hui. La procédure doit couvrir :
  les tables de la société, ses utilisateurs dans Clerk, et le journal d'audit — `audit_log` est en
  ajout seul, un déclencheur refuse `DELETE` même au propriétaire
  (`backend/migrations/versions/0008_audit_log.py`) : il faut une procédure documentée pour l'effacer.
- **Effacer les échanges avec un prospect 3 ans après son dernier message** (boîte Gmail comprise).
- **Avant d'activer** la lecture par IA (`EXTRACTION_API_KEY`), les alertes e-mail (`RESEND_API_KEY`)
  ou le suivi automatique : mettre à jour `subprocessors.ts` (et le paragraphe IA de `/securite` et
  `/confidentialite` pour Anthropic, avec son mécanisme de transfert), l'annexe 1 du DPA, et prévenir
  chaque client par écrit. Le code de lecture par IA s'applique à toutes les sociétés à la fois : il n'y
  a pas d'activation société par société.
- **Changer de prestataire de prise de rendez-vous** (`NEXT_PUBLIC_BOOKING_URL`) : la page
  `/confidentialite` ne liste Cal.com que si l'URL commence par `https://cal.com/` ; un autre outil
  doit y être ajouté.
- La phrase de `/securite` sur la restauration dit, depuis le 16 octobre 2026, ce que la CI rejoue : à
  chaque changement du back-end et chaque semaine, jusqu'à relire la copie sous le rôle applicatif.
  Aucune restauration n'a encore été prouvée sur la production elle-même : ne pas l'affirmer.

## Sources (lues le 16 octobre 2026)

| Fait affiché | Source |
|---|---|
| Vercel Inc., 440 N Barranca Avenue #4133, Covina, CA 91723 ; DPF et clauses contractuelles types | https://vercel.com/legal/privacy-policy (mise à jour du 1er juin 2026), https://vercel.com/legal/terms |
| Vercel certifié DPF, SOC 2 Type 2, ISO 27001 | https://vercel.com/security |
| Railway Corporation, 548 Market St PMB 68956, San Francisco, CA 94104 ; transferts sous DPF si le destinataire est certifié, sinon clauses contractuelles types (DPA §9.2) | https://railway.com/legal/dpa |
| Railway SOC 2 Type II | https://docs.railway.com/enterprise/compliance |
| Clerk : auto-certifié DPF (cl. 11.2), clauses contractuelles types modules 1-3 si le DPF ne peut plus être invoqué (cl. 11.1) | https://clerk.com/legal/dpa (mise à jour du 26 novembre 2024) |
| Sentry : DPF, clauses contractuelles types si le DPF est invalidé | https://sentry.io/legal/dpa/ |
| Sentry : région UE à Francfort ; métadonnées de compte toujours aux États-Unis | https://docs.sentry.io/organization/data-storage-location/ ; organisation FreightSight sur `de.sentry.io` (diagnostic D5, lu via l'API Sentry) |
| Sentry : conservation des erreurs 30 jours (Developer), 90 jours (Team, Business) | https://docs.sentry.io/security-legal-pii/security/data-retention-periods/ |
| Resend : clauses contractuelles types (§6.2) et DPF (§11.1) ; traitement principal aux États-Unis | https://resend.com/legal/dpa (mise à jour du 31 décembre 2025) |
| Cal.com : clauses contractuelles types modules 2/3 ; DPF seulement « si et tant que » certifié | https://cal.com/dpa |
| Google : DPF et clauses contractuelles types | https://policies.google.com/privacy/frameworks?hl=fr |
| Décision d'adéquation DPF du 10 juillet 2023 ; recours C-703/25 P pendant devant la CJUE | Diagnostic D7-F4 |
| Pénalités de retard (taux BCE + 10 points), indemnité de 40 €, mention obligatoire dans les CGV | https://entreprendre.service-public.gouv.fr/vosdroits/F23211 (art. L441-10 et D441-5 du Code de commerce) |
| Contenu obligatoire des mentions légales (LCEN art. 6-III) ; amendes | https://entreprendre.service-public.gouv.fr/vosdroits/F37351 (diagnostic D7-F1) |
| Cookies strictement nécessaires dispensés de consentement | https://entreprendre.service-public.gouv.fr/vosdroits/F31228 (diagnostic D7-F6) |
| Prospects : 3 ans à compter du dernier contact émanant du prospect | Référentiel CNIL « gestion commerciale », cité par des sources secondaires ; texte de la CNIL non relu (voir ci-dessous) |

Faits tirés du code : Vercel `cdg1` (`frontend/vercel.json`), Railway `europe-west4-drams3a`
(`.railway/railway.ts`), Scaleway Paris (`backend/app/ops/backup.py`, 30 quotidiennes et 12
mensuelles), Sentry sans données personnelles par défaut (`sendDefaultPii: false`,
`frontend/src/instrumentation-client.ts`), cookie de langue d'un an (`frontend/src/i18n/actions.ts`),
données de compte (`users` : e-mail, nom, identifiant Clerk — `backend/app/domain/models.py`), lecture
par IA vers `api.anthropic.com` seulement avec une clé (`backend/app/domain/invoices/registry.py`),
données envoyées au suivi de conteneurs (`backend/app/adapters/tracking/*.py`), lien de rendez-vous
Cal.com sur le site en production (lu le 16/10/2026).

## Non vérifié

- **Absence de `EXTRACTION_API_KEY` en production aujourd'hui** : lue absente le 17/09/2026 ; la
  configuration versionnée (`.railway/railway.ts`) ne la mentionne pas ; la production est arrêtée et
  ses variables n'ont pas été relues depuis. À vérifier dans Railway avant de répondre à un DPO.
- Le DSN de chaque projet Sentry pointe bien vers l'ingestion UE (seule l'organisation a été vue sur
  `de.sentry.io`), et l'offre Sentry souscrite (la page dit « 90 jours au plus »).
- Les numéros de téléphone de Vercel et Railway.
- Les noms exacts des cookies posés par Clerk (non mesuré dans un navigateur).
- La durée de conservation des journaux de Vercel pour l'offre souscrite.
- La certification DPF de Railway et de Cal.com (la page s'appuie sur leurs clauses contractuelles
  types, qui sont, elles, établies).
- Que Pierre a bien accepté le DPA de chaque prestataire (section 3).
- Le référentiel CNIL sur les prospects, relu seulement à travers des sources secondaires.
