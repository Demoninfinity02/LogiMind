from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("shipments/create/", views.create_shipment, name="create_shipment"),
    path("live-updates/", views.live_updates, name="live_updates"),
]
