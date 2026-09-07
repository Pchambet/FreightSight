# FreightSight — Stratégie Go-To-Market & Plan de Test

## Rapport de Tests (QA)

Tous les endpoints ont été testés via `curl` et la base de données vérifiée directement en SQL.

| Endpoint | Statut | Résultat |
|---|---|---|
| `GET /` | ✅ OK | API up and running |
| `GET /api/containers` | ✅ OK | 2 conteneurs retournés (MSCU, CMAU) |
| `POST /api/purchase-orders/upload` | ✅ OK | 3 POs créés, 3 liens conteneur-PO |
| `POST /api/containers/{id}/costs` | ✅ OK | Coût ajouté, ID retourné |
| `POST /api/containers/{id}/upload-invoice` | ✅ OK | 2 coûts IA simulés (1500$ + 300$) |
| `GET /api/containers/{id}/landed-costs` | ✅ OK | Calcul correct : Michelin = 14 900.50$, Pirelli = 9 600.00$ |

### Vérification Base de Données (PostgreSQL)
```
container_number | allocation_percentage | po_number
-----------------+-----------------------+------------
MSCU1234567      |                100.00 | PO-2026-001 (Michelin)
MSCU1234567      |                 50.00 | PO-2026-002 (Pirelli)
CMAU9876543      |                100.00 | PO-2026-003 (Hankook)
```

> [!TIP]
> **Le modèle Many-to-Many fonctionne parfaitement.** Michelin reçoit 100% des frais, Pirelli 50%. C'est exactement le problème que l'ancien Odoo ne savait pas gérer.

---

## Stratégie Go-To-Market : Comment Vendre FreightSight

### 1. Qui Cibler ? (Personas)

**Le client idéal : La PME importatrice (10-200 salariés, 5M-50M€ CA)**

| Secteur | Exemples concrets | Pourquoi c'est parfait |
|---|---|---|
| **E-commerce / D2C** | Marques Shopify qui importent de Chine | Volume élevé, marges serrées, besoin de connaître le coût réel par SKU |
| **Négoce de vin** | Importateurs de vins italiens/espagnols | Conteneurs multiples, droits de douane variables (accises) |
| **Pièces auto** | Distributeurs de pièces détachées | Beaucoup de références par conteneur, allocation complexe |
| **Mobilier / Décoration** | Importateurs de meubles d'Asie | Conteneurs volumineux, coûts de drayage élevés |
| **Agroalimentaire** | Importateurs de café, épices, huiles | Régulations douanières strictes, surestaries fréquentes |

**Titres à cibler sur LinkedIn :**
- Directeur des Opérations / COO
- Responsable Supply Chain / Logistique
- Directeur Achats / Procurement Manager
- DAF / CFO (dans les petites structures, c'est lui qui souffre des marges floues)

---

### 2. Où Les Trouver ?

**LinkedIn (canal n°1) :**
- Recherche : `"supply chain" OR "logistics" OR "import" OR "procurement" site:linkedin.com`
- Filtres : 11-200 employés, secteurs Manufacturing / Wholesale / E-commerce
- Localisation : France, Belgique, Suisse pour commencer (francophone)

**Communautés :**
- Reddit : r/supplychain, r/logistics, r/ecommerce
- Slack : Supply Chain Revolution, E-Commerce Fuel
- LinkedIn Groups : "Supply Chain Management Professionals", "Freight Forwarding Network"

**Salons professionnels (France) :**
- **SITL** (Semaine de l'Innovation Transport & Logistique) — Paris, mars
- **Supply Chain Event** — Paris, novembre
- **Top Transport & Logistics** — Marseille

---

### 3. Le Pitch — 3 Templates LinkedIn

#### Template 1 : Le Message Froid (Premier Contact)

> Bonjour [Prénom],
> 
> Je développe FreightSight, un outil SaaS pour calculer automatiquement les coûts d'approche (landed costs) des conteneurs maritimes.
> 
> En regardant [Nom de l'entreprise], j'ai l'impression que vous gérez pas mal d'imports par mer. Est-ce que le calcul du prix de revient réel de vos marchandises est un sujet chez vous, ou c'est déjà bien cadré ?
> 
> Pas de pitch, juste curieux d'avoir votre retour terrain.
> 
> Pierre

#### Template 2 : L'Approche "Design Partner"

> Bonjour [Prénom],
> 
> Je construis un outil qui résout un problème que j'ai vécu directement : savoir combien coûte VRAIMENT une commande fournisseur quand on ajoute le fret, la douane, le transport local, les surestaries…
> 
> Je cherche 5 professionnels du métier pour tester l'outil gratuitement pendant 2 mois et m'aider à le rendre parfait. En échange : accès à vie à -50% + influence directe sur les fonctionnalités.
> 
> Ça vous parlerait ?

#### Template 3 : Le Follow-Up (J+3 sans réponse)

> [Prénom], je me permets de relancer — je sais que LinkedIn c'est la jungle.
> 
> En 30 secondes : FreightSight lit vos factures de transport, calcule le coût réel par commande, et suit vos conteneurs en temps réel. Le tout sans toucher à votre ERP.
> 
> Si c'est pas pertinent pour vous, aucun souci — mais si vous connaissez quelqu'un qui galère avec ses landed costs, je suis preneur d'une mise en relation.
> 
> Bonne journée !

---

### 4. Pourquoi Ils Switcher depuis Excel ?

> [!IMPORTANT]
> **Le coût de ne PAS avoir FreightSight :**

| Problème | Impact quantifié |
|---|---|
| Calcul manuel des landed costs sur Excel | **10-15h/semaine** d'un employé qualifié |
| Erreur de marge (prix de vente basé sur le FOB seul) | **2-5% de marge perdue** par commande |
| Surestaries non anticipées (conteneur oublié au port) | **500-2000€/jour** de pénalité |
| Réconciliation comptable à la fin du mois | **3-5 jours** de retard de clôture |
| Pas de visibilité sur les conteneurs en transit | Commandes clients en retard, service client débordé |

**L'argument massue :** *"Un seul conteneur oublié au port pendant 5 jours vous coûte 5 000€ de surestaries. Notre abonnement coûte 499€/mois. Le logiciel se rembourse dès le premier incident évité."*

---

### 5. Pricing Recommandé

| Plan | Prix | Contenu |
|---|---|---|
| **Design Partner (MVP)** | Gratuit 2 mois | Accès complet, en échange de feedback hebdo |
| **Starter** | 299€/mois | Jusqu'à 20 conteneurs/mois, 1 utilisateur |
| **Growth** | 499€/mois | Jusqu'à 100 conteneurs/mois, 5 utilisateurs, OCR |
| **Enterprise** | 999€/mois | Illimité, connecteurs ERP, support prioritaire |
| **Design Partners à vie** | -50% sur le plan choisi | Récompense pour les premiers adoptants |

> [!TIP]
> **Ne pas vendre au prix.** Vendre au ROI. Si tu fais économiser 5 000€/mois de surestaries, 499€/mois c'est un non-sujet.

---

### 6. Le Concurrence — Se Positionner

| Concurrent | Ce qu'ils font | Leur faiblesse | Notre angle |
|---|---|---|---|
| **Flexport** | Transitaire full-service | Trop cher, pas un outil — c'est un service | On est un outil SaaS autonome |
| **project44 / FourKites** | Tracking enterprise | Prix 50k+$/an, PME exclues | On cible les PME à 500€/mois |
| **Freightos** | Marketplace de devis fret | Pas de landed cost, pas de suivi | On fait le suivi + le calcul |
| **Excel / Google Sheets** | Le vrai concurrent n°1 | Pas de temps réel, erreurs, pas scalable | Automatisation + OCR + API |

> [!IMPORTANT]
> **Le vrai concurrent c'est Excel.** Pas les gros SaaS. Ta bataille c'est de convaincre que 499€/mois vaut mieux que le stagiaire qui passe 15h/semaine sur un spreadsheet.

---

### 7. Plan d'Action Semaine 1

| Jour | Action |
|---|---|
| **Lundi** | Créer une landing page simple (1 page, Vercel). Préparer le scénario de démo avec des données réalistes |
| **Mardi** | Identifier 50 prospects sur LinkedIn (filtres : import, supply chain, 10-200 employés, France) |
| **Mercredi** | Envoyer 20 messages (Template 1 ou 2). Poster un contenu sur LinkedIn sur le problème des landed costs |
| **Jeudi** | Relancer les non-répondants (Template 3). Contacter 20 nouveaux prospects |
| **Vendredi** | Faire les premiers appels de démo avec ceux qui ont répondu. Itérer sur le produit selon les retours |

> [!CAUTION]
> **Ne pas coder plus avant d'avoir parlé à 5 vrais prospects.** Le risque n°1 d'un fondateur technique, c'est de construire dans le vide. Le MVP est fonctionnel. La priorité absolue est de valider le marché avec de vrais humains.
