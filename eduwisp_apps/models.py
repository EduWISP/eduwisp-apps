# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""App consentite (ADR-0019).

Elenco per istituto, indirizzo e classe; sblocchi temporanei dei docenti per le proprie classi.
Le app non consentite vengono sospese sul tablet dall'agente.
"""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from eduwisp_school.models import SchoolClass, Track
from eduwisp_users.models import OrganizationOwned

MAX_SBLOCCO = timedelta(hours=4)


class AppPolicyState(OrganizationOwned):
    """Stato delle app consentite dell'istituto: attivazione e versione (cresce a ogni modifica)."""

    allowlist_enabled = models.BooleanField(
        "elenco di app consentite attivo",
        default=False,
        help_text="se attivo, sui tablet si usano solo le app consentite",
    )
    version = models.PositiveIntegerField("versione", default=0, editable=False)

    class Meta:
        verbose_name = "impostazione delle app"
        verbose_name_plural = "impostazioni delle app"
        constraints = [
            models.UniqueConstraint(fields=["organization"], name="stato_app_unico_per_istituto")
        ]

    def __str__(self):
        stato = "attivo" if self.allowlist_enabled else "non attivo"
        return f"App consentite di {self.organization}: {stato}"


class App(OrganizationOwned):
    """App del catalogo dell'istituto."""

    name = models.CharField("nome", max_length=100)
    platform = models.CharField("piattaforma", max_length=32, default="android")
    identifier = models.CharField(
        "identificativo",
        max_length=255,
        help_text="per Android il nome del pacchetto, per esempio org.mozilla.firefox",
        validators=[RegexValidator(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,254}$")],
    )
    description = models.CharField("descrizione", max_length=200, blank=True)

    class Meta:
        verbose_name = "app"
        verbose_name_plural = "catalogo delle app"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "platform", "identifier"], name="app_unica_per_istituto"
            )
        ]

    def __str__(self):
        return self.name


class AppRule(OrganizationOwned):
    """App consentita per tutto l'istituto, per un indirizzo o per una classe."""

    app = models.ForeignKey(App, on_delete=models.CASCADE, related_name="rules", verbose_name="app")
    track = models.ForeignKey(
        Track, on_delete=models.CASCADE, null=True, blank=True, verbose_name="indirizzo"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, null=True, blank=True, verbose_name="classe"
    )
    same_organization_fields = ("app", "track", "school_class")

    class Meta:
        verbose_name = "app consentita"
        verbose_name_plural = "app consentite"

    def __str__(self):
        ambito = self.school_class or self.track or "tutto l'istituto"
        return f"{self.app} — {ambito}"

    def clean(self):
        super().clean()
        if self.track_id and self.school_class_id:
            raise ValidationError("Scegli un indirizzo oppure una classe, non entrambi.")
        if not self.app_id:
            return
        doppia = AppRule.objects.filter(
            app=self.app, track=self.track, school_class=self.school_class
        ).exclude(pk=self.pk)
        if doppia.exists():
            raise ValidationError("Questa app è già consentita in questo ambito.")


class TemporaryUnlock(OrganizationOwned):
    """Sblocco temporaneo di un'app per una classe, deciso da un suo docente."""

    app = models.ForeignKey(
        App, on_delete=models.CASCADE, related_name="unlocks", verbose_name="app"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="app_unlocks", verbose_name="classe"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name="docente",
    )
    starts_at = models.DateTimeField("inizio", default=timezone.now)
    ends_at = models.DateTimeField("fine")
    ended_early_at = models.DateTimeField("terminato in anticipo il", null=True, blank=True)
    same_organization_fields = ("app", "school_class")

    class Meta:
        verbose_name = "sblocco temporaneo"
        verbose_name_plural = "sblocchi temporanei"
        ordering = ["-starts_at"]

    def __str__(self):
        return (
            f"{self.app} — {self.school_class} fino alle {timezone.localtime(self.ends_at):%H:%M}"
        )

    @property
    def fine_effettiva(self):
        return min(self.ends_at, self.ended_early_at) if self.ended_early_at else self.ends_at

    def is_active(self, now=None):
        now = now or timezone.now()
        return self.starts_at <= now < self.fine_effettiva

    def clean(self):
        super().clean()
        if self.ends_at and self.starts_at:
            if self.ends_at <= self.starts_at:
                raise ValidationError({"ends_at": "La fine deve essere dopo l'inizio."})
            if self.ends_at - self.starts_at > MAX_SBLOCCO:
                raise ValidationError({"ends_at": "Uno sblocco dura al massimo 4 ore."})
