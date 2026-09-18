# Reprendre le trimestre d'un prospect, en une heure et sans fausser un euro

L'audit d'un trimestre clos (490–990 € HT) se vend sur les propres fichiers du prospect. Ce document
dit quoi lui demander, dans quel ordre le charger, comment savoir qu'on peut lancer l'audit, et ce que
chaque source permet ou non d'affirmer.

## 1. Le kit à demander

Quatre fichiers et quelques factures. Chaque fichier se dépose dans **Imports**, par son type. Pour
chaque type, **Imports** propose un modèle CSV dont les en-têtes se reconnaissent seuls ; nos propres
exports se réimportent aussi tels quels.

| Fichier | Où le prospect le trouve | Sans lui |
|---|---|---|
| **Tarif** : référence, désignation, code SH, taux de droits, poids et volume unitaires, prix de vente HT et sa devise | Fiche article de l'ERP, tarif de vente | Pas de marge par référence ; droits répartis à la valeur CIF quand les commandes n'ont pas de taux |
| **Commandes** du trimestre, et celles dont un conteneur est arrivé dans le trimestre : n° de commande, fournisseur, devise, incoterm, date, lignes (référence, quantité, prix unitaire, taux de droits si connu) | Export des commandes fournisseurs de l'ERP | Rien à ventiler : pas d'audit |
| **Suivi des conteneurs** : n° de conteneur, type (40HC…), n° de B/L, compagnie, ports, ETD/ETA, arrivée réelle, déchargement, **sortie du terminal**, **restitution du vide**, n° de commande(s) chargée(s) | Tableau de suivi des arrivages de l'appro, ou du transitaire | Les conteneurs n'ont pas de date : **l'audit ne les voit pas** |
| **Frais** : date, prestataire, n° de facture, libellé, montant **HT**, devise, et si possible n° de conteneur, de B/L ou de commande | **Journal des achats** (factures des transitaires, transporteurs, commissionnaires en douane), tel que la compta l'exporte — le **FEC** filtré sur le journal d'achats convient : ses colonnes se reconnaissent seules. **Pas** les journaux d'opérations diverses : une provision ou une extourne n'est pas une facture | Pas de coût rendu réel |
| **Deux à cinq factures PDF** de transitaire du trimestre | Boîte mail de la compta | On ne vérifie pas que le journal correspond aux factures |

Demander aussi : **« Quel coefficient d'approche appliquez-vous aujourd'hui ? »** (ex. 1,12). Saisi
dans l'audit, il donne l'écart entre ce que le prospect croit et ce que ses conteneurs ont coûté.
C'est souvent la phrase qui vend.

## 2. L'ordre de chargement

1. **Tarif** — en premier : une fiche article ne prête son taux de droits, son code SH, son poids et
   son volume qu'aux lignes de commande écrites **après** elle. Une ligne déjà écrite garde ce qu'elle
   disait (un coût rendu déjà montré ne bouge pas parce que le tarif a changé).
2. **Commandes**.
3. **Suivi des conteneurs** — une commande présente sur un seul conteneur et chargée nulle part y est
   chargée en entier ; une commande répartie sur plusieurs conteneurs est laissée à une personne
   (PO_SPLIT : saisir les quantités de chaque conteneur).
4. **Frais** — les cibles (conteneurs, B/L, commandes) doivent exister : toujours après le suivi.
5. **Factures PDF** — une facture déjà présente dans les frais est refusée à la confirmation
   (« déjà enregistrée ») : c'est la garde contre le double compte, pas une erreur. La rejeter.

Chaque import passe par un **aperçu** obligatoire : l'argent d'abord (total en devise de base, par
type, par devise), les estimés remplacés, les doublons, les libellés à typer, les avoirs écartés. Ce
qui est validé est exactement l'aperçu que la personne a sous les yeux ; si les livres ont bougé entre
les deux, ou si le même fichier a été revu ailleurs avec d'autres options, l'application le dit et
montre les nouveaux chiffres avant d'écrire quoi que ce soit.

Un journal exporté ligne par ligne (compte, débit, crédit) est lu par ses comptes : seules les lignes
des **comptes de charges (classe 6)** deviennent des coûts ; la TVA (445…) et le total du fournisseur
(401…) sont écartés et comptés ; un avoir au crédit d'un compte de charges est compté comme avoir.

Un fichier de frais se **reprend** (« Annuler cet import ») tant que ses coûts ne sont ni partis dans
l'ERP ni dans un mois clos, et qu'aucun fichier plus récent du même journal ne s'appuie sur ses lignes :
dans ce cas, reprendre d'abord le plus récent.

## 3. Avant de lancer l'audit : la préparation

**Audit** affiche, pour la période, ce qui fausserait l'audit (**bloquants**) puis ce qu'il ne pourra
pas dire (**limites**). On lance l'audit quand il ne reste aucun bloquant.

Bloquants les plus fréquents à la reprise :

- **Conteneurs sans date** → le suivi des conteneurs manque ou n'a pas de dates d'arrivée.
- **Conteneurs sans marchandise** → une commande répartie (PO_SPLIT) : saisir les chargements.
- **Conteneurs sans fret** (achetés EXW, FCA, FOB ou sans incoterm) → la facture de fret manque au
  journal, ou le fret est porté par un autre compte.
- **Conteneurs sans droits** → la note de débours du commissionnaire en douane manque.
- **Factures à relire ou non lues** → les relire, ou rejeter celles qui sont déjà dans les frais.
- **Lignes de frais refusées à l'import** (sans conteneur connu, libellé sans type, pas de taux de
  change…) → charger le conteneur manquant ou typer le libellé, puis reprendre le fichier et le
  réimporter ; ou saisir la charge à la main. Chaque ligne disparaît dès qu'un coût la porte.
- **Même facture saisie deux fois** → supprimer l'une des deux saisies, après vérification sur les
  deux documents.
- **Avoir qui annule un coût enregistré** → le journal porte la ligne et son avoir, les livres la
  ligne : supprimer le coût annulé.

Limites qui ne bloquent pas mais se disent au client : avoirs écartés, lignes sans taux de droits,
conteneurs sans route ou sans taille (non comparés), frais d'un type « Autre », pas de prix de vente,
pas de coefficient d'approche, horloges de surestaries encore ouvertes.

## 4. Ce que chaque source de frais permet d'affirmer

| La source a… | L'audit peut… |
|---|---|
| n° de facture **et** prestataire | dire « facturé deux fois » avec certitude, reconnaître une même facture saisie deux fois |
| pas de n° de facture | seulement poser la question (« à vérifier ») d'un doublon |
| un type de coût en colonne | établir un constat |
| un type **déduit** du libellé ou choisi pour tout le fichier | seulement poser la question : le libellé peut désigner autre chose |
| une colonne de montants **TTC**, ou une ligne marquée TTC | rien : la colonne est refusée, la ligne aussi (sa part hors taxes n'est écrite nulle part) |
| des lignes de **TVA** | rien : elles sont écartées, quel que soit leur libellé ou leur type ; la TVA import avancée par le transitaire est gardée comme telle, hors coût rendu. Une ligne « droits et TVA » est refusée : elle doit être séparée |
| des avoirs (montants négatifs) | les écarter et les compter : vérifier qu'aucun ne rembourse un constat. Celui qui annule une ligne déjà en compte bloque l'audit jusqu'à ce que le coût annulé soit retiré |

Une reprise **ne contient pas d'estimés** : la règle « facture au-dessus de l'estimé » reste
silencieuse pour un trimestre repris. Ne jamais la promettre à un prospect qui n'a pas encore utilisé
l'application pendant un trimestre.

## 5. Contrôle en fin de reprise

- La préparation n'a plus de bloquant.
- Le coût rendu total = FOB des commandes + frais du journal + factures confirmées, chaque euro une
  fois (le test `backend/tests/test_intake_kit.py` le vérifie sur un kit complet, dans deux ordres de
  chargement).
- Les constats « établis » ont chacun deux pièces derrière eux ; les autres sont des questions.
