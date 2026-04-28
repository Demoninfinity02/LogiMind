import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "control_tower.settings")
django.setup()
from tower.models import Shipment
for s in Shipment.objects.filter(ai_explanation__isnull=False):
    print(f"[{s.reference}] -> {s.ai_explanation}")
