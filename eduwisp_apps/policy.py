# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Contributo alla policy del dispositivo (EDUWISP_POLICY_PROVIDERS in eduwisp-devices).

- ``blocked``: app vietate dalla piattaforma, sempre (anche senza elenco di app consentite).
- ``allowed``: con l'elenco attivo, catalogo della piattaforma + regole dell'istituto +
  sblocchi temporanei della classe; senza elenco, solo le app obbligatorie.
- ``required``: app obbligatorie decise dall'istituto (ADR-0019).
"""

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from eduwisp_devices.models import DeviceAssignment

from .models import (
    AppPolicyState,
    AppRule,
    PlatformApp,
    PlatformCatalogVersion,
    PlatformStatus,
    TemporaryUnlock,
)


def classe_del_dispositivo(device):
    a = (
        DeviceAssignment.objects.filter(device=device, ended_at__isnull=True)
        .select_related("school_class__section")
        .first()
    )
    return a.school_class if a else None


def studente_del_dispositivo(device):
    """Lo studente a cui il tablet è affidato (solo tablet personali), oppure None."""
    a = (
        DeviceAssignment.objects.filter(device=device, ended_at__isnull=True, student__isnull=False)
        .select_related("student")
        .first()
    )
    return a.student if a else None


def ambito(classe, studente=None):
    """Regole valide per il tablet: istituto, indirizzo e classe, e quelle del suo studente.

    Una regola d'istituto non ha né indirizzo, né classe, né studente: le regole per un
    singolo studente non valgono mai per gli altri (ADR-0021).
    """
    q = Q(track__isnull=True, school_class__isnull=True, student__isnull=True)
    if classe is not None:
        q |= Q(school_class=classe)
        if classe.section.track_id:
            q |= Q(track_id=classe.section.track_id)
    if studente is not None:
        q |= Q(student=studente)
    return q


def _piattaforma(device, status):
    return set(
        PlatformApp.objects.filter(platform=device.platform, status=status).values_list(
            "identifier", flat=True
        )
    )


def _url(percorso):
    base = getattr(settings, "EDUWISP_PUBLIC_URL", "").rstrip("/")
    return f"{base}{percorso}" if base else None


def voce_obbligatoria(app):
    """Voce del protocollo per un'app obbligatoria: nome, logo e APK se presenti (ADR-0020)."""
    voce = {"id": app.identifier, "required": True, "name": app.name[:100]}
    if app.icon:
        icona = _url(app.icon.url)
        if icona:
            voce["icon"] = icona
    if app.apk and app.apk_sha256:
        indirizzo = _url(reverse("eduwisp_apps:apk", args=[app.pk]))
        if indirizzo:
            voce["install"] = {"url": indirizzo, "sha256": app.apk_sha256, "size": app.apk_size}
    return voce


def required_apps(device, classe=None, studente=None):
    """App obbligatorie per il dispositivo: identificativo → App del catalogo dell'istituto."""
    regole = AppRule.objects.filter(
        ambito(classe, studente),
        organization=device.organization,
        app__platform=device.platform,
        required=True,
    ).select_related("app")
    return {r.app.identifier: r.app for r in regole}


def allowed_apps(device, now=None, vietate=None):
    """Elenco per il protocollo: [{"id": ...}, {"id": ..., "until": ...}, ...] (ADR-0019)."""
    now = now or timezone.now()
    vietate = _piattaforma(device, PlatformStatus.VIETATA) if vietate is None else vietate
    classe = classe_del_dispositivo(device)
    studente = studente_del_dispositivo(device)
    obbligatorie_app = required_apps(device, classe, studente)
    obbligatorie = set(obbligatorie_app) - vietate
    sempre = (
        _piattaforma(device, PlatformStatus.CONSENTITA)
        | set(
            AppRule.objects.filter(
                ambito(classe, studente),
                organization=device.organization,
                app__platform=device.platform,
            ).values_list("app__identifier", flat=True)
        )
        | obbligatorie
    ) - vietate
    elenco = [
        voce_obbligatoria(obbligatorie_app[i]) if i in obbligatorie else {"id": i}
        for i in sorted(sempre)
    ]
    if classe is not None:
        scadenze = {}
        for s in TemporaryUnlock.objects.filter(
            school_class=classe,
            app__platform=device.platform,
            starts_at__lte=now,
            ends_at__gt=now,
            ended_early_at__isnull=True,
        ).select_related("app"):
            i = s.app.identifier
            if i not in sempre and i not in vietate:
                scadenze[i] = max(scadenze.get(i, s.ends_at), s.ends_at)
        elenco += [{"id": i, "until": t.isoformat()} for i, t in sorted(scadenze.items())]
    return elenco


def requests_of_student(studente):
    """Stato dell'ultima richiesta per ogni app dello studente (ADR-0021)."""
    from .models import AppRequest

    if studente is None:
        return []
    ultime = {}
    for r in AppRequest.objects.filter(student=studente).order_by("created_at")[:500]:
        ultime[r.identifier] = r.status
    return [{"id": i, "status": st} for i, st in sorted(ultime.items())][:200]


def provide(device):
    stato = AppPolicyState.objects.filter(organization=device.organization).first()
    vietate = _piattaforma(device, PlatformStatus.VIETATA)
    catalogo = PlatformCatalogVersion.objects.filter(pk=1).first()
    versione = (stato.version if stato else 0) + (catalogo.version if catalogo else 0)
    if stato is not None and stato.allowlist_enabled:
        apps = {"mode": "allowlist", "allowed": allowed_apps(device, vietate=vietate)}
    else:
        obbligatorie_app = required_apps(
            device, classe_del_dispositivo(device), studente_del_dispositivo(device)
        )
        obbligatorie = sorted(set(obbligatorie_app) - vietate)
        if not vietate and not obbligatorie:
            return None
        apps = {
            "mode": "blocklist",
            "allowed": [voce_obbligatoria(obbligatorie_app[i]) for i in obbligatorie],
        }
    apps["blocked"] = sorted(vietate)
    richieste = requests_of_student(studente_del_dispositivo(device))
    if richieste:
        apps["requests"] = richieste
    return {"policy": {"apps": apps}, "version": versione}
