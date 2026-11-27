# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Download degli APK per l'installazione silenziosa (ADR-0020)."""

from django.http import FileResponse
from eduwisp_devices.api.views import ProtocolView, error

from .models import App, PlatformApp, PlatformStatus
from .policy import classe_del_dispositivo, required_apps


class ApkView(ProtocolView):
    """Solo i dispositivi dell'istituto, e solo per le app obbligatorie per loro."""

    def get(self, request, pk):
        device, err = self.authenticated_device(request)
        if err:
            return err
        app = App.objects.filter(pk=pk, organization=device.organization).first()
        if app is None or not app.apk:
            return error("not_found", "APK non disponibile.", 404)
        if app.identifier not in required_apps(device, classe_del_dispositivo(device)):
            return error("not_found", "APK non disponibile.", 404)
        if PlatformApp.objects.filter(
            platform=app.platform, identifier=app.identifier, status=PlatformStatus.VIETATA
        ).exists():
            return error("not_found", "APK non disponibile.", 404)
        risposta = FileResponse(
            app.apk.open("rb"),
            as_attachment=True,
            filename=f"{app.identifier}.apk",
            content_type="application/vnd.android.package-archive",
        )
        risposta["X-Content-SHA256"] = app.apk_sha256
        return risposta
