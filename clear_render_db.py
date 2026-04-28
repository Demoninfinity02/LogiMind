from dotenv import load_dotenv
load_dotenv()
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "control_tower.settings")
django.setup()

from tower.models import Shipment
Shipment.objects.filter(ai_explanation__contains="Decision explanation is temporarily unavailable").update(ai_explanation=None, ai_explained_at=None)
print("Cleared fallback explanations from the Render Postgres Database!")
