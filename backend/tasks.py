import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("freightsight_tasks", broker=REDIS_URL)

@celery_app.task
def recalculate_landed_costs(po_id: str):
    # Logique complexe de recalcul répartissant les coûts du conteneur sur le PO
    print(f"Recalculating landed costs for PO: {po_id}")
    return True
