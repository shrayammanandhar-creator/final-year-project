"""Centralized festival-sale pricing used by product views and the cart."""
from __future__ import annotations

from decimal import Decimal

from recommendations.festival import UpcomingEvent, get_upcoming_festival


def active_sale() -> UpcomingEvent | None:
    """Return the current featured event only when it has a valid discount."""
    event = get_upcoming_festival()
    if event is None or event.discount_percent is None:
        return None
    try:
        percent = int(event.discount_percent)
    except (TypeError, ValueError):
        return None
    return event if 0 < percent <= 95 else None


def discount_percent_for_product(product, *, sale: UpcomingEvent | None = None) -> int:
    sale = active_sale() if sale is None else sale
    if sale is None:
        return 0
    tag_slugs = {tag.slug for tag in product.tags.all()}
    return int(sale.discount_percent) if sale.slug in tag_slugs else 0


def discounted_price_npr(product, *, sale: UpcomingEvent | None = None) -> Decimal:
    """The server-authoritative unit price for a product in the active sale."""
    base_price = Decimal(str(product.base_price_npr or "0.00"))
    percent = discount_percent_for_product(product, sale=sale)
    return (base_price * Decimal(100 - percent) / Decimal(100)).quantize(Decimal("0.01"))


def attach_sale_prices(products, *, sale: UpcomingEvent | None = None) -> None:
    """Attach display-only sale fields without persisting them on Product."""
    sale = active_sale() if sale is None else sale
    for product in products:
        percent = discount_percent_for_product(product, sale=sale)
        product.sale_discount_percent = percent
        product.sale_price_npr = discounted_price_npr(product, sale=sale) if percent else None
