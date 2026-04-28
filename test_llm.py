from dotenv import load_dotenv
load_dotenv()
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "control_tower.settings")
django.setup()

from tower.models import Shipment
from tower.services.llm import get_gemini_explanation

shipment = Shipment.objects.first()
if not shipment:
    print("No shipments found.")
else:
    context = {
        "mode": shipment.mode,
        "risk": 0.9,
        "delay_hours": 1.5,
        "top_factors": {"weather": "Clear", "traffic": "Heavy", "disruptions": "None"},
        "alternative_mode": "None",
        "constraint": "Cost constraint: Low",
        "final_decision": "Continue current mode."
    }
    try:
        explanation = get_gemini_explanation(context)
        print("SUCCESS:", explanation)
    except Exception as e:
        print("ERROR:", str(e))
        import traceback
        traceback.print_exc()
