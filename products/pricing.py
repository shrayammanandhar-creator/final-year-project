from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings


def convert_from_npr(amount_npr: Decimal, currency: str) -> Decimal:
    """
    Simple currency conversion based on settings.NW_CURRENCY_RATES.
    This is intentionally simple and deterministic for the project skeleton.
    """
    currency = (currency or "NPR").upper()
    rates = getattr(settings, "NW_CURRENCY_RATES", {"NPR": 1.0})
    rate = Decimal(str(rates.get(currency, rates.get("NPR", 1.0))))
    if currency == "NPR":
        return amount_npr.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (amount_npr * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def currency_symbol(currency: str) -> str:
    c = (currency or "NPR").upper()
    return {"NPR": "₨", "USD": "$", "EUR": "€"}.get(c, c)

