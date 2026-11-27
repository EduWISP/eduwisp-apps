# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Sblocchi temporanei del docente (ADR-0019): solo nelle proprie classi, sempre registrati."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from eduwisp_audit.log import record
from eduwisp_audit.models import Action
from eduwisp_school.queries import classes_for_teacher

from .models import MAX_SBLOCCO, App, TemporaryUnlock

DURATE_MINUTI = (30, 60, 120, 240)


def _puo_sbloccare(user, school_class):
    return classes_for_teacher(user).filter(pk=school_class.pk).exists()


def unlock(user, school_class, app, minutes):
    if not _puo_sbloccare(user, school_class):
        raise PermissionDenied("Puoi sbloccare app solo nelle tue classi.")
    if app.organization_id != school_class.organization_id:
        raise PermissionDenied("L'app non è nel catalogo di questo istituto.")
    durata = timedelta(minutes=int(minutes))
    if durata <= timedelta(0) or durata > MAX_SBLOCCO:
        raise ValidationError("Uno sblocco dura al massimo 4 ore.")
    adesso = timezone.now()
    sblocco = TemporaryUnlock(
        organization=school_class.organization,
        app=app,
        school_class=school_class,
        teacher=user,
        starts_at=adesso,
        ends_at=adesso + durata,
    )
    sblocco.full_clean()
    sblocco.save()
    record(
        Action.APP_UNLOCK,
        actor=user,
        organization=school_class.organization,
        app=app.identifier,
        classe=str(school_class),
        minuti=int(minutes),
    )
    return sblocco


def end_unlock(user, sblocco):
    if not _puo_sbloccare(user, sblocco.school_class):
        raise PermissionDenied("Puoi richiudere app solo nelle tue classi.")
    if sblocco.ended_early_at or not sblocco.is_active():
        return sblocco
    sblocco.ended_early_at = timezone.now()
    sblocco.save(update_fields=["ended_early_at"])
    record(
        Action.APP_UNLOCK_END,
        actor=user,
        organization=sblocco.organization,
        app=sblocco.app.identifier,
        classe=str(sblocco.school_class),
    )
    return sblocco


def active_unlocks(school_class, now=None):
    now = now or timezone.now()
    return TemporaryUnlock.objects.filter(
        school_class=school_class, starts_at__lte=now, ends_at__gt=now, ended_early_at__isnull=True
    ).select_related("app", "teacher")


def unlockable_apps(school_class):
    """App del catalogo che si possono sbloccare (non già consentite per la classe)."""
    from django.db.models import Q

    from .models import AppRule

    ambito = Q(track__isnull=True, school_class__isnull=True) | Q(school_class=school_class)
    if school_class.section.track_id:
        ambito |= Q(track_id=school_class.section.track_id)
    consentite = AppRule.objects.filter(ambito).values_list("app_id", flat=True)
    return App.objects.filter(organization=school_class.organization).exclude(pk__in=consentite)
