from __future__ import annotations

from decimal import Decimal

from django import template

from products.pricing import convert_from_npr


register = template.Library()


@register.filter
def price_in(amount_npr, currency: str):
    try:
        npr = Decimal(str(amount_npr))
    except Exception:
        return ""
    return convert_from_npr(npr, currency)


@register.simple_tag
def discounted_price(amount_npr, currency: str, discount_percent: int):
    """
    Returns converted price after applying discount_percent on NPR base.
    """
    try:
        npr = Decimal(str(amount_npr))
        pct = int(discount_percent)
    except Exception:
        return ""
    pct = max(0, min(pct, 95))
    discounted_npr = npr * Decimal(100 - pct) / Decimal(100)
    return convert_from_npr(discounted_npr, currency)

