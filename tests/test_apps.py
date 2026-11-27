# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from eduwisp_audit.models import Action, AuditEvent
from eduwisp_devices.models import Device, DeviceAssignment
from eduwisp_protocol import validate
from eduwisp_school.models import (
    SchoolClass,
    SchoolLevel,
    SchoolYear,
    Section,
    Site,
    TeachingAssignment,
    Track,
)
from eduwisp_users.models import Organization
from rest_framework.test import APIClient

from eduwisp_apps.models import App, AppPolicyState, AppRule
from eduwisp_apps.policy import provide
from eduwisp_apps.unlocks import end_unlock, unlock, unlockable_apps

pytestmark = pytest.mark.django_db


@pytest.fixture
def liceo():
    org = Organization.objects.create(name="Liceo Fittizio", slug="liceo")
    anno = SchoolYear.objects.create(
        organization=org,
        label="2026/2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 6, 30),
        is_current=True,
    )
    sede = Site.objects.create(organization=org, name="Sede", level=SchoolLevel.SECONDARIA_2)
    sa = Track.objects.create(organization=org, site=sede, name="Scienze applicate")
    a = Section.objects.create(organization=org, site=sede, name="A")
    e = Section.objects.create(organization=org, site=sede, name="E", track=sa)
    c1a = SchoolClass.objects.create(organization=org, school_year=anno, section=a, year_number=1)
    c1e = SchoolClass.objects.create(organization=org, school_year=anno, section=e, year_number=1)
    docente = get_user_model().objects.create_user("prof")
    TeachingAssignment.objects.create(
        organization=org, teacher=docente, school_year=anno, section=a
    )

    def app(nome, ident):
        return App.objects.create(organization=org, name=nome, identifier=ident)

    catalogo = {
        "firefox": app("Firefox", "org.mozilla.firefox"),
        "geogebra": app("GeoGebra", "org.geogebra.android"),
        "python": app("Pydroid", "ru.iiec.pydroid3"),
        "wiki": app("Wikipedia", "org.wikipedia"),
    }
    AppRule.objects.create(organization=org, app=catalogo["firefox"])
    AppRule.objects.create(organization=org, app=catalogo["python"], track=sa)
    AppRule.objects.create(organization=org, app=catalogo["geogebra"], school_class=c1a)
    AppPolicyState.objects.update_or_create(organization=org, defaults={"allowlist_enabled": True})

    def tablet(classe):
        d = Device(organization=org, platform="android", agent_version="0.3", os_version="15")
        d.issue_token()
        d.save()
        DeviceAssignment.objects.create(organization=org, device=d, school_class=classe)
        return d

    return {
        "org": org,
        "c1a": c1a,
        "c1e": c1e,
        "docente": docente,
        "app": catalogo,
        "tablet": tablet,
    }


def ids(device):
    return [a["id"] for a in provide(device)["policy"]["apps"]["allowed"]]


def test_livelli_si_sommano(liceo):
    assert ids(liceo["tablet"](liceo["c1a"])) == ["org.geogebra.android", "org.mozilla.firefox"]
    assert ids(liceo["tablet"](liceo["c1e"])) == ["org.mozilla.firefox", "ru.iiec.pydroid3"]


def test_elenco_non_attivo_nessun_contributo(liceo):
    stato = AppPolicyState.objects.get(organization=liceo["org"])
    stato.allowlist_enabled = False
    stato.save()
    assert provide(liceo["tablet"](liceo["c1a"])) is None


def test_la_versione_cresce_a_ogni_modifica(liceo):
    d = liceo["tablet"](liceo["c1a"])
    v = provide(d)["version"]
    AppRule.objects.create(organization=liceo["org"], app=liceo["app"]["wiki"])
    assert provide(d)["version"] > v


def test_sblocco_del_docente_con_scadenza_e_registro(liceo):
    d = liceo["tablet"](liceo["c1a"])
    s = unlock(liceo["docente"], liceo["c1a"], liceo["app"]["wiki"], 60)
    voce = [a for a in provide(d)["policy"]["apps"]["allowed"] if a["id"] == "org.wikipedia"][0]
    assert voce["until"] == s.ends_at.isoformat()
    assert AuditEvent.objects.filter(action=Action.APP_UNLOCK).count() == 1
    # Solo per quella classe
    assert "org.wikipedia" not in ids(liceo["tablet"](liceo["c1e"]))
    end_unlock(liceo["docente"], s)
    assert "org.wikipedia" not in ids(d)
    assert AuditEvent.objects.filter(action=Action.APP_UNLOCK_END).count() == 1


def test_sblocco_scaduto_non_conta(liceo):
    d = liceo["tablet"](liceo["c1a"])
    s = unlock(liceo["docente"], liceo["c1a"], liceo["app"]["wiki"], 30)
    s.starts_at -= timedelta(hours=1)
    s.ends_at = timezone.now() - timedelta(minutes=1)
    s.save()
    assert "org.wikipedia" not in ids(d)


def test_docente_solo_nelle_sue_classi(liceo):
    with pytest.raises(PermissionDenied):
        unlock(liceo["docente"], liceo["c1e"], liceo["app"]["wiki"], 60)
    assert not AuditEvent.objects.exists()


def test_al_massimo_quattro_ore(liceo):
    with pytest.raises(ValidationError):
        unlock(liceo["docente"], liceo["c1a"], liceo["app"]["wiki"], 300)


def test_app_sbloccabili_escludono_quelle_gia_consentite(liceo):
    nomi = {a.name for a in unlockable_apps(liceo["c1a"])}
    assert nomi == {"Pydroid", "Wikipedia"}


def test_regola_con_indirizzo_e_classe_rifiutata(liceo):
    r = AppRule(
        organization=liceo["org"],
        app=liceo["app"]["wiki"],
        track=liceo["c1e"].section.track,
        school_class=liceo["c1e"],
    )
    with pytest.raises(ValidationError):
        r.full_clean()


def test_policy_dal_protocollo(liceo):
    d = liceo["tablet"](liceo["c1a"])
    token = d.issue_token()
    d.save()
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    policy = api.get("/api/protocol/v0/policy").json()
    validate("policy", policy)
    assert policy["apps"]["mode"] == "allowlist"
    assert {"id": "org.mozilla.firefox"} in policy["apps"]["allowed"]
