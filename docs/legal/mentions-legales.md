# Mentions légales — brouillon et justification

Le texte publié est celui de `frontend/src/app/(marketing)/mentions-legales/page.tsx`, alimenté par
`frontend/src/lib/site.ts`. La page répond 404, et aucun lien n'y mène, tant qu'un champ exigé par la
loi est vide. Ce document dit ce que la loi demande et d'où vient chaque valeur.

**Brouillon rédigé par un outil d'IA, non relu par un avocat.**

## Ce que la loi exige

Article 6-III de la loi n° 2004-575 du 21 juin 2004 (LCEN), résumé par
https://entreprendre.service-public.gouv.fr/vosdroits/F37351 (diagnostic D7-F1) : tout éditeur
professionnel d'un site accessible en France affiche, dès la mise en ligne,

- **personne physique** : nom, prénom, domicile, téléphone, e-mail, numéro d'immatriculation (RNE ou
  RCS) le cas échéant ;
- **société** : dénomination, forme juridique, capital, siège, téléphone, e-mail, numéro
  d'immatriculation ;
- le numéro de TVA intracommunautaire s'il en existe un ;
- le **directeur de la publication** ;
- l'**hébergeur** : nom, adresse, téléphone.

Amendes affichées par service-public : jusqu'à 75 000 € pour une personne physique, 375 000 € pour une
personne morale.

## 1. Éditeur — rempli le 19 octobre 2026, sauf le téléphone

| Mention | Champ de `site.publisher` | Valeur |
|---|---|---|
| Nom ou dénomination | `legalName` | Pierre Chambet |
| Forme juridique (et capital pour une société) | `legalForm` | Entrepreneur individuel (EI), inscrit le 26 août 2026 (INSEE, RNE), NAF 6201Z |
| SIREN | `siren` | 109 186 510 (siège : SIRET 109 186 510 00011) |
| Registre | `registry` | Vide : entrepreneur individuel |
| TVA intracommunautaire | `vatNumber` | Vide en franchise en base (art. 293 B du CGI). [À VÉRIFIER par Pierre : le FR48109186510 affiché par les annuaires est calculé depuis le SIREN, il ne prouve pas un assujettissement] |
| Adresse | `address` | 211 chemin du Pré Montclair, 74330 Poisy (adresse du siège déclarée ; une domiciliation la remplacerait) |
| Téléphone | `phone` | [À COMPLÉTER par Pierre : c'est le seul champ qui manque pour publier la page] |
| E-mail | `email` | `pierrechambet@gmail.com` (déjà affiché sur le site) ; à remplacer par une adresse sur domaine propre quand il existe |

## 2. Directeur de la publication — rempli

`site.publisher.publicationDirector` : Pierre Chambet.

## 3. Hébergeurs — rempli ; un contact à la place du téléphone

Le site (pages et interface) et l'application (API, base de données) sont hébergés séparément ; les deux
sont listés, car l'obligation vise quiconque stocke ce que le service publie.

| | Vercel Inc. | Railway Corporation |
|---|---|---|
| Rôle | Site et interface (fonctions serveur région Paris `cdg1`, CDN mondial) | API et base de données (région Amsterdam `europe-west4-drams3a`) |
| Adresse | 440 N Barranca Avenue #4133, Covina, CA 91723, États-Unis | 548 Market St PMB 68956, San Francisco, CA 94104, États-Unis |
| Source de l'adresse | https://vercel.com/legal/privacy-policy (1er juin 2026), aussi dans https://vercel.com/legal/terms | https://railway.com/legal/dpa (annexe B) |
| Téléphone | Non publié par Vercel : la page donne https://vercel.com/contact | Non publié par Railway : la page donne https://help.railway.com |

L'ancienne adresse « 340 S Lemon Ave, Walnut » de Railway, citée par le premier brouillon, n'est plus
celle de ses pages légales.

## 4. Propriété intellectuelle — rempli

« Les textes, images, marques, logos et logiciels de ce site et du service FreightSight appartiennent à
<éditeur> ou sont utilisés avec l'autorisation de leurs titulaires. Toute reproduction ou réutilisation
sans autorisation écrite préalable est interdite. » Cohérent avec `LICENSE` (tous droits réservés,
Pierre Chambet, 2026). Si une société est créée, Pierre lui cède ou lui concède ses droits sur le code :
à prévoir à la création (statuts ou acte de cession), sinon la société vend un logiciel qui ne lui
appartient pas.

## 5. Données personnelles — rempli

Renvoi vers `/confidentialite` (publiée).

## Ce qui n'est pas dans la page

Le droit applicable et le règlement des litiges relèvent des CGV (`cgv.md`, art. 11), pas des mentions
légales.
