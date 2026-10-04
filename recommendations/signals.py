from __future__ import annotations

from django.utils import timezone


def log_signal(user, product, kind: str):
    """
    Lightweight helper to log user intent signals for recommendations.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return
    from .models import UserProductSignal

    UserProductSignal.objects.create(user=user, product=product, kind=kind, created_at=timezone.now())

