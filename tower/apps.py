import os
import threading
import time

from django.apps import AppConfig
from django.core.management import call_command


def _run_refresher_in_background():
    # Wait a few seconds to ensure the database and server are fully initialized
    time.sleep(10)
    # Run the refresh loop command directly in this thread
    call_command("refresh_live_data", loop=True, interval=180)


class TowerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tower"

    def ready(self) -> None:
        from . import signals  # noqa: F401

        # Only start the background thread if we are in the main server process.
        # (Prevents starting multiple loops during Django's auto-reload in dev mode).
        if os.environ.get("RUN_MAIN", None) == "true" or not os.environ.get("DEBUG") == "1":
            # Check if we already started it to avoid duplicate threads per worker
            if not getattr(self, "_refresher_started", False):
                self._refresher_started = True
                thread = threading.Thread(target=_run_refresher_in_background, daemon=True)
                thread.start()
