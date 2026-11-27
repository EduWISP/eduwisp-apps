# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from eduwisp_audit.models import Action, AuditEvent
from eduwisp_devices.models import Device, DeviceAssignment
from eduwisp_school.models import (
    Guardian,
    SchoolClass,
    SchoolLevel,
    SchoolYear,
    Section,
    Site,
    Student,
    StudentEnrollment,
    TeachingAssignment,
)
from eduwisp_users.models import Organization, Role
from rest_framework.test import APIClient

from eduwisp_apps.models import AppPolicyState, AppRequest, AppRule, RequestStatus
from eduwisp_apps.policy import provide
from eduwisp_apps.requests import add_opinion, decide, visible_requests

pytestmark = pytest.mark.django_db
User = get_user_model()
URL = "/api/protocol/v0/app-requests"


@pytest.fixture
def scuola():
    org = Organization.objects.create(name="Liceo Fittizio", slug="liceo")
    anno = SchoolYear.objects.create(
        organization=org,
        label="2026/2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 6, 30),
        is_current=True,
    )
    sede = Site.objects.create(organization=org, name="Sede", level=SchoolLevel.SECONDARIA_2)
    a = Section.objects.create(organization=org, site=sede, name="A")
    b = Section.objects.create(organization=org, site=sede, name="B")
    c1a = SchoolClass.objects.create(organization=org, school_year=anno, section=a, year_number=1)
    c1b = SchoolClass.objects.create(organization=org, school_year=anno, section=b, year_number=1)
    prof = User.objects.create_user("prof")
    altro_prof = User.objects.create_user("altro")
    TeachingAssignment.objects.create(organization=org, teacher=prof, school_year=anno, section=a)
    TeachingAssignment.objects.create(
        organization=org, teacher=altro_prof, school_year=anno, section=b
    )
    AppPolicyState.objects.create(organization=org, allowlist_enabled=True)

    def studente(nome, classe):
        s = Student.objects.create(organization=org, display_name=nome)
        StudentEnrollment.objects.create(organization=org, student=s, school_class=classe)
        return s

    anna, luca = studente("Rossi Anna", c1a), studente("Bianchi Luca", c1a)
    madre = User.objects.create_user("madre")
    Guardian.objects.create(organization=org, user=madre, student=anna, is_primary=True)

    def tablet(classe, stud=None):
        d = Device(organization=org, platform="android", agent_version="0.5", os_version="15")
        token = d.issue_token()
        d.save()
        DeviceAssignment.objects.create(
            organization=org, device=d, school_class=classe, student=stud
        )
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        return d, api

    return locals()


def chiedi(api, ident="org.example.dizionario", **extra):
    return api.post(URL, {"protocol_version": "0", "app": {"id": ident, **extra}}, format="json")


def ids(device):
    return {a["id"] for a in provide(device)["policy"]["apps"]["allowed"]}


def test_richiesta_parere_e_approvazione_solo_per_lo_studente(scuola):
    d_anna, api = scuola["tablet"](scuola["c1a"], scuola["anna"])
    d_luca, _ = scuola["tablet"](scuola["c1a"], scuola["luca"])
    r = chiedi(api, name="Dizionario di latino")
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert chiedi(api).status_code == 200  # una sola richiesta in attesa per app
    richiesta = AppRequest.objects.get()
    assert richiesta.school_class == scuola["c1a"]

    add_opinion(scuola["madre"], richiesta, "Le serve per i compiti di latino.")
    with pytest.raises(ValidationError):
        decide(scuola["prof"], richiesta, True, "  ")
    with pytest.raises(PermissionDenied):
        decide(scuola["altro_prof"], richiesta, True, "va bene")
    decide(scuola["prof"], richiesta, True, "Utile per le versioni.")

    richiesta.refresh_from_db()
    assert richiesta.status == RequestStatus.APPROVATA
    assert "org.example.dizionario" in ids(d_anna)
    assert "org.example.dizionario" not in ids(d_luca)  # solo per Anna
    azioni = set(AuditEvent.objects.values_list("action", flat=True))
    assert {Action.APP_REQUEST_DECISION, Action.APP_REQUEST_OPINION} <= azioni


def test_app_vietata_respinta_subito(scuola):
    _, api = scuola["tablet"](scuola["c1a"], scuola["anna"])
    r = chiedi(api, "com.zhiliaoapp.musically")
    assert r.status_code == 201 and r.json()["status"] == "rejected"
    richiesta = AppRequest.objects.get()
    assert richiesta.status == RequestStatus.RESPINTA and "vietata" in richiesta.decision_reason
    with pytest.raises(PermissionDenied):
        decide(scuola["prof"], richiesta, True, "proviamo")


def test_solo_dai_tablet_personali(scuola):
    _, api = scuola["tablet"](scuola["c1a"])
    r = chiedi(api)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_personal_device"


def test_app_gia_consentita(scuola):
    _, api = scuola["tablet"](scuola["c1a"], scuola["anna"])
    r = chiedi(api, "com.microsoft.teams")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert not AppRequest.objects.exists()


def test_chi_vede_le_richieste(scuola):
    _, api = scuola["tablet"](scuola["c1a"], scuola["anna"])
    chiedi(api)
    org = scuola["org"]
    assert visible_requests(scuola["prof"], Role.TEACHER, org).count() == 1
    assert visible_requests(scuola["altro_prof"], Role.TEACHER, org).count() == 0
    assert visible_requests(scuola["madre"], Role.GUARDIAN, org).count() == 1
    assert (
        visible_requests(User.objects.create_user("preside"), Role.SCHOOL_ADMIN, org).count() == 1
    )


def test_parere_solo_dei_familiari_e_motivato(scuola):
    _, api = scuola["tablet"](scuola["c1a"], scuola["anna"])
    chiedi(api)
    richiesta = AppRequest.objects.get()
    with pytest.raises(ValidationError):
        add_opinion(scuola["madre"], richiesta, "")
    with pytest.raises(PermissionDenied):
        add_opinion(User.objects.create_user("estraneo"), richiesta, "sì")
    # Maggiorenne senza consenso: la famiglia non dà pareri
    anna = scuola["anna"]
    anna.adult_on = date(2000, 1, 1)
    anna.save()
    with pytest.raises(PermissionDenied):
        add_opinion(scuola["madre"], richiesta, "sì")


def test_regola_per_studente_non_vale_per_l_istituto(scuola):
    from eduwisp_apps.models import App

    app = App.objects.create(
        organization=scuola["org"], name="Sintesi vocale", identifier="org.example.tts"
    )
    AppRule.objects.create(organization=scuola["org"], app=app, student=scuola["anna"])
    d_anna, _ = scuola["tablet"](scuola["c1a"], scuola["anna"])
    d_luca, _ = scuola["tablet"](scuola["c1a"], scuola["luca"])
    d_carrello, _ = scuola["tablet"](scuola["c1b"])
    assert "org.example.tts" in ids(d_anna)
    assert "org.example.tts" not in ids(d_luca)
    assert "org.example.tts" not in ids(d_carrello)


def test_regola_con_due_ambiti_rifiutata(scuola):
    from eduwisp_apps.models import App

    app = App.objects.create(organization=scuola["org"], name="X", identifier="org.example.x")
    r = AppRule(
        organization=scuola["org"], app=app, school_class=scuola["c1a"], student=scuola["anna"]
    )
    with pytest.raises(ValidationError):
        r.full_clean()
