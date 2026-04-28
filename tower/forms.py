from django import forms

from .models import Shipment


class ShipmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control form-control-sm"

    class Meta:
        model = Shipment
        fields = [
            "reference",
            "origin",
            "destination",
            "mode",
            "priority",
            "status",
            "base_eta",
            "base_transit_hours",
            "cost_level",
            "budget_usd",
            "expected_profit_usd",
        ]
