# FreightSight 🚢⚖️

**Landed Cost Calculator & Container Tracking SaaS for SMB Importers**

FreightSight calculates the *true cost* of imported goods by automatically allocating freight, customs, drayage, and demurrage costs across Purchase Orders — in real time, as your containers move across the ocean.

## The Problem

SMB importers lose **2-5% of margin** because they don't know their true landed costs until 30-45 days after goods arrive. They rely on manual Excel spreadsheets, miss demurrage deadlines, and price their products based on FOB values instead of fully-burdened costs.

## The Solution

FreightSight provides:
- **📦 CSV Import** — Bulk ingest Purchase Orders with container-to-PO allocation percentages
- **🚢 Container Tracking** — Real-time tracking via Vizion API with webhook-driven status updates
- **💰 Landed Cost Engine** — Automatic cost allocation across POs using configurable percentages
- **🤖 AI Invoice Parsing** — Drop a PDF freight invoice and let AI extract the costs (OCR)
- **📊 Control Tower Dashboard** — Bird's-eye view of all active shipments and their financial impact

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 16 (App Router), Tailwind CSS, Lucide Icons, Sonner |
| **Backend** | FastAPI, SQLAlchemy, Pydantic, Celery |
| **Database** | PostgreSQL 15 |
| **Queue** | Redis 7 |
| **Infra** | Docker Compose |
| **Tracking API** | Vizion API (webhook-driven) |

## Quick Start

```bash
# Clone the repo
git clone https://github.com/Pchambet/FreightSight.git
cd FreightSight

# Start the backend (API + DB + Redis + Celery)
docker compose up -d --build

# Start the frontend
cd frontend
npm install
npm run dev
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8001
- **API Docs (Swagger)**: http://localhost:8001/docs

## Data Model

```
Organization (1:N) → PurchaseOrder
Organization (1:N) → Container
Container (M:N) → PurchaseOrder  [via ContainerPurchaseOrder with allocation_%]
Container (1:N) → Cost
Container (1:1) → VizionTrackingMetadata
```

The key innovation is the **Many-to-Many** relationship between Containers and POs with an `allocation_percentage`, enabling accurate cost proration across split shipments.

## API Endpoints

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/containers` | List all containers |
| `POST` | `/api/containers` | Create container + subscribe to Vizion |
| `POST` | `/api/purchase-orders/upload` | Ingest POs from CSV |
| `POST` | `/api/containers/{id}/costs` | Add a cost to a container |
| `GET` | `/api/containers/{id}/landed-costs` | Calculate landed costs per PO |
| `POST` | `/api/containers/{id}/upload-invoice` | AI-parse a freight invoice (PDF) |
| `POST` | `/api/webhooks/vizion` | Receive Vizion tracking events |

## Strategy & Documentation

All strategic documents are in the [`/docs`](./docs) folder:

- **[01 — Audit & Skok Framework](./docs/01_audit_skok_framework.md)** — Project audit using Michael Skok's 4Us and BLAC & White frameworks
- **[02 — Go-To-Market Strategy](./docs/02_gtm_strategy.md)** — Target personas, LinkedIn outreach templates, competitive analysis, pricing
- **[03 — Technical Walkthrough](./docs/03_technical_walkthrough.md)** — Architecture, files, endpoints, test results

## License

MIT
