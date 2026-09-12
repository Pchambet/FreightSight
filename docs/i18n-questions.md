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

## Les e-mails d'alerte

Le digest part dans la langue de l'organisation (`organizations.locale`, « fr » par défaut, réglable
par `PATCH /organization`). Les phrases sont construites côté serveur depuis le `kind` et le
`payload` de l'alerte, exactement comme l'écran le fait dans
`frontend/src/features/alerts/text.ts` — elles sont dans `backend/app/domain/alerts/text.py` et un
test (`test_the_email_says_exactly_what_the_screen_says`) compare les deux fichiers mot pour mot,
pour que reformuler une alerte dans `frontend/messages/fr.json` fasse échouer la CI plutôt que de
laisser l'e-mail de 6 h dire l'ancienne phrase pendant des mois.

Ce qui reste ouvert :

- **La langue est par organisation, pas par personne.** Une équipe franco-anglaise reçoit un seul
  digest, dans une seule langue. Une préférence par utilisateur demanderait un digest par langue et
  une colonne sur `users` : pas fait tant que personne ne l'a demandé.
- **`TRACKING_DELIVERY_FAILED` n'a pas de phrase**, ni sur l'écran ni dans l'e-mail : l'alerte part
  avec son titre anglais stocké. C'est une panne interne (un webhook qu'on n'a pas su traiter), pas
  une nouvelle sur la marchandise ; à traduire le jour où elle est montrée aux clients.
- **Les dates sont écrites en UTC** dans les e-mails comme sur l'écran (`20/09/2026 06:30`). Une ETA
  lue dans deux fuseaux est deux faits différents ; le fuseau de l'organisation viendra avec le
  réglage correspondant, s'il est demandé.

Deux points hors vocabulaire :

- **Les messages d'erreur du backend restent en anglais.** Le front traduit le `code` (`OVER_ALLOCATED`,
  `MISSING_BASIS`, `REQUIRED`…) via `errors.*` et n'affiche la phrase du serveur que pour les codes
  inconnus, ou pour la liste de lignes qu'elle ajoute après un `: `. Si un code apparaît sans clé, c'est
  l'anglais du serveur qui s'affiche : ajouter la clé dans `fr.json` et `en.json` suffit.
- **Les pages marketing ne passent pas par next-intl** : elles sont écrites en français dans le code.
  Les traduire en anglais demandera de les reprendre, ce qui n'est pas fait ici.
