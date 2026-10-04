from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

from products.models import Product


def load_bundle_associations() -> list[dict[str, Any]]:
    """
    Placeholder loader for the future association dataset in `datasets/bundles.json`.
    """
    data_dir = Path(getattr(settings, "NW_DATA_DIR", Path(settings.BASE_DIR) / "datasets"))
    path = data_dir / "bundles.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8") or "[]")
    except Exception:
        return []


def bundle_suggestions_for_product(product_id: int) -> list[dict[str, Any]]:
    """
    Placeholder: return associations involving the given product_id.
    Expected future shapes can be adapted once you provide the dataset.
    """
    bundles = load_bundle_associations()
    out = []
    for b in bundles:
        try:
            ids = set(int(x) for x in b.get("product_ids", []))
        except Exception:
            continue
        if product_id in ids:
            out.append(b)
    return out


def complete_outfit_for_product(product: Product, *, limit: int = 4) -> list[Product]:
    """
    Return culturally paired products from the curated bundle dataset.

    This powers "complete the outfit" suggestions such as Daura Suruwal with
    Dhaka Topi, Waistcoat, and Janai Pack for Bratabandha/formal looks.
    """
    if not product or not product.pk:
        return []

    product_sku = (product.sku or "").strip()
    product_name = (product.name or "").strip()
    candidate_skus: list[str] = []
    candidate_names: list[str] = []

    for bundle in load_bundle_associations():
        skus = [str(s).strip() for s in (bundle.get("product_skus") or []) if str(s).strip()]
        names = [str(n).strip() for n in (bundle.get("product_names") or []) if str(n).strip()]
        if (product_sku and product_sku in skus) or (product_name and product_name in names):
            candidate_skus.extend([sku for sku in skus if sku != product_sku])
            candidate_names.extend([name for name in names if name != product_name])

    # Strong explicit path for the requested ceremony outfit.
    if "daura-suruwal" in product_sku or "daura suruwal" in product_name.lower():
        candidate_skus = [
            "bratabandha-dhaka-topi-teen-boy",
            "bratabandha-waistcoat-men",
            "janai-sacred-thread-pack",
            *candidate_skus,
        ]

    candidate_skus = list(dict.fromkeys(candidate_skus))
    candidate_names = list(dict.fromkeys(candidate_names))
    qs = Product.objects.filter(is_active=True).exclude(id=product.id)
    if not candidate_skus and not candidate_names:
        return []

    products = list(
        qs.filter(sku__in=candidate_skus).prefetch_related("tags", "images")
    )
    found_ids = {p.id for p in products}
    if candidate_names:
        products.extend(
            p
            for p in qs.filter(name__in=candidate_names).exclude(id__in=found_ids).prefetch_related("tags", "images")
            if p.id not in found_ids
        )

    order = {sku: pos for pos, sku in enumerate(candidate_skus)}
    products.sort(key=lambda p: order.get(p.sku or "", len(order)))
    for p in products:
        p.recommendation_reason = _bundle_reason_for(product, p)
    return products[: max(0, int(limit))]


def _bundle_reason_for(seed: Product, candidate: Product) -> str:
    seed_name = (seed.name or "").lower()
    sku = candidate.sku or ""
    if "daura suruwal" in seed_name:
        if "topi" in sku:
            return "Completes the Daura Suruwal look"
        if "waistcoat" in sku:
            return "Formal layer for ceremony wear"
        if "janai" in sku:
            return "Matches Bratabandha ritual wear"
    return "Completes this cultural outfit"
