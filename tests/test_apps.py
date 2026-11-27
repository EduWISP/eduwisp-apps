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
from eduwisp_apps.unlocks import allowed_apps_for_class, end_unlock, unlock, unlockable_apps

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
        "firefox": app("Browser di prova", "org.example.browser"),
        "geogebra": app("Geometria di prova", "org.example.geometria"),
        "python": app("Python di prova", "org.example.python"),
        "wiki": app("Enciclopedia di prova", "org.example.enciclopedia"),
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
    """Solo le app del catalogo dell'istituto (quelle della piattaforma sono sempre presenti)."""
    return [
        a["id"]
        for a in provide(device)["policy"]["apps"]["allowed"]
        if a["id"].startswith("org.example.")
    ]


def test_livelli_si_sommano(liceo):
    assert ids(liceo["tablet"](liceo["c1a"])) == ["org.example.browser", "org.example.geometria"]
    assert ids(liceo["tablet"](liceo["c1e"])) == ["org.example.browser", "org.example.python"]


def test_elenco_non_attivo_restano_vietate_le_app_della_piattaforma(liceo):
    stato = AppPolicyState.objects.get(organization=liceo["org"])
    stato.allowlist_enabled = False
    stato.save()
    apps = provide(liceo["tablet"](liceo["c1a"]))["policy"]["apps"]
    assert apps["mode"] == "blocklist" and apps["allowed"] == []
    assert {"com.zhiliaoapp.musically", "com.snapchat.android", "org.torproject.torbrowser"} <= set(
        apps["blocked"]
    )


def test_app_della_piattaforma_consentite_e_vietate(liceo):
    apps = provide(liceo["tablet"](liceo["c1a"]))["policy"]["apps"]
    consentite = {a["id"] for a in apps["allowed"]}
    assert {"com.microsoft.teams", "it.maieuticallabs.mylim", "com.whatsapp"} <= consentite
    assert "com.instagram.android" in apps["blocked"]
    assert not consentite & set(apps["blocked"])


def test_app_vietata_non_entra_nel_catalogo(liceo):
    a = App(organization=liceo["org"], name="TikTok", identifier="com.zhiliaoapp.musically")
    with pytest.raises(ValidationError):
        a.full_clean()


def test_vietata_dopo_resta_bloccata(liceo):
    from eduwisp_apps.models import PlatformApp

    PlatformApp.objects.create(
        name="Browser di prova", identifier="org.example.browser", category="vpn", status="vietata"
    )
    apps = provide(liceo["tablet"](liceo["c1a"]))["policy"]["apps"]
    assert "org.example.browser" not in {a["id"] for a in apps["allowed"]}
    assert "org.example.browser" in apps["blocked"]


def test_app_obbligatorie_con_la_spunta(liceo):
    org = liceo["org"]
    mylim = App.objects.create(organization=org, name="MyLIM", identifier="it.maieuticallabs.mylim")
    AppRule.objects.create(organization=org, app=mylim, required=True)
    AppRule.objects.create(
        organization=org,
        app=liceo["app"]["python"],
        track=liceo["c1e"].section.track,
        required=True,
    )
    voci = {a["id"]: a for a in provide(liceo["tablet"](liceo["c1e"]))["policy"]["apps"]["allowed"]}
    assert voci["it.maieuticallabs.mylim"] == {
        "id": "it.maieuticallabs.mylim",
        "required": True,
        "name": "MyLIM",
    }
    assert voci["org.example.python"]["required"] is True
    voci_a = {
        a["id"]: a for a in provide(liceo["tablet"](liceo["c1a"]))["policy"]["apps"]["allowed"]
    }
    assert "required" not in voci_a.get("org.example.python", {})
    # Anche senza elenco attivo le obbligatorie arrivano al tablet
    AppPolicyState.objects.filter(organization=org).update(allowlist_enabled=False)
    apps = provide(liceo["tablet"](liceo["c1a"]))["policy"]["apps"]
    assert [a["id"] for a in apps["allowed"]] == ["it.maieuticallabs.mylim"]


@pytest.fixture
def con_apk(liceo, settings, tmp_path):
    from django.core.files.base import ContentFile

    settings.EDUWISP_PRIVATE_MEDIA_ROOT = tmp_path / "privato"
    settings.MEDIA_ROOT = tmp_path / "media"
    app = liceo["app"]["python"]
    app.apk.save("python.apk", ContentFile(b"PK finto apk"), save=False)
    app.icon.save("python.png", ContentFile(b"\x89PNG finto"), save=False)
    app.save()
    AppRule.objects.create(organization=liceo["org"], app=app, required=True)
    return app


def test_apk_e_logo_nella_policy(liceo, con_apk):
    import hashlib

    voce = next(
        a
        for a in provide(liceo["tablet"](liceo["c1a"]))["policy"]["apps"]["allowed"]
        if a["id"] == "org.example.python"
    )
    validate(
        "policy",
        {
            "protocol_version": "0",
            "policy_version": 1,
            "poll_interval_seconds": 900,
            "settings": {},
            "apps": {"mode": "allowlist", "allowed": [voce]},
        },
    )
    assert voce["install"]["sha256"] == hashlib.sha256(b"PK finto apk").hexdigest()
    assert voce["install"]["url"] == f"https://demo.example/api/protocol/v0/apps/{con_apk.pk}/apk"
    assert voce["icon"].startswith("https://demo.example/media/app/icone/")


def test_download_dell_apk_solo_per_i_dispositivi_giusti(liceo, con_apk):
    def client_per(device):
        token = device.issue_token()
        device.save()
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        return api

    url = f"/api/protocol/v0/apps/{con_apk.pk}/apk"
    assert APIClient().get(url).status_code == 401
    r = client_per(liceo["tablet"](liceo["c1a"])).get(url)
    assert r.status_code == 200 and b"".join(r.streaming_content) == b"PK finto apk"
    # Un dispositivo di un altro istituto non lo scarica
    altro = Organization.objects.create(name="Altro", slug="altro")
    d = Device(organization=altro, platform="android", agent_version="0.3", os_version="15")
    d.issue_token()
    d.save()
    assert client_per(d).get(url).status_code == 404
    # Senza spunta «obbligatoria» l'APK non si scarica
    AppRule.objects.filter(app=con_apk).update(required=False)
    assert client_per(liceo["tablet"](liceo["c1a"])).get(url).status_code == 404


def test_la_versione_cresce_a_ogni_modifica(liceo):
    d = liceo["tablet"](liceo["c1a"])
    v = provide(d)["version"]
    AppRule.objects.create(organization=liceo["org"], app=liceo["app"]["wiki"])
    assert provide(d)["version"] > v


def test_sblocco_del_docente_con_scadenza_e_registro(liceo):
    d = liceo["tablet"](liceo["c1a"])
    s = unlock(liceo["docente"], liceo["c1a"], liceo["app"]["wiki"], 60)
    voce = [
        a for a in provide(d)["policy"]["apps"]["allowed"] if a["id"] == "org.example.enciclopedia"
    ][0]
    assert voce["until"] == s.ends_at.isoformat()
    assert AuditEvent.objects.filter(action=Action.APP_UNLOCK).count() == 1
    # Solo per quella classe
    assert "org.example.enciclopedia" not in ids(liceo["tablet"](liceo["c1e"]))
    end_unlock(liceo["docente"], s)
    assert "org.example.enciclopedia" not in ids(d)
    assert AuditEvent.objects.filter(action=Action.APP_UNLOCK_END).count() == 1


def test_sblocco_scaduto_non_conta(liceo):
    d = liceo["tablet"](liceo["c1a"])
    s = unlock(liceo["docente"], liceo["c1a"], liceo["app"]["wiki"], 30)
    s.starts_at -= timedelta(hours=1)
    s.ends_at = timezone.now() - timedelta(minutes=1)
    s.save()
    assert "org.example.enciclopedia" not in ids(d)


def test_docente_solo_nelle_sue_classi(liceo):
    with pytest.raises(PermissionDenied):
        unlock(liceo["docente"], liceo["c1e"], liceo["app"]["wiki"], 60)
    assert not AuditEvent.objects.exists()


def test_al_massimo_quattro_ore(liceo):
    with pytest.raises(ValidationError):
        unlock(liceo["docente"], liceo["c1a"], liceo["app"]["wiki"], 300)


def test_app_sbloccabili_escludono_quelle_gia_consentite(liceo):
    nomi = {a.name for a in unlockable_apps(liceo["c1a"])}
    assert nomi == {"Python di prova", "Enciclopedia di prova"}
    consentite = {a.name for a in allowed_apps_for_class(liceo["c1a"])}
    assert {
        "Browser di prova",
        "Geometria di prova",
        "Microsoft Teams",
        "MyLIM (Loescher)",
    } <= consentite
    assert "TikTok" not in consentite


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
    assert {"id": "org.example.browser"} in policy["apps"]["allowed"]
