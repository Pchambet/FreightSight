# docs/legal — brouillons juridiques et commerciaux

Cinq documents rédigés le 17 septembre 2026 pour préparer le premier design partner et le premier
pilote payant, en réponse aux findings A4-6 et A4-7 de
`docs/plan/audit-2026-09-17/A4-site-commercial-prod.md` (absence de mentions légales, de politique de
confidentialité et d'entité juridique déclarée) et à la section 5 du
`docs/plan/gtm-2026-09-17/00_PLAYBOOK_VENTE.md` (offre d'audit payant).

**Tous ces documents sont des brouillons rédigés par un outil d'IA.** Aucun n'a de valeur juridique
tant qu'il n'a pas été relu par un avocat (ou, à défaut de budget, vérifié point par point à la main
contre les textes officiels cités). Chaque document contient des `[À COMPLÉTER : …]` — des faits que
l'outil ne peut pas connaître ou inventer (SIREN, forme juridique, adresse, assureur) — et des
`[À VÉRIFIER : …]` — des points de droit ou de fait présentés comme probables mais pas confirmés en
source officielle au moment de la rédaction, faute de budget de recherche web restant pour cette
session. Ne rien publier avec un placeholder encore ouvert.

## Ce que contient chaque document

- **`mentions-legales.md`** — ce que l'article 6-III de la LCEN impose sur toute page publique :
  identité de l'éditeur, hébergeurs (Vercel et Railway), directeur de publication. C'est le document le
  plus urgent : la LCEN s'applique dès la mise en ligne, indépendamment de l'existence d'un client.
- **`politique-de-confidentialite.md`** — l'information RGPD (art. 13) pour le site public et pour
  l'application, avec une distinction explicite entre les données de compte (FreightSight responsable
  de traitement) et les données métier du client (FreightSight sous-traitant). Reprend et détaille les
  engagements déjà publiés sur `/securite`.
- **`accord-de-pilote.md`** — le contrat d'une page pour l'audit de coût de revient payant décrit dans
  le playbook de vente, avec sa variante pour la formule design partner gratuite de 8 semaines.
- **`dpa-article-28.md`** — le DPA annoncé sur `/securite` (« fourni à la signature du programme design
  partner ») mais qui n'existait nulle part avant ce document. Couvre chaque point obligatoire de
  l'article 28§3 du RGPD, avec une annexe sous-traitants et une annexe mesures de sécurité sourcées sur
  le code et la documentation ops réels.
- **`reponses-questionnaire-securite.md`** — 30 réponses courtes, chacune marquée VRAI AUJOURD'HUI (avec
  sa preuve dans le dépôt) ou PRÉVU, pour répondre vite et honnêtement à un questionnaire de DPO ou de
  DSI sans improviser au moment T.

## Ordre de priorité avant le premier pilote

1. **Décider la forme juridique** (auto-entreprise suffit à ce stade d'après l'audit A4-6) et
   l'immatriculer — sans ça, `mentions-legales.md`, `politique-de-confidentialite.md`,
   `accord-de-pilote.md` et `dpa-article-28.md` gardent tous un `[À COMPLÉTER]` sur l'identité de
   FreightSight, et un service achats de PME ne peut pas signer un contrat avec un compte Gmail.
2. **Publier `mentions-legales.md`** en page `/mentions-legales` dès que l'entité existe — c'est une
   obligation légale indépendante de toute vente, à ne pas laisser traîner.
3. **Publier `politique-de-confidentialite.md`** en page `/politique-de-confidentialite`, après avoir
   résolu ses `[À VÉRIFIER]` sur les mécanismes de transfert (Clerk, Vercel, Resend, Shipsgo) — vérifier
   les pages de conformité de chaque fournisseur avant publication, elles évoluent.
4. **Faire relire `dpa-article-28.md` par un avocat et le garder prêt à signer**, avant le premier appel
   commercial : `/securite` promet déjà qu'il existe, il faut que ce soit vrai.
5. **Utiliser `accord-de-pilote.md`** dès la première proposition d'audit payant envoyée à un prospect —
   trancher d'abord ses décisions commerciales ouvertes (prix, seuils de succès, prix cible
   post-pilote) avec le fondateur, ce ne sont pas des faits à vérifier mais des choix à faire.
6. **Garder `reponses-questionnaire-securite.md` à jour** au fil des changements d'infrastructure — le
   relire avant chaque envoi réel à un DPO, pas l'envoyer tel quel.

## LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md — à ne pas changer ici

Ces trois fichiers, à la racine du dépôt, décrivent un projet open source (licence MIT, guide de
contribution, code de conduite communautaire) alors que FreightSight est aujourd'hui un produit
commercial fermé, développé dans un dépôt privé. C'est le finding A4-6 de l'audit du 17/09/2026 : tant
que le dépôt reste privé, l'incohérence est sans effet pratique — personne d'extérieur ne peut se
prévaloir de la licence MIT sur du code qu'il n'a pas le droit de voir. Mais l'incohérence devient un
vrai risque le jour où le dépôt est rendu public, partagé pour un audit technique, ou visible dans une
due diligence : une licence MIT y autoriserait légalement quiconque à redistribuer le code, ce qui
contredit un produit commercial vendu par abonnement.

**Cette lane (`legal-pack`) n'a pas mandat pour toucher ces trois fichiers** : ils sont hors de son
périmètre (`docs/legal/` uniquement). Ce qu'il faut faire, par quelqu'un qui a mandat sur la racine du
dépôt :

- Remplacer `LICENSE` par une mention de type « Propriétaire — tous droits réservés » (ou la supprimer)
  tant que FreightSight reste un produit commercial fermé.
- Décider si `CONTRIBUTING.md` et `CODE_OF_CONDUCT.md` ont encore un sens (un dépôt privé à un seul
  contributeur n'a pas besoin d'un guide de contribution externe) et les retirer ou les adapter en
  conséquence.
- Ne faire ce changement qu'une fois la décision de forme juridique prise (point 1 ci-dessus), pour
  que la nouvelle mention de licence porte le bon titulaire de droits.

## Placeholders à compléter par le fondateur

Voir le champ `risks` du rapport de cette tâche pour la liste consolidée de tous les
`[À COMPLÉTER]` des cinq documents — en résumé : forme juridique, SIREN/SIRET, capital social,
adresse du siège, contact e-mail professionnel, nom du directeur de publication, prix et seuils de
l'audit pilote, délai de notification d'incident dans le DPA, conditions d'audit contractuel, effectif
avec accès aux données de production, existence d'une assurance RC professionnelle, et une dizaine de
`[À VÉRIFIER]` sur des faits externes (adresses d'hébergeurs, mécanismes de transfert des
sous-traitants américains, région Sentry effective).
