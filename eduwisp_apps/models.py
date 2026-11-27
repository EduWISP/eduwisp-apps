# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""App consentite (ADR-0019).

Elenco per istituto, indirizzo e classe; sblocchi temporanei dei docenti per le proprie classi.
Le app non consentite vengono sospese sul tablet dall'agente.
"""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from eduwisp_school.models import SchoolClass, Student, Track
from eduwisp_users.models import OrganizationOwned

MAX_SBLOCCO = timedelta(hours=4)


def archivio_privato():
    """Gli APK non sono pubblici: stanno fuori da MEDIA_ROOT e li scaricano solo i dispositivi."""
    # Nessun ripiego su BASE_DIR: non tutti i progetti lo definiscono.
    return FileSystemStorage(
        location=getattr(settings, "EDUWISP_PRIVATE_MEDIA_ROOT", None) or "privato"
    )


@deconstructible
class DimensioneMassima:
    """Rifiuta i file più grandi di ``kb`` kilobyte."""

    def __init__(self, kb):
        self.kb = kb

    def __call__(self, file):
        if file.size > self.kb * 1024:
            raise ValidationError(f"File troppo grande: al massimo {self.kb} KB.")

    def __eq__(self, other):
        return isinstance(other, DimensioneMassima) and other.kb == self.kb


IDENTIFICATIVO = RegexValidator(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,254}$")


class PlatformStatus(models.TextChoices):
    CONSENTITA = "consentita", "consentita in tutti gli istituti"
    VIETATA = "vietata", "vietata in tutti gli istituti"


class PlatformApp(models.Model):
    """Catalogo della piattaforma, deciso dall'amministratore di sistema (ADR-0019).

    Le app **vietate** (social, VPN, Tor, browser con VPN...) restano bloccate in ogni istituto,
    anche senza elenco di app consentite, e nessuno le può consentire o sbloccare. Le app
    **consentite** (per esempio quelle di istruzione) valgono per tutti gli istituti che usano
    l'elenco di app consentite.
    """

    name = models.CharField("nome", max_length=100)
    platform = models.CharField("piattaforma", max_length=32, default="android")
    identifier = models.CharField("identificativo", max_length=255, validators=[IDENTIFICATIVO])
    category = models.CharField("categoria", max_length=50)
    status = models.CharField("stato", max_length=20, choices=PlatformStatus.choices)

    class Meta:
        verbose_name = "app della piattaforma"
        verbose_name_plural = "catalogo della piattaforma"
        ordering = ["status", "category", "name"]
        constraints = [
            models.UniqueConstraint(fields=["platform", "identifier"], name="app_piattaforma_unica")
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class PlatformCatalogVersion(models.Model):
    """Versione del catalogo della piattaforma: cresce a ogni modifica (riga unica)."""

    version = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "versione del catalogo della piattaforma"

    def __str__(self):
        return f"Catalogo della piattaforma v{self.version}"


def is_forbidden(platform, identifier):
    return PlatformApp.objects.filter(
        platform=platform, identifier=identifier, status=PlatformStatus.VIETATA
    ).exists()


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
        validators=[IDENTIFICATIVO],
    )
    description = models.CharField("descrizione", max_length=200, blank=True)
    icon = models.FileField(
        "logo",
        upload_to="app/icone/",
        blank=True,
        validators=[FileExtensionValidator(["png", "webp", "jpg", "jpeg"]), DimensioneMassima(512)],
        help_text="PNG, WebP o JPEG, al massimo 512 KB; mostrato nel portale e sul tablet",
    )
    apk = models.FileField(
        "APK",
        upload_to="apk/",
        storage=archivio_privato,
        blank=True,
        validators=[FileExtensionValidator(["apk"]), DimensioneMassima(300 * 1024)],
        help_text="facoltativo: se l'app è obbligatoria, il tablet la installa da solo (ADR-0020). "
        "Solo APK liberi o forniti dall'editore.",
    )
    apk_sha256 = models.CharField(
        "impronta SHA-256 dell'APK", max_length=64, blank=True, editable=False
    )
    apk_size = models.PositiveBigIntegerField(
        "dimensione dell'APK", null=True, blank=True, editable=False
    )

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

    def clean(self):
        super().clean()
        if is_forbidden(self.platform, self.identifier):
            raise ValidationError(
                {"identifier": "App vietata in tutti gli istituti: non si può consentire."}
            )

    def save(self, *args, **kwargs):
        """Calcola impronta e dimensione dell'APK quando il file è nuovo o cambiato."""
        if not self.apk:
            self.apk_sha256, self.apk_size = "", None
        else:
            prima = App.objects.filter(pk=self.pk).values_list("apk", flat=True).first()
            if prima != self.apk.name or not self.apk_sha256:
                impronta = hashlib.sha256()
                self.apk.open("rb")
                for blocco in self.apk.chunks():
                    impronta.update(blocco)
                self.apk_sha256, self.apk_size = impronta.hexdigest(), self.apk.size
        super().save(*args, **kwargs)


class AppRule(OrganizationOwned):
    """App consentita per tutto l'istituto, per un indirizzo o per una classe."""

    app = models.ForeignKey(App, on_delete=models.CASCADE, related_name="rules", verbose_name="app")
    track = models.ForeignKey(
        Track, on_delete=models.CASCADE, null=True, blank=True, verbose_name="indirizzo"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, null=True, blank=True, verbose_name="classe"
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="app_rules",
        verbose_name="studente",
        help_text="solo per questo studente (per esempio strumenti del PDP); il motivo non si "
        "registra (ADR-0021)",
    )
    required = models.BooleanField(
        "obbligatoria",
        default=False,
        help_text="il tablet la installa da solo se nel catalogo c'è l'APK, altrimenti la "
        "propone allo studente (ADR-0020)",
    )
    same_organization_fields = ("app", "track", "school_class", "student")

    class Meta:
        verbose_name = "app consentita"
        verbose_name_plural = "app consentite"

    def __str__(self):
        ambito = self.student or self.school_class or self.track or "tutto l'istituto"
        return f"{self.app} — {ambito}"

    def clean(self):
        super().clean()
        if sum(bool(x) for x in (self.track_id, self.school_class_id, self.student_id)) > 1:
            raise ValidationError("Scegli un indirizzo, una classe oppure uno studente, uno solo.")
        if not self.app_id:
            return
        doppia = AppRule.objects.filter(
            app=self.app, track=self.track, school_class=self.school_class, student=self.student
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


class RequestStatus(models.TextChoices):
    IN_ATTESA = "pending", "in attesa"
    APPROVATA = "approved", "approvata"
    RESPINTA = "rejected", "respinta"


class AppRequest(OrganizationOwned):
    """Richiesta di usare un'app, fatta dallo studente dal suo tablet (ADR-0021)."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="app_requests", verbose_name="studente"
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        related_name="app_requests",
        verbose_name="classe",
    )
    platform = models.CharField("piattaforma", max_length=32, default="android")
    identifier = models.CharField("identificativo", max_length=255, validators=[IDENTIFICATIVO])
    name = models.CharField("nome dell'app", max_length=100, blank=True)
    note = models.CharField("motivazione dello studente", max_length=300, blank=True)
    created_at = models.DateTimeField("chiesta il", auto_now_add=True)
    status = models.CharField(
        "stato", max_length=20, choices=RequestStatus.choices, default=RequestStatus.IN_ATTESA
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="deciso da",
    )
    decided_at = models.DateTimeField("deciso il", null=True, blank=True)
    decision_reason = models.TextField("motivazione della decisione", blank=True)
    same_organization_fields = ("student", "school_class")

    class Meta:
        verbose_name = "richiesta di app"
        verbose_name_plural = "richieste di app"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name or self.identifier} — {self.student} ({self.get_status_display()})"


class AppRequestOpinion(models.Model):
    """Parere favorevole di un familiare, con motivazione (ADR-0021)."""

    request = models.ForeignKey(
        AppRequest, on_delete=models.CASCADE, related_name="opinions", verbose_name="richiesta"
    )
    guardian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name="familiare",
    )
    reason = models.TextField("motivazione")
    created_at = models.DateTimeField("dato il", auto_now_add=True)

    class Meta:
        verbose_name = "parere della famiglia"
        verbose_name_plural = "pareri della famiglia"
        constraints = [
            models.UniqueConstraint(fields=["request", "guardian"], name="un_parere_per_familiare")
        ]

    def __str__(self):
        return f"Parere di {self.guardian} su {self.request}"
