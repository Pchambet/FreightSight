import os
import csv
import io
import httpx
import logging
from fastapi import FastAPI, Depends, Request, BackgroundTasks, UploadFile, File, Form, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import models
import schemas
from database import engine, get_db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Création des tables dans la base de données
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FreightSight API", description="Landed Cost & Container Tracking MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for MVP local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


VIZION_API_KEY = os.getenv("VIZION_API_KEY", "DEMO_KEY")
VIZION_API_URL = os.getenv("VIZION_API_URL", "https://prod.api.vizionapi.com")

@app.get("/")
def read_root():
    return {"message": "Welcome to FreightSight API. Services are up and running."}

def process_vizion_event(payload: schemas.WebhookPayload, db: Session):
    logger.info(f"Processing background Vizion event: {payload}")
    try:
        if payload.container_id:
            metadata = db.query(models.VizionTrackingMetadata).filter(
                models.VizionTrackingMetadata.vizion_reference_id == payload.container_id
            ).first()
            if metadata:
                metadata.last_event_code = payload.event
                db.commit()
                logger.info(f"Updated metadata for container ID {metadata.container_id}")
    except SQLAlchemyError as e:
        logger.error(f"Database error while processing Vizion event: {str(e)}")
        db.rollback()

@app.post("/api/webhooks/vizion")
async def vizion_webhook(payload: schemas.WebhookPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    background_tasks.add_task(process_vizion_event, payload, db)
    return {"status": "received", "message": "Event queued for processing."}

@app.post("/api/containers", response_model=schemas.ContainerResponse, status_code=status.HTTP_201_CREATED)
async def create_container(container: schemas.ContainerCreate, db: Session = Depends(get_db)):
    """Crée un conteneur et déclenche l'abonnement API Vizion"""
    
    try:
        # Vérifier si le conteneur existe déjà
        existing = db.query(models.Container).filter(
            models.Container.container_number == container.container_number,
            models.Container.org_id == container.org_id
        ).first()
        
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Container already exists for this organization")

        # Création en DB
        db_container = models.Container(
            org_id=container.org_id,
            container_number=container.container_number,
            carrier=container.carrier
        )
        db.add(db_container)
        db.flush() # Flush to get ID
        
        # Simulation d'appel API Vizion (remplacer par vrai appel httpx si API KEY valide)
        # TODO: Implement actual Vizion API call here using httpx
        vizion_ref_id = f"VIZ_{db_container.container_number}"
        
        vizion_metadata = models.VizionTrackingMetadata(
            container_id=db_container.id,
            vizion_reference_id=vizion_ref_id
        )
        db.add(vizion_metadata)
        db.commit()
        db.refresh(db_container)
        
        return schemas.ContainerResponse.model_validate({
            "id": db_container.id,
            "container_number": db_container.container_number,
            "carrier": db_container.carrier,
            "status": db_container.status.value,
            "vizion_reference_id": vizion_ref_id
        })
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during container creation: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error occurred")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error during container creation: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")

@app.post("/api/purchase-orders/upload")
async def upload_po_csv(org_id: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Ingère un CSV de Bons de Commande et les lie aux Conteneurs"""
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")
    
    content = await file.read()
    decoded_content = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded_content))
    
    rows_processed = 0
    containers_linked = 0
    
    try:
        # Vérification et création de l'Organisation "dummy" pour le MVP
        org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
        if not org:
            org = models.Organization(id=org_id, name="MVP Organization")
            db.add(org)
            db.commit()

        for line_num, row in enumerate(reader, start=2):
            po_number = row.get("po_number")
            supplier_name = row.get("supplier_name", "")
            
            try:
                total_value = float(row.get("total_value", 0) or 0)
            except ValueError:
                logger.warning(f"Invalid total_value at line {line_num}. Defaulting to 0.")
                total_value = 0.0

            container_number = row.get("container_number")
            
            if not po_number:
                logger.warning(f"Skipping line {line_num}: missing po_number")
                continue
                
            # Cherche le PO ou le crée
            po = db.query(models.PurchaseOrder).filter(
                models.PurchaseOrder.po_number == po_number,
                models.PurchaseOrder.org_id == org_id
            ).first()
            
            if not po:
                po = models.PurchaseOrder(
                    org_id=org_id,
                    po_number=po_number,
                    supplier_name=supplier_name,
                    total_value=total_value
                )
                db.add(po)
                db.flush() # flush pour obtenir po.id
            
            # Si un conteneur est précisé dans le CSV
            if container_number:
                container = db.query(models.Container).filter(
                    models.Container.container_number == container_number,
                    models.Container.org_id == org_id
                ).first()
                
                if not container:
                    # On le crée à la volée s'il n'existe pas
                    container = models.Container(
                        org_id=org_id,
                        container_number=container_number
                    )
                    db.add(container)
                    db.flush()
                
                # Vérifie si le lien existe déjà
                link = db.query(models.ContainerPurchaseOrder).filter(
                    models.ContainerPurchaseOrder.container_id == container.id,
                    models.ContainerPurchaseOrder.po_id == po.id
                ).first()
                
                if not link:
                    try:
                        alloc = float(row.get("allocation_percentage", 100.0) or 100.0)
                    except ValueError:
                        alloc = 100.0
                    new_link = models.ContainerPurchaseOrder(
                        container_id=container.id,
                        po_id=po.id,
                        allocation_percentage=alloc
                    )
                    db.add(new_link)
                    containers_linked += 1
            
            rows_processed += 1
            
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error processing CSV: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error occurred during CSV processing")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error processing CSV: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"CSV processing failed: {str(e)}")
        
    return {
        "status": "success",
        "rows_processed": rows_processed,
        "containers_linked": containers_linked
    }

@app.get("/api/containers", response_model=list[schemas.ContainerResponse])
async def get_containers(db: Session = Depends(get_db)):
    try:
        containers = db.query(models.Container).all()
        result = []
        for c in containers:
            vizion_ref = c.vizion_metadata.vizion_reference_id if c.vizion_metadata else None
            result.append(schemas.ContainerResponse.model_validate({
                "id": c.id,
                "container_number": c.container_number,
                "carrier": c.carrier,
                "status": c.status.value,
                "vizion_reference_id": vizion_ref
            }))
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error getting containers: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error occurred")

@app.post("/api/containers/{container_id}/costs", status_code=status.HTTP_201_CREATED)
async def add_cost(container_id: str, cost: schemas.CostCreate, db: Session = Depends(get_db)):
    try:
        try:
            cost_type_enum = models.CostType(cost.cost_type)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cost_type: {cost.cost_type}")
            
        db_cost = models.Cost(
            container_id=container_id,
            cost_type=cost_type_enum,
            amount=cost.amount,
            currency=cost.currency
        )
        db.add(db_cost)
        db.commit()
        return {"status": "success", "cost_id": db_cost.id}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding cost: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error occurred")

@app.post("/api/containers/{container_id}/upload-invoice")
async def upload_invoice(container_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Simulates AI OCR extraction of costs from an invoice and saves them."""
    try:
        container = db.query(models.Container).filter(models.Container.id == container_id).first()
        if not container:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Container not found")
        
        logger.info(f"Simulating AI OCR on file: {file.filename}")
        simulated_costs = [
            {"cost_type": models.CostType.OCEAN_FREIGHT, "amount": 1500.0, "currency": "USD"},
            {"cost_type": models.CostType.CUSTOMS, "amount": 300.0, "currency": "USD"}
        ]
        
        saved_costs = []
        for cost_data in simulated_costs:
            db_cost = models.Cost(
                container_id=container_id,
                cost_type=cost_data["cost_type"],
                amount=cost_data["amount"],
                currency=cost_data["currency"]
            )
            db.add(db_cost)
            saved_costs.append(db_cost)
            
        db.commit()
        
        return {
            "status": "success",
            "message": "Invoice processed and costs extracted successfully",
            "extracted_costs": [
                {
                    "cost_type": c.cost_type.value,
                    "amount": float(c.amount),
                    "currency": c.currency
                } for c in saved_costs
            ]
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during invoice upload: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error occurred")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error during invoice upload: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")

@app.get("/api/containers/{container_id}/landed-costs", response_model=schemas.LandedCostResponse)
async def get_landed_costs(container_id: str, db: Session = Depends(get_db)):
    try:
        container = db.query(models.Container).filter(models.Container.id == container_id).first()
        if not container:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Container not found")

        costs = db.query(models.Cost).filter(models.Cost.container_id == container_id).all()
        total_additional_costs = sum(float(c.amount) for c in costs)
        
        links = db.query(models.ContainerPurchaseOrder).filter(models.ContainerPurchaseOrder.container_id == container_id).all()
        
        po_breakdown = []
        for link in links:
            po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == link.po_id).first()
            if po:
                # MVP Logic: allocating costs strictly based on allocation_percentage
                # In a real app, it might be prorated by weight/volume/value
                allocated_cost = total_additional_costs * (float(link.allocation_percentage) / 100.0)
                true_landed_cost = float(po.total_value) + allocated_cost
                
                po_breakdown.append({
                    "po_number": po.po_number,
                    "supplier_name": po.supplier_name,
                    "fob_value": float(po.total_value),
                    "allocation_pct": float(link.allocation_percentage),
                    "allocated_freight_and_duty": allocated_cost,
                    "true_landed_cost": true_landed_cost
                })

        return schemas.LandedCostResponse(
            container_number=container.container_number,
            total_additional_costs=total_additional_costs,
            breakdown=po_breakdown,
            raw_costs=[{"type": c.cost_type.value if hasattr(c.cost_type, "value") else c.cost_type, "amount": float(c.amount)} for c in costs]
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error calculating landed costs: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error occurred")


