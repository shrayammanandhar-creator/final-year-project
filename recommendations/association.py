from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from math import sqrt
from typing import Iterable

from django.db.models import Prefetch

from orders.models import Order, OrderItem, OrderStatus
from products.models import Product
from recommendations.bundles import load_bundle_associations


@dataclass(frozen=True)
class AssocRule:
    antecedent: tuple[int, ...]
    consequent: int
    support: float
    confidence: float


def _transactions_from_orders(*, max_orders: int = 500) -> list[set[int]]:
    """
    Builds transactions as sets of product_ids from past orders.
    """
    orders = (
        Order.objects.filter(status__in=[OrderStatus.PLACED, OrderStatus.PAID, OrderStatus.SHIPPED])
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.only("order_id", "product_id")))
        .order_by("-created_at")[: max_orders]
    )

    tx: list[set[int]] = []
    for o in orders:
        items = {int(it.product_id) for it in o.items.all() if it.product_id}
        if len(items) >= 2:
            tx.append(items)

    # Add dataset-defined bundles as synthetic transactions (priors)
    for b in load_bundle_associations():
        skus = b.get("product_skus") or []
        names = b.get("product_names") or []
        if not isinstance(skus, list):
            skus = []
        if not isinstance(names, list):
            names = []
        if len(skus) < 2 and len(names) < 2:
            continue
        clean_skus = [str(s).strip() for s in skus if str(s).strip()]
        clean_names = [str(n).strip() for n in names if str(n).strip()]
        # Prefer hidden SKUs so display names can stay clean and even repeat.
        product_q = Product.objects.none()
        if clean_skus:
            product_q = Product.objects.filter(sku__in=clean_skus)
        if clean_names:
            product_q = product_q | Product.objects.filter(name__in=clean_names)
        ids = list(product_q.values_list("id", flat=True))
        ids = [int(i) for i in ids if i]
        if len(ids) < 2:
            continue
        strength = b.get("strength")
        try:
            repeat = max(1, min(6, int(round(float(strength) * 4)))) if strength is not None else 2
        except Exception:
            repeat = 2
        for _ in range(repeat):
            tx.append(set(ids))

    return tx


def mine_apriori_rules(
    transactions: list[set[int]],
    *,
    min_support: float = 0.02,
    min_confidence: float = 0.25,
    max_len: int = 3,
) -> list[AssocRule]:
    """
    Lightweight Apriori-like miner (up to max_len=3) for small datasets.
    """
    if not transactions:
        return []
    n = len(transactions)
    if n == 0:
        return []

    # Count itemsets of length 1..max_len
    counts: dict[tuple[int, ...], int] = Counter()
    for t in transactions:
        items = sorted(t)
        for k in range(1, max_len + 1):
            for comb in combinations(items, k):
                counts[comb] += 1

    def support(itemset: tuple[int, ...]) -> float:
        return counts.get(tuple(sorted(itemset)), 0) / float(n)

    # Keep frequent itemsets
    frequent = {iset: c for iset, c in counts.items() if (c / float(n)) >= min_support}
    if not frequent:
        return []

    # Mine rules X -> y for itemsets >= 2
    rules: list[AssocRule] = []
    for itemset, c in frequent.items():
        if len(itemset) < 2:
            continue
        sup_xy = c / float(n)
        for i in range(len(itemset)):
            y = itemset[i]
            x = itemset[:i] + itemset[i + 1 :]
            sup_x = support(x)
            if sup_x <= 0:
                continue
            conf = sup_xy / sup_x
            if conf >= min_confidence:
                rules.append(
                    AssocRule(
                        antecedent=tuple(sorted(x)),
                        consequent=int(y),
                        support=sup_xy,
                        confidence=conf,
                    )
                )

    rules.sort(key=lambda r: (r.confidence, r.support), reverse=True)
    return rules


def recommend_by_association(
    *,
    seed_product_ids: Iterable[int],
    exclude_product_ids: set[int],
    limit: int = 6,
) -> list[int]:
    """
    Returns product IDs recommended via Apriori rules given a seed basket.
    """
    seeds = {int(x) for x in seed_product_ids if x}
    if not seeds:
        return []

    tx = _transactions_from_orders()
    rules = mine_apriori_rules(tx)
    if not rules:
        return []

    scored: dict[int, float] = defaultdict(float)
    for r in rules:
        if r.consequent in exclude_product_ids:
            continue
        if r.consequent in seeds:
            continue
        if set(r.antecedent).issubset(seeds):
            # confidence-first scoring, support as tie-breaker
            scored[int(r.consequent)] = max(scored[int(r.consequent)], r.confidence + 0.1 * r.support)

    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return [pid for pid, _ in ranked[: max(0, int(limit))]]
