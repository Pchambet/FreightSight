# Conditions générales de vente — brouillon et justification

Le texte publié est celui de `frontend/src/app/(marketing)/cgv/page.tsx` ; ce document dit pourquoi
chaque article est écrit ainsi et ce que Pierre doit trancher avant de le dater. La page reste en 404
tant que l'identité de l'éditeur n'est pas complète **et** que `termsEffectiveDate` est vide
(`frontend/src/lib/site.ts`) : des CGV qui ne nomment pas le vendeur, ou que personne n'a approuvées,
n'engagent personne.

**Brouillon rédigé par un outil d'IA, non relu par un avocat.** Les choix ci-dessous sont prudents
pour le vendeur, sans clause qu'un juge écarterait d'emblée entre professionnels.

## Pourquoi des CGV

Entre professionnels, les CGV ne sont pas obligatoires, mais elles doivent être communiquées à tout
acheteur professionnel qui les demande (un refus est sanctionné jusqu'à 75 000 € d'amende,
diagnostic D7-F5), et elles **doivent** indiquer les conditions de règlement, les pénalités de retard et
l'indemnité forfaitaire de 40 € (https://entreprendre.service-public.gouv.fr/vosdroits/F23211).

## Article par article

| Art. | Contenu | Pourquoi | À trancher |
|---|---|---|---|
| 1 | Identité du vendeur (depuis `site.publisher`), B2B seulement, le devis prime | Le service n'est vendu qu'à des entreprises ; exclure les consommateurs évite le droit de la consommation (rétractation, médiation) | — |
| 2 | Le service : logiciel en ligne, périmètre fixé par le devis, en développement actif | Le site dit « pré-alpha » ; on promet seulement de ne pas retirer une fonction essentielle du plan en cours | — |
| 3 | Vente formée par devis accepté ; abonnement mensuel, résiliable par e-mail en fin de mois ; résiliation pour manquement après 30 jours de mise en demeure | Simple et symétrique ; rien n'oblige un design partner à rester | Durée minimale d'engagement ? (aucune proposée) |
| 4 | Prix du devis, HT, TVA si assujetti ; mensuel d'avance ; audit facturé à la commande ; paiement à 30 jours date de facture ; pénalités BCE + 10 points ; 40 € ; suspension 15 jours après mise en demeure | Délai et pénalités : le défaut légal (art. L441-10), dans le plafond de 60 jours ; « TVA si assujetti » couvre la franchise en base sans changer le texte | Délai de paiement, délai avant suspension |
| 5 | Le client protège ses accès, a le droit d'importer ses fichiers, vérifie les résultats avant décision | Un coût de revient faux peut coûter une marge : le service signale ce qui manque et ne crée aucun coût sans validation humaine (règles 1 et 2 du produit), le client garde la décision | — |
| 6 | Données du client : propriété du client, FreightSight sous-traitant (DPA), export à tout moment, suppression sous 30 jours en fin de contrat, sauvegardes expirées sous 12 mois | Reprend mot pour mot les engagements de `/securite` ; la durée des sauvegardes vient de `backend/app/ops/backup.py` (30 quotidiennes, 12 mensuelles) | — |
| 7 | Disponibilité : obligation de moyens, maintenance annoncée | Aucun SLA chiffré tant qu'aucune mesure ne le soutient | Un SLA plus tard, s'il est mesuré |
| 8 | Responsabilité : dommages directs prouvés ; pas d'indirects ; plafond = sommes payées sur 12 mois ; pas de plafond en cas de faute lourde ou dolosive | Usage courant en SaaS B2B ; un plafond dérisoire ou couvrant la faute lourde serait réputé non écrit | **Le plafond**, à aligner sur la police RC Pro (D7-F12) |
| 9 | Propriété intellectuelle : droit d'usage non exclusif, non cessible, pour la durée de l'abonnement | L'article porte sur le service hébergé. Le code, lui, est publié sous FSL-1.1-MIT (`LICENSE`) : Pierre en reste titulaire, et la licence interdit seulement d'en faire un service concurrent | — |
| 10 | Confidentialité réciproque pendant le contrat et 3 ans après | Reprend `/securite` (« aucun croisement entre sociétés ») | Durée après la fin |
| 11 | Droit français ; amiable d'abord ; juridiction de droit commun | Pas de clause attributive de compétence : elle n'est valable qu'entre commerçants (art. 48 du Code de procédure civile), ce que n'est pas forcément un entrepreneur individuel en BNC | Clause de compétence si une société commerciale est créée |
| 12 | Version en vigueur à la date d'acceptation ; communiquées sur demande | Obligation de communication (art. L441-1) | — |

## Ce que les CGV ne font pas

- Pas d'acceptation à l'inscription : l'application n'a ni paiement ni case à cocher. Les CGV
  s'appliquent par le devis, qui doit les citer (« Conditions générales de vente : <site>/cgv »).
- Pas de prix : ils sont dans le devis. La grille de la page d'accueil est indicative.
- Les mentions de facture (délai de paiement, 40 €, « TVA non applicable, art. 293 B du CGI » en
  franchise) se mettent sur chaque facture, pas seulement ici.
