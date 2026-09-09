# Inbox factures — questions ouvertes

Comme pour le tracking et les jobs : ce que je n'ai pas tranché tout seul.

**La règle qui ne se discute pas, elle :** aucun coût n'est créé sans confirmation humaine. Elle est
écrite en tête de `app/domain/invoices/ports.py`, de `service.py` et du routeur, et testée
(`test_confirming_nothing_is_refused`, `test_one_bad_line_leaves_no_cost_at_all`).

## 1. Les octets dans Postgres

Les fichiers sont stockés dans la base (`document_blobs`), parce qu'il n'y a pas encore de compte
Scaleway. Ça tient pour des dizaines de factures, pas pour des milliers : à 2 Mo la facture, la
sauvegarde grossit vite et le `pg_dump` avec. L'adapter S3 est écrit et testé (signature V4 à la
main, pas de boto3) ; il suffit de renseigner `DOCUMENTS_S3_BUCKET`, `DOCUMENTS_S3_ACCESS_KEY`,
`DOCUMENTS_S3_SECRET_KEY` (région et endpoint par défaut : `fr-par`, Scaleway Paris) pour basculer.
→ **Question pour Pierre : à quel volume bascule-t-on ?** Mon avis : dès le premier design partner
qui envoie ses vraies factures.

Rien ne migre les fichiers déjà en base vers S3 le jour de la bascule : les anciens documents restent
lisibles (la colonne `documents.storage` dit où chacun est), mais il faudra un petit script.

## 2. Ce que l'extracteur par motifs ne sait pas faire

- **Les scans.** Pas de couche texte, pas de lecture : la facture passe en `FAILED` avec un message
  qui dit d'entrer les coûts à la main ou de configurer le modèle. Pas d'OCR, et je n'en ajoute pas
  sans qu'on ait vu de vrais scans.
- **Les tableaux en colonnes.** On prend le montant le plus à droite de la ligne, ce qui marche sur
  les factures testées (quantité, PU, montant) mais se trompera sur une facture qui met une remise en
  dernière colonne. → À revoir sur de vraies factures de transitaire.
- **La devise par ligne.** Une facture multi-devises est lue avec la devise de l'en-tête pour toutes
  les lignes sauf celles qui portent un symbole.

## 3. Le rattachement des charges

Quand la facture ne nomme qu'un seul conteneur connu de l'organisation, **toutes** ses lignes lui sont
rattachées. C'est le cas ordinaire (un transitaire facture par conteneur) et c'est déterministe, donc
c'est décidé dans `checks.py`, pas par ce qui a lu le document.

Quand elle en nomme plusieurs, seules les lignes qui citent explicitement un numéro sont rattachées ;
les autres arrivent sans cible et la confirmation les refuse tant qu'un humain n'a pas choisi. → Est-ce
le bon compromis, ou faut-il proposer une répartition ? Je ne l'ai pas fait : une répartition proposée
qu'on accepte sans réfléchir est exactement le genre de chiffre faux qu'on cherche à éliminer.

## 4. Le modèle

`EXTRACTION_API_KEY` + `EXTRACTION_MODEL` (défaut `claude-opus-5`) activent l'extracteur LLM, qui
passe **avant** les motifs. Il reçoit la liste des conteneurs et des commandes de l'organisation pour
*reconnaître* les références au lieu de les inventer ; tout ce qu'il renvoie hors de ces listes est
jeté par `checks.py`, à voix haute (la ligne le dit dans ses notes).

Non fait, volontairement : pas de jeu d'évaluation. Le plan en prévoit un (20 vraies factures
anonymisées, seuil 90 % de lignes correctes avant activation par défaut) et il faut de vraies
factures pour le construire. → **À faire avec le premier design partner, avant d'activer le modèle en
production.**

## 5. Les contrôles arithmétiques

Σ lignes + TVA doit égaler le total, à 0,02 près. Sinon la confiance est plafonnée à 0,5 et la revue
dit de combien et dans quel sens ça cloche. Ce que ça **ne** fait **pas** : deviner la ligne
manquante. → Faut-il refuser la confirmation quand l'écart dépasse un seuil ? Aujourd'hui non : c'est
un avertissement, l'humain décide.

## 6. Divers

- Une facture confirmée est de l'histoire : on ne peut plus corriger ses lignes ni la rejeter. Pour
  revenir en arrière, on supprime les coûts. → À confirmer que c'est le bon geste côté produit.
- Pas de TVA en tant que coût : la ligne TVA n'est pas proposée comme charge (elle est récupérable et
  le moteur l'exclut déjà du coût de revient). Le montant est stocké sur la facture pour le contrôle.
- La date de coût est la date de facture, et le taux BCE est celui de cette date. Une devise sans taux
  à cette date marque la ligne, elle ne bloque pas la revue.
