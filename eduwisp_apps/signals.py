# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Ogni modifica a catalogo, regole o sblocchi fa crescere la versione della policy."""

from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import (
    App,
    AppPolicyState,
    AppRule,
    PlatformApp,
    PlatformCatalogVersion,
    RequiredApp,
    TemporaryUnlock,
)


def incrementa(organization_id):
    stato, _ = AppPolicyState.objects.get_or_create(organization_id=organization_id)
    AppPolicyState.objects.filter(pk=stato.pk).update(version=F("version") + 1)


@receiver(post_save, sender=App)
@receiver(post_delete, sender=App)
@receiver(post_save, sender=AppRule)
@receiver(post_delete, sender=AppRule)
@receiver(post_save, sender=TemporaryUnlock)
@receiver(post_delete, sender=TemporaryUnlock)
@receiver(post_save, sender=RequiredApp)
@receiver(post_delete, sender=RequiredApp)
def _cambiato(sender, instance, **kwargs):
    incrementa(instance.organization_id)


@receiver(post_save, sender=AppPolicyState)
def _stato_cambiato(sender, instance, created, update_fields=None, **kwargs):
    # Attivare o disattivare l'elenco cambia la policy (l'update della versione non passa di qui).
    if not created:
        AppPolicyState.objects.filter(pk=instance.pk).update(version=F("version") + 1)


@receiver(post_save, sender=PlatformApp)
@receiver(post_delete, sender=PlatformApp)
def _catalogo_piattaforma_cambiato(sender, instance, **kwargs):
    riga, _ = PlatformCatalogVersion.objects.get_or_create(pk=1)
    PlatformCatalogVersion.objects.filter(pk=riga.pk).update(version=F("version") + 1)
