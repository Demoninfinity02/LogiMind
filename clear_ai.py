import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "control_tower.settings")
django.setup()

from tower.models import Shipment
Shipment.objects.update(ai_explanation=None, ai_explained_at=None)
print("Cleared AI explanations again!")
