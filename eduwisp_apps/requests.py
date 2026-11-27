# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Richieste di app (ADR-0021): lo studente chiede, la famiglia può dare un parere
favorevole motivato, un docente della classe decide con una motivazione."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from eduwisp_audit.log import record
from eduwisp_audit.models import Action
from eduwisp_school.queries import classes_for_teacher, students_for_guardian

from .models import (
    App,
    AppRequest,
    AppRequestOpinion,
    AppRule,
    PlatformApp,
    PlatformStatus,
    RequestStatus,
    is_forbidden,
)
from .policy import allowed_apps, classe_del_dispositivo, studente_del_dispositivo

MOTIVO_VIETATA = "App vietata in tutti gli istituti (ADR-0019): non si può approvare."


class NotPersonalDevice(Exception):
    """Le richieste partono solo dai tablet affidati a uno studente."""


def create_request(device, identifier, name="", note=""):
    """Crea la richiesta e restituisce (richiesta, creata)."""
    studente = studente_del_dispositivo(device)
    if studente is None:
        raise NotPersonalDevice
    if is_forbidden(device.platform, identifier):
        richiesta = AppRequest.objects.create(
            organization=device.organization,
            student=studente,
            school_class=classe_del_dispositivo(device),
            platform=device.platform,
            identifier=identifier,
            name=name[:100],
            note=note[:300],
            status=RequestStatus.RESPINTA,
            decided_at=timezone.now(),
            decision_reason=MOTIVO_VIETATA,
        )
        return richiesta, True
    if identifier in {a["id"] for a in allowed_apps(device) if "until" not in a}:
        return None, False  # già consentita: niente da chiedere
    esistente = AppRequest.objects.filter(
        student=studente,
        platform=device.platform,
        identifier=identifier,
        status=RequestStatus.IN_ATTESA,
    ).first()
    if esistente:
        return esistente, False
    if not name:
        piattaforma = PlatformApp.objects.filter(
            platform=device.platform, identifier=identifier, status=PlatformStatus.CONSENTITA
        ).first()
        name = piattaforma.name if piattaforma else ""
    richiesta = AppRequest.objects.create(
        organization=device.organization,
        student=studente,
        school_class=classe_del_dispositivo(device),
        platform=device.platform,
        identifier=identifier,
        name=name[:100],
        note=note[:300],
    )
    return richiesta, True


def visible_requests(user, role, organization):
    """Richieste che la persona può vedere, secondo il ruolo (ADR-0018 e ADR-0021)."""
    from eduwisp_users.models import Role

    qs = AppRequest.objects.filter(organization=organization).select_related(
        "student", "school_class", "decided_by"
    )
    if role == Role.SCHOOL_ADMIN:
        return qs
    if role == Role.TEACHER:
        return qs.filter(school_class__in=classes_for_teacher(user))
    if role == Role.GUARDIAN:
        return qs.filter(student__in=students_for_guardian(user))
    return qs.none()


def can_decide(user, richiesta):
    return (
        richiesta.status == RequestStatus.IN_ATTESA
        and richiesta.school_class_id is not None
        and classes_for_teacher(user).filter(pk=richiesta.school_class_id).exists()
    )


def can_give_opinion(user, richiesta):
    return (
        richiesta.status == RequestStatus.IN_ATTESA
        and students_for_guardian(user).filter(pk=richiesta.student_id).exists()
    )


@transaction.atomic
def decide(user, richiesta, approve, reason):
    """Decisione del docente, con motivazione obbligatoria. Se approva, l'app diventa
    consentita solo per quello studente."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("La motivazione è obbligatoria.")
    if not can_decide(user, richiesta):
        raise PermissionDenied("Decide un docente della classe, finché la richiesta è in attesa.")
    if approve and is_forbidden(richiesta.platform, richiesta.identifier):
        raise ValidationError(MOTIVO_VIETATA)
    if approve:
        app, _ = App.objects.get_or_create(
            organization=richiesta.organization,
            platform=richiesta.platform,
            identifier=richiesta.identifier,
            defaults={"name": richiesta.name or richiesta.identifier},
        )
        AppRule.objects.get_or_create(
            organization=richiesta.organization,
            app=app,
            track=None,
            school_class=None,
            student=richiesta.student,
        )
    richiesta.status = RequestStatus.APPROVATA if approve else RequestStatus.RESPINTA
    richiesta.decided_by = user
    richiesta.decided_at = timezone.now()
    richiesta.decision_reason = reason
    richiesta.save()
    record(
        Action.APP_REQUEST_DECISION,
        actor=user,
        organization=richiesta.organization,
        reason=reason,
        app=richiesta.identifier,
        approvata=approve,
        richiesta_id=richiesta.pk,
        studente_id=richiesta.student_id,
    )
    return richiesta


def add_opinion(user, richiesta, reason):
    """Parere favorevole di un familiare, con motivazione obbligatoria."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("La motivazione è obbligatoria.")
    if not can_give_opinion(user, richiesta):
        raise PermissionDenied("Solo i familiari dello studente, finché la richiesta è in attesa.")
    parere, _ = AppRequestOpinion.objects.update_or_create(
        request=richiesta, guardian=user, defaults={"reason": reason}
    )
    record(
        Action.APP_REQUEST_OPINION,
        actor=user,
        organization=richiesta.organization,
        reason=reason,
        app=richiesta.identifier,
        richiesta_id=richiesta.pk,
    )
    return parere
