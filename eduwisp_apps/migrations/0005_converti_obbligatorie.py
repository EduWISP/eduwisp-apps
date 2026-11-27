# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Le vecchie app obbligatorie diventano app consentite con la spunta (ADR-0020).

Migrazione separata: su PostgreSQL non si possono modificare dati e schema nella stessa
transazione quando ci sono vincoli differiti.
"""

from django.db import migrations


def converti_obbligatorie(apps, schema_editor):
    """Le vecchie app obbligatorie diventano app consentite con la spunta (ADR-0020)."""
    RequiredApp = apps.get_model("eduwisp_apps", "RequiredApp")
    App = apps.get_model("eduwisp_apps", "App")
    AppRule = apps.get_model("eduwisp_apps", "AppRule")
    for r in RequiredApp.objects.all():
        app, _ = App.objects.get_or_create(
            organization_id=r.organization_id,
            platform=r.platform,
            identifier=r.identifier,
            defaults={"name": r.name},
        )
        regola = AppRule.objects.filter(
            app=app, track_id=r.track_id, school_class_id=r.school_class_id
        ).first()
        if regola is None:
            regola = AppRule(
                organization_id=r.organization_id,
                app=app,
                track_id=r.track_id,
                school_class_id=r.school_class_id,
            )
        regola.required = True
        regola.save()


class Migration(migrations.Migration):
    dependencies = [("eduwisp_apps", "0004_elenco_unico")]
    operations = [migrations.RunPython(converti_obbligatorie, migrations.RunPython.noop)]
