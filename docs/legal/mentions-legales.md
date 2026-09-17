# Mentions légales — brouillon

Document de travail pour la page `/mentions-legales` du site FreightSight. Rédigé pour respecter
l'article 6-III de la loi n° 2004-575 du 21 juin 2004 pour la confiance dans l'économie numérique
(LCEN), qui impose ces informations à tout éditeur professionnel d'un site accessible au public en
France — dès la mise en ligne, pas seulement à partir de la première vente.

**Ce document est un brouillon rédigé par un outil d'IA. Il doit être relu par un avocat ou, a minima,
vérifié point par point avant publication.** Chaque `[À COMPLÉTER : …]` est une information que
l'outil ne peut pas connaître ou inventer (identité juridique, adresse, numéros officiels). Rien n'a
été inventé : pas de SIREN, pas de forme juridique, pas d'adresse fictifs.

---

## 1. Éditeur du site

- Nom / raison sociale : [À COMPLÉTER : nom de la personne physique (micro-entrepreneur) ou raison
  sociale de la société]
- Forme juridique : [À COMPLÉTER : entreprise individuelle / micro-entreprise / SASU / autre — l'audit
  A4-6 suggère qu'une micro-entreprise suffit à ce stade, mais c'est une décision du fondateur]
- Capital social : [À COMPLÉTER : sans objet si entreprise individuelle ; montant si société]
- Numéro SIREN / SIRET : [À COMPLÉTER : obtenu à l'immatriculation, non existant à ce jour d'après
  l'audit A4-6 — « aucune mention de SIREN/forme juridique trouvée »]
- Numéro de TVA intracommunautaire : [À COMPLÉTER : le cas échéant — une micro-entreprise en
  franchise en base de TVA n'en a pas et doit alors faire figurer la mention « TVA non applicable,
  art. 293 B du CGI »]
- RCS (ville d'immatriculation) : [À COMPLÉTER : sans objet pour une entreprise individuelle non
  commerçante inscrite au RNE plutôt qu'au RCS — à trancher avec le statut juridique]
- Siège social / adresse postale : [À COMPLÉTER : une adresse professionnelle ou personnelle de
  domiciliation, pas une boîte postale seule]
- Contact : [À COMPLÉTER : adresse e-mail professionnelle — aujourd'hui `pierrechambet@gmail.com`,
  `frontend/src/lib/site.ts:4`. Une adresse Gmail n'est pas interdite en mentions légales, mais
  l'audit A4-6 note que ça nuit à la crédibilité commerciale ; à remplacer par une adresse sur domaine
  propre dès que le domaine existe]
- Téléphone : [À COMPLÉTER : optionnel en LCEN pour une personne physique, mais utile pour la
  crédibilité commerciale]

## 2. Directeur de la publication

- Nom : [À COMPLÉTER : en général le fondateur — Pierre Chambet, sous réserve de confirmation]
- Qualité : [À COMPLÉTER : gérant / président / entrepreneur individuel, selon la forme retenue]

## 3. Hébergeurs

Le site FreightSight est composé d'une interface web (front) et d'une API (back), hébergées
séparément. Les deux doivent apparaître : l'obligation LCEN vise « la personne physique ou morale qui
assure [...] le stockage de signaux, d'écrits, d'images, de sons ou de messages », ce qui couvre
chaque hébergeur effectivement utilisé.

### Interface web (front)

- Nom : Vercel Inc.
- Adresse : [À VÉRIFIER : adresse officielle actuelle — historiquement 440 N Barranca Ave #4133,
  Covina, CA 91723, États-Unis ; à confirmer sur la page légale de vercel.com avant publication]
- Site : https://vercel.com
- Note technique : le rendu serveur (fonctions) est exécuté dans la région de Paris (`cdg1`), le CDN
  pour les fichiers statiques est mondial — cohérent avec `docs/04_ops_railway_vercel.md` §4 et la
  page `/securite`.

### API et base de données (back)

- Nom : Railway Corporation
- Adresse : [À VÉRIFIER : adresse officielle actuelle — historiquement 340 S Lemon Ave #4021,
  Walnut, CA 91789, États-Unis ; à confirmer sur la page légale de railway.com avant publication]
- Site : https://railway.com
- Note technique : les services tournent dans la région d'Amsterdam (`europe-west4-drams3a`) depuis le
  8 septembre 2026 (`docs/04_ops_railway_vercel.md` §4, `docs/plan/audit-2026-09-17/F1-verifications-prod.md`
  confirme la configuration lue en production).

## 4. Propriété intellectuelle

[À COMPLÉTER avec un avocat : clause standard — le contenu du site (textes, marque, logo, mise en
page) est la propriété de [éditeur] ou de ses concédants ; toute reproduction sans autorisation
préalable est interdite. Attention à la cohérence avec le fichier `LICENSE` du dépôt de code — voir
`docs/legal/README.md`, point sur `LICENSE`/`CONTRIBUTING.md`/`CODE_OF_CONDUCT.md` : ces fichiers
n'ont d'effet que si le code source lui-même est rendu public, ce qu'il n'est pas aujourd'hui (dépôt
privé), mais ils ne doivent pas être laissés en l'état si le dépôt devait un jour être ouvert ou audité
par un tiers.]

## 5. Données personnelles

Le traitement des données personnelles des visiteurs du site et des utilisateurs de l'application est
décrit dans la politique de confidentialité : voir `docs/legal/politique-de-confidentialite.md` (à
publier sous `/politique-de-confidentialite` une fois validée).

## 6. Médiation et litiges

[À COMPLÉTER avec un avocat : clause de droit applicable (droit français) et de juridiction compétente
en cas de litige avec un client professionnel — pour un contrat B2B entre professionnels, la clause
attributive de compétence est possible mais doit être rédigée avec soin.]

---

**Ordre de complétion recommandé** (voir aussi `docs/legal/README.md`) : ce document dépend de deux
décisions préalables du fondateur — la forme juridique et le nom de domaine propre. Les deux
adresses d'hébergeur marquées `[À VÉRIFIER]` doivent être confirmées sur les pages légales officielles
de Vercel et Railway juste avant publication (elles changent parfois).
