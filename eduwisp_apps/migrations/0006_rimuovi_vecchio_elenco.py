# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("eduwisp_apps", "0005_converti_obbligatorie")]
    operations = [
        migrations.DeleteModel(
            name="RequiredApp",
        ),
    ]
