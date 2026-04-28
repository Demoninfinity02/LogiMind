from django.apps import AppConfig


class TowerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tower"

    def ready(self) -> None:
        from . import signals  # noqa: F401
