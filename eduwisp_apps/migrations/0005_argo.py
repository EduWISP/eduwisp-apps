# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""App di Argo (registro elettronico) consentite in tutti gli istituti; pacchetti verificati."""

from django.db import migrations
from django.db.models import F

ARGO = [
    ("didUP - Famiglia (Argo)", "it.argosoft.didup.famiglia.new"),
    ("didUP (Argo)", "it.argosoft.didup"),
]


def carica(apps, schema_editor):
    PlatformApp = apps.get_model("eduwisp_apps", "PlatformApp")
    Versione = apps.get_model("eduwisp_apps", "PlatformCatalogVersion")
    for nome, pacchetto in ARGO:
        PlatformApp.objects.update_or_create(
            platform="android",
            identifier=pacchetto,
            defaults={"name": nome, "category": "istruzione", "status": "consentita"},
        )
    Versione.objects.get_or_create(pk=1)
    Versione.objects.filter(pk=1).update(version=F("version") + 1)


class Migration(migrations.Migration):
    dependencies = [("eduwisp_apps", "0004_elenco_unico")]
    operations = [migrations.RunPython(carica, migrations.RunPython.noop)]
