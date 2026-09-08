# Traductions à trancher

L'interface applicative est en français depuis le passage à next-intl. Les termes ci-dessous ont été
tranchés par défaut pour livrer, mais méritent l'avis d'un importateur : la colonne « retenu » est ce
qui est dans `frontend/messages/fr.json` aujourd'hui, changer une valeur ne demande que d'éditer ce
fichier (et son jumeau `en.json` si l'anglais bouge aussi).

| Terme source | Retenu | Alternatives écartées | Pourquoi c'est douteux |
|---|---|---|---|
| Cost `vendor` | Prestataire | Fournisseur, Émetteur de la facture | « Fournisseur » est déjà pris par le fournisseur de la commande ; un transitaire n'est pas un fournisseur au sens achat, mais « prestataire » est vague. |
| `DRAYAGE` | Camionnage / livraison | Post-acheminement, Traction | « Post-acheminement » est le mot des transitaires, « camionnage » celui des PME. À vérifier auprès d'un design partner. |
| `GATE_IN_FULL_ORIGIN` / `GATE_OUT_FULL` | Entrée terminal (origine) / Sortie terminal (plein) | Mise à quai / Enlèvement, Gate in / Gate out | Beaucoup de PME disent « gate in / gate out » en anglais dans leurs échanges avec le transitaire. |
| `Shipment` | Expédition | Envoi, Dossier | « Dossier » est le mot du transitaire (dossier d'importation) ; « expédition » est plus littéral. |
| `Last free day` | Dernier jour franc | Date limite de franchise, Fin du free time | « Free time » est utilisé tel quel par beaucoup de transitaires français. |
| `Landed cost` | Coût de revient rendu / coût rendu | Coût complet, Prix de revient | Le plan et la landing disent « coût de revient rendu » ; l'interface abrège en « coût rendu » faute de place dans les tableaux. |
| `Allocation` | Ventilation | Répartition, Affectation | « Ventilation » est le mot comptable ; « répartition » serait plus courant à l'oral. |
| `Load` (container load) | Chargement | Empotage, Ligne chargée | « Empotage » est précis (mise en conteneur) mais rare hors du métier. |
| `Pre-alpha` | Pré-alpha | (laissé en anglais) | Terme produit, pas métier : à supprimer plutôt qu'à traduire, une fois la bêta ouverte. |
| `SKU` | Référence / SKU | Article, Code article | Les deux cohabitent chez les importateurs. |

Deux points hors vocabulaire :

- **Les messages d'erreur du backend restent en anglais.** Le front traduit le `code` (`OVER_ALLOCATED`,
  `MISSING_BASIS`, `REQUIRED`…) via `errors.*` et n'affiche la phrase du serveur que pour les codes
  inconnus, ou pour la liste de lignes qu'elle ajoute après un `: `. Si un code apparaît sans clé, c'est
  l'anglais du serveur qui s'affiche : ajouter la clé dans `fr.json` et `en.json` suffit.
- **Les pages marketing ne passent pas par next-intl** : elles sont écrites en français dans le code.
  Les traduire en anglais demandera de les reprendre, ce qui n'est pas fait ici.
