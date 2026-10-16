# Kit testeur FreightSight — « Terrasses du Ponant »

**Pour qui :** quelqu'un qui teste le site en ligne et n'a encore rien vu de concret.
**Durée :** 45 min. **Il vous faut :** les 6 fichiers de ce dossier et un compte sur le site.

<!-- kit-dates -->
> **Ce kit a été préparé le 16/10/2026.** Ses dates en dépendent, le guide y renvoie :
>
> - le journal des frais (fichier 4) couvre le trimestre **du 01/07/2026 au 30/09/2026** : c'est la période de l'audit (étape 6) ;
> - **MSCU6702211** a été déchargé le **13/10/2026**, son dernier jour franc est le **17/10/2026** (étape 2) ;
> - **MSCU6715564** est attendu le **25/10/2026** (étape 7).
>
> Ces dates passées, rien ne casse : un dernier jour franc dépassé, ce sont des surestaries qui
> courent, et l'audit se lit sur la période ci-dessus. Les montants, eux, ne changent jamais.
<!-- /kit-dates -->

Une organisation vide ne montre rien : FreightSight ne vaut que sur des conteneurs, des commandes et des
factures. Ce kit vous donne ceux d'une fausse PME, tels qu'elle les enverrait vraiment : un export de
son ERP, le tableau de suivi de son transitaire, le journal des achats de son comptable et deux
factures PDF. Vous les déposez, et l'outil fait le reste.

---

## 1. La fiche — qui vous êtes

Vous êtes **DAF de Terrasses du Ponant SAS** (Carquefou, près de Nantes). La société importe du mobilier
de jardin et de l'éclairage extérieur de Chine et du Vietnam : environ 3 conteneurs 40' par mois, arrivée
au Havre, livraison à l'entrepôt de Carquefou.

| | |
|---|---|
| **Fournisseurs** | Ningbo Greenleaf Outdoor (parasols, lampes solaires, coussins) · Ningbo Suncraft Furniture (chaises alu) · Saigon Teak Craft (tables en teck) |
| **Prestataires** | Marée Haute Logistique (transitaire et commissionnaire en douane) · Transports Kervadec (camionnage) |
| **Votre méthode actuelle** | Prix d'achat FOB × **1,12** = « coût de revient ». Le même coefficient pour tout, depuis toujours |
| **La question du patron** | « Nos chaises empilables à 39 € HT, on gagne vraiment combien dessus ? » |

Toutes ces sociétés sont fictives.

## 2. Ce que l'outil promet (la proposition de valeur)

1. **Le vrai coût de revient de chaque article**, conteneur par conteneur : le fret, les frais de port,
   le dédouanement, les droits et la livraison répartis sur chaque ligne de commande, au centime.
2. **Lire les factures du transitaire à votre place** : un PDF déposé devient des coûts, après votre
   validation — jamais sans.
3. **Ne rien payer deux fois** : une facture déjà en compta est refusée, un frais facturé deux fois est
   signalé, un tarif anormal est mis en question.
4. **Voir venir les surestaries** : le dernier jour franc de chaque conteneur, et une alerte avant qu'il
   ne soit trop tard.
5. **Un audit du trimestre** prêt à imprimer : ce que vos importations ont réellement coûté, contre ce
   que votre coefficient supposait.

Le parcours ci-dessous vous fait vivre ces cinq promesses. À chaque étape : **le geste**, puis **ce que vous
devez voir**. Si vous voyez autre chose, c'est un retour précieux — notez-le.

## 3. Le contenu du kit

| Fichier | Ce que c'est, dans la vraie vie |
|---|---|
| `1-tarif.csv` | La fiche article de l'ERP : code douanier, taux de droits, poids, volume, prix de vente |
| `2-commandes.csv` | L'export des commandes fournisseurs (11 commandes, 14 lignes, 3 fournisseurs) |
| `3-suivi-conteneurs.csv` | Le tableau de suivi des arrivages (10 conteneurs, dont un encore au port et un en mer) |
| `4-frais-trimestre.csv` | Le journal des achats du dernier trimestre, tel que le comptable l'exporte |
| `5-facture-transitaire-MSCU6702211.pdf` | La facture du conteneur arrivé juste avant la préparation du kit — **nouvelle** |
| `6-facture-transitaire-MSCU6678835.pdf` | Une facture **déjà saisie** en compta, renvoyée par erreur |

Ces fichiers s'ouvrent dans Excel ; inutile de les modifier.

---

## 4. Le parcours — à cocher

### Avant de commencer

- [ ] **Partir d'une organisation vide.** Si votre organisation contient déjà des essais, créez-en une
  nouvelle (sélecteur d'organisation en haut à droite, à côté de la cloche → *Créer une organisation*, par
  exemple
  « Terrasses du Ponant — test »). Sinon, vos essais se mélangent aux chiffres du kit.

### Étape 1 — Charger la société (10 min)

Menu **Imports → Nouvel import**. Pour chaque fichier : **choisir vous-même le type** (celui qui est
coché au départ n'est pas forcément le bon), *Déposer et détecter les colonnes* (les colonnes se
reconnaissent seules), *Valider (à blanc)*, lire l'aperçu — **rien n'est encore écrit** — puis
*Importer*. L'ordre compte : chaque fichier s'appuie sur les précédents.

- [ ] Type **Tarif** → `1-tarif.csv` → **5 fiches produits**.
- [ ] Type **Commandes** → `2-commandes.csv` → **11 commandes, 14 lignes**. Les avertissements qui
  disent que le poids, le volume et le taux de droits sont repris de la fiche produit sont normaux :
  ils viennent du tarif, vous n'avez pas à les ressaisir.
- [ ] Type **Suivi des conteneurs** → `3-suivi-conteneurs.csv` → **10 conteneurs, 14 chargements**, et un
  avertissement sur **MSCU6702211** : déchargé, jamais sorti du terminal, ses surestaries courent.
  Retenez-le.
- [ ] Type **Frais** → `4-frais-trimestre.csv` → l'aperçu montre l'argent d'abord : **42 coûts pour
  45 758,53 € HT**, par type (fret 29 510 €, droits 7 878,53 €, camionnage 4 265 €…), et **un avoir de
  −80 € écarté et compté** — un avoir n'est pas un coût.

> **Pourquoi c'est important :** un client réel n'a rien à ressaisir. Il envoie ce qu'il a déjà, dans le
> format de son ERP et de son comptable (point-virgule, virgule décimale, accents).

### Étape 2 — Le conteneur qui va coûter cher (3 min)

- [ ] Menu **Conteneurs**. **MSCU6702211** est signalé à risque : déchargé au Havre, toujours au
  terminal. Son dernier jour franc est celui de l'encadré en tête de ce guide ; une fois cette date
  passée, le conteneur l'a dépassé et les surestaries courent : même signal, en plus grave.
- [ ] La **cloche** en haut à droite porte **1 alerte** pour ce conteneur (menu **Alertes** pour la lire).

> **Valeur :** sans l'outil, on découvre les surestaries sur la facture de l'armateur, un mois après.

### Étape 3 — La facture du transitaire arrive (7 min)

- [ ] Menu **Factures** → *Déposer une facture* → `5-facture-transitaire-MSCU6702211.pdf` → *Déposer
  et lire*. Attendre quelques secondes la lecture.
- [ ] La facture **n° 0571** de Marée Haute Logistique (5 943,09 € HT, TVA 0 % : transport international
  exonéré) est lue en
  **5 lignes**, chacune typée et rattachée au conteneur **MSCU6702211** :

  | Ligne | Montant |
  |---|---|
  | Fret maritime | 3 780,00 € |
  | THC destination Le Havre | 285,00 € |
  | Dédouanement import | 145,00 € |
  | Camionnage Le Havre – Carquefou | 440,00 € |
  | Débours droits de douane | 1 293,09 € |

- [ ] *Retenir les 5 lignes*. Avant de confirmer, vérifiez que le bandeau au-dessus des lignes les compte
  **toutes** comme retenues et que leur somme égale le total HT de la facture ; sinon recliquez
  *Retenir*. Puis *Confirmer*. Rien n'est devenu un coût avant ce clic.
- [ ] Ouvrir le conteneur **MSCU6702211** (le lien « Voir le conteneur » de la page de la facture y
  mène) : le **coût rendu par ligne de commande** s'affiche.
  **Parasol 3 m : 47,91 €** pour un prix d'achat de 38,50 € (+24 %) ; **coussin : 3,95 €** pour 3,20 €.

### Étape 4 — La facture déjà payée (3 min)

- [ ] Déposer `6-facture-transitaire-MSCU6678835.pdf`. Chaque ligne est signalée en rouge : *un coût de ce
  type et de ce montant existe déjà sur ce conteneur* (la facture est dans le journal du comptable).
  Comme ces lignes sont des doublons, aucun bouton ne les retient en bloc : **cochez une ligne à
  la main** (*Accepter*).
- [ ] Essayer *Confirmer* : **refusé**, l'outil dit que cette facture est déjà enregistrée. Cliquer
  *Rejeter*.

> **Valeur :** la même facture envoyée deux fois, par mail puis par courrier, ne sera jamais comptée deux
> fois.

### Étape 5 — Le parasol et la lampe : la méthode change le prix (5 min)

- [ ] Ouvrir le conteneur **MSCU6614208** (600 parasols + 1 500 lots de lampes solaires).
  Coût unitaire : **parasol 45,04 €**, **lampe 7,70 €** — les frais sont répartis à la valeur, comme dans
  la plupart des tableurs.
- [ ] Dans **Coût rendu par ligne de commande**, *Et si la ventilation était :* passer le **fret maritime**, les
  **THC** et le **camionnage** **au volume**. **Parasol 46,13 €**, **lampe 7,27 €**. C'est une simulation,
  rien n'est enregistré.

> **Valeur :** le parasol remplit le conteneur, la lampe presque pas. Répartir le fret à la valeur
> sous-estime le coût des articles encombrants et surestime celui des petits articles chers.

### Étape 6 — L'audit du trimestre : le moment « aïe » (10 min)

- [ ] Menu **Audit des coûts** → période **du … au …** du trimestre de l'encadré en tête de ce guide
  (champs *Du* et *Au*, puis *Appliquer*). Tant que ce trimestre est le dernier clos, le raccourci
  *Dernier trimestre clos* donne la même chose.
- [ ] Dans *Le coefficient que vous appliquez*, saisir **1,12**.
- [ ] Lire **L'essentiel** :
  - **8 conteneurs**, 189 180 € achetés FOB, **234 938,53 € de coût rendu** ;
  - **coefficient d'approche réel : 1,24**, pas 1,12 ;
  - **23 056,93 € de frais non couverts par votre coefficient** sur le trimestre ;
  - **à faire justifier par vos prestataires : 285 € établis et 715 € à vérifier** ;
  - **surestaries payées : 380 €** sur 1 conteneur.
- [ ] Coefficient **par fournisseur** : Ningbo Suncraft (les chaises) **1,46** — contre 1,20 pour Greenleaf
  et 1,18 pour les tables en teck.
- [ ] La réponse au patron, ligne **CHA-ALU-ANT** : coût rendu **30,95 €** la chaise ; la marge calculée sur
  le FOB serait de **45,7 %**, la **marge réelle est de 20,6 %**. Vingt-cinq points de marge invisibles.
- [ ] Les **constats** :
  - **MSCU6662309** — la manutention portuaire (THC, 285 €) facturée **deux fois** par Marée Haute
    Logistique, sur deux factures : *établi* ;
  - **MSCU6651475** — camionnage à 1 150 € quand la médiane de la ligne Ningbo → Le Havre est à 435 € :
    *à vérifier* (une question à poser, pas une économie promise) ;
  - **CMAU4437293** — resté 9 jours au terminal, soit 5 jours après son dernier jour franc : 380 € de
    surestaries.
- [ ] Essayer *Imprimer ou enregistrer en PDF*, le lien de partage et l'export *Constats (CSV)*.

> **Valeur :** c'est le document que le DAF pose devant son patron, et que l'on vend en entrée
> (« votre dernier trimestre, audité »).

### Étape 7 — Le conteneur encore en mer : estimer avant la facture (5 min)

- [ ] **Paramètres → Barèmes d'estimation** : ajouter quatre barèmes, par conteneur, au forfait, en
  EUR — **Fret maritime 3 650**, **Manutention portuaire (THC) 285**, **Frais de dédouanement 145**,
  **Camionnage / livraison 440**. (N'ajoutez pas de barème de surestaries pour ce test. La section
  peut se refermer après chaque ajout : rouvrez-la pour retrouver vos barèmes.)
- [ ] Ouvrir le conteneur **MSCU6715564** (520 chaises, arrivée prévue à la date de l'encadré) →
  *Estimer avec les barèmes*. Les droits de douane s'estiment seuls à partir du tarif.
- [ ] Coût rendu **estimé de la chaise : 30,96 €** pour un prix d'achat de 21,50 € — avant toute facture.
  Quand la vraie facture arrivera, elle remplacera chaque estimé un pour un, et l'écart sera mesuré.

### Étape 8 — Se promener (libre)

- [ ] **Vue d'ensemble** : coefficient d'approche par mois et par fournisseur.
- [ ] **Références** → `CHA-ALU-ANT` : le coût unitaire de la chaise, conteneur après conteneur.
- [ ] **Rapports** : coût rendu par fournisseur, par route, par type de frais ; exports CSV.
- [ ] **Historique** : un journal en ajout seul — les factures confirmées, les imports de frais, vos
  modifications, qui les a faites et quand.
- [ ] Le sélecteur de langue : tout existe aussi en anglais.

---

## 5. Vos retours — les cinq questions

Notez les réponses au fil de l'eau, même en vrac :

1. À quelle étape avez-vous **compris** ce que fait l'outil ? À quelle étape avez-vous **décroché** ?
2. Un chiffre vous a-t-il paru **faux** ou **inexpliqué** ? Lequel, sur quel écran ?
3. Un bouton, un mot ou un message vous a-t-il **bloqué** ? (capture d'écran bienvenue)
4. Des cinq promesses du §2, laquelle vaut de l'argent pour une PME qui importe ? Laquelle ne sert à rien ?
5. Si vous étiez ce DAF : **paieriez-vous l'audit du trimestre** ? Combien ?

## 6. Si quelque chose coince

| Symptôme | Que faire |
|---|---|
| L'import des frais refuse des lignes « conteneur inconnu » | Le suivi des conteneurs n'a pas été importé avant : respecter l'ordre 1 → 4 |
| « Ce fichier a déjà été importé » | Normal : réimporter compterait chaque frais deux fois. Passer au fichier suivant |
| La facture reste « Déposée » sans lignes | Attendre 30 s et rafraîchir ; sinon le signaler (le lecteur tourne en arrière-plan) |
| Les chiffres ne sont pas ceux du guide | L'organisation contenait déjà des données : recommencer dans une organisation neuve. Les dates, elles, changent d'un kit à l'autre ; les montants non |
| L'audit dit qu'une facture est à relire | La facture n° 6 n'a pas été rejetée (étape 4) |

## Pour régénérer le kit

Les dates sont calculées par rapport au jour de génération (le journal couvre le dernier trimestre clos,
un conteneur vient d'arriver, un autre est en mer) ; le script refuse les quatre premiers jours d'un
trimestre. Il réécrit aussi l'encadré de dates en tête de ce guide. Avant de confier le kit à un nouveau
testeur, ou dès que ces dates sont loin :

```bash
python3 docs/demo/kit-testeur/generate_kit.py     # Google Chrome imprime les PDF
cd backend && uv run pytest tests/test_tester_kit.py
```

Les montants ne dépendent pas de la date ; `backend/tests/test_tester_kit.py` charge ces fichiers par
l'API, vérifie chaque chiffre cité ici, et que les fichiers sont bien ceux que le script écrit pour le
jour indiqué dans l'encadré.
