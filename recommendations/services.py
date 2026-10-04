from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.db.models import Case, Count, IntegerField, Q, Value, When

from orders.models import OrderStatus
from products.models import Product, TagKind
from recommendations.association import recommend_by_association
from recommendations.bundles import complete_outfit_for_product
from recommendations.festival import get_upcoming_festival
from recommendations.models import SignalKind, UserProductSignal
from recommendations.similarity import cosine_similarity_binary_weighted
from users.models import WishlistItem


def _load_festival_rules() -> dict[str, dict]:
    data_dir = Path(getattr(settings, "NW_DATA_DIR", Path(settings.BASE_DIR) / "datasets"))
    path = data_dir / "festival_rules.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _strict_gender_filter_for_product(product: Product) -> Q | None:
    rules = _load_festival_rules()
    if not rules:
        return None
    relevant_slugs = {t.slug for t in product.tags.all() if t.kind in {TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION}}
    for slug in relevant_slugs:
        rule = rules.get(slug)
        if not isinstance(rule, dict):
            continue
        gender_scope = str(rule.get("gender_scope") or "").strip().lower()
        strict_exclusion = bool(rule.get("strict_exclusion"))
        if strict_exclusion and gender_scope in {"men", "women", "kids"}:
            return Q(tags__kind=TagKind.GENDER, tags__slug=gender_scope) | Q(tags__kind=TagKind.GENDER, tags__slug="all")
    return None


def _gender_filter_for_slug(slug: str | None, *, fallback_gender: str | None = None) -> Q | None:
    rules = _load_festival_rules()
    if slug:
        rule = rules.get(slug)
        if isinstance(rule, dict):
            gender_scope = str(rule.get("gender_scope") or "").strip().lower()
            strict_exclusion = bool(rule.get("strict_exclusion"))
            if strict_exclusion and gender_scope in {"men", "women", "kids"}:
                return Q(tags__kind=TagKind.GENDER, tags__slug=gender_scope) | Q(tags__kind=TagKind.GENDER, tags__slug="all")
            if not strict_exclusion and gender_scope in {"mixed", "unisex"}:
                return None
    # Only fall back to the user's gender when a specific strict rule exists.
    if slug and slug in rules and fallback_gender in {"men", "women", "kids"}:
        return Q(tags__kind=TagKind.GENDER, tags__slug=fallback_gender) | Q(tags__kind=TagKind.GENDER, tags__slug="all")
    return None


def recommend_for_user(user, *, limit: int = 12):
    """
    Placeholder recommendation engine.

    Current logic:
    - If user is anonymous: return trending products (by sales count).
    - If user has purchases: boost products sharing tags with purchased items.

    You can later plug in:
    - viewed history
    - association/bundle dataset
    - country/location priors
    """
    qs = Product.objects.filter(is_active=True).prefetch_related("tags")
    upcoming = get_upcoming_festival()
    upcoming_slug = upcoming.slug if upcoming else None
    upcoming_kind = _tag_kind_for_event(upcoming.kind) if upcoming else TagKind.FESTIVAL

    if user is None or not getattr(user, "is_authenticated", False):
        trending = list(qs.annotate(sales=Count("order_items")).order_by("-sales", "-created_at")[: max(0, int(limit))])
        seasonal = []
        if upcoming_slug:
            seasonal = list(
                qs.filter(_seasonal_tag_q(upcoming_slug, upcoming_kind))
                .distinct()
                .order_by("-created_at")[: max(0, min(6, int(limit)))]
            )
        recs = []
        seen = set()
        for p in seasonal + trending:
            if p.id in seen:
                continue
            seen.add(p.id)
            recs.append(p)
            if len(recs) >= limit:
                break
        _attach_recommendation_reasons(recs, upcoming_slug=upcoming_slug, upcoming_kind=upcoming_kind)
        return recs

    # Build a weighted tag profile from:
    # - signals (view/cart/purchase)
    # - wishlist
    # - cart contents
    # - order history
    # - user profile (gender + age_group)
    weights = {SignalKind.VIEW: 2, SignalKind.CART: 4, SignalKind.PURCHASE: 6}
    signals = (
        UserProductSignal.objects.filter(user=user)
        .select_related("product")
        .order_by("-created_at")[:200]
    )

    tag_counter: Counter[int] = Counter()
    # Collect product ids from multiple sources, then pull tag ids per product to avoid N+1.
    product_ids: list[int] = [s.product_id for s in signals]

    # Wishlist: strong signal of intent
    wishlist_product_ids = list(
        WishlistItem.objects.filter(user=user).values_list("product_id", flat=True)[:200]
    )
    product_ids.extend([int(pid) for pid in wishlist_product_ids if pid])

    # Cart contents: current buying intent
    cart_product_ids = list(
        Product.objects.filter(
            order_items__order__user=user,
            order_items__order__status=OrderStatus.CART,
        )
        .values_list("id", flat=True)
        .distinct()[:200]
    )
    product_ids.extend([int(pid) for pid in cart_product_ids if pid])

    # Order history: past purchases
    ordered_product_ids = list(
        Product.objects.filter(
            order_items__order__user=user,
            order_items__order__status__in=[OrderStatus.PLACED, OrderStatus.PAID, OrderStatus.SHIPPED],
        )
        .values_list("id", flat=True)
        .distinct()[:500]
    )
    product_ids.extend([int(pid) for pid in ordered_product_ids if pid])

    product_ids = list(dict.fromkeys(product_ids))  # de-dupe preserve order
    product_tags = (
        Product.objects.filter(id__in=product_ids)
        .values_list("id", "tags__id")
    )
    tags_by_product: dict[int, list[int]] = {}
    for pid, tid in product_tags:
        if tid is None:
            continue
        tags_by_product.setdefault(pid, []).append(tid)

    for s in signals:
        w = weights.get(s.kind, 1)
        for tid in tags_by_product.get(s.product_id, []):
            tag_counter[tid] += w

    # Recency boost: strongly bias toward the most recently viewed product's tags
    if signals:
        last = signals[0]
        for tid in tags_by_product.get(last.product_id, []):
            tag_counter[int(tid)] += 3

    # Add wishlist/cart/order weights (non-signal sources)
    for pid in wishlist_product_ids:
        for tid in tags_by_product.get(int(pid), []):
            tag_counter[tid] += 4
    for pid in cart_product_ids:
        for tid in tags_by_product.get(int(pid), []):
            tag_counter[tid] += 3
    for pid in ordered_product_ids:
        for tid in tags_by_product.get(int(pid), []):
            tag_counter[tid] += 5

    # Add light profile priors
    if getattr(user, "gender", "") in {"men", "women"}:
        # Prefer products matching user gender
        gender_slug = user.gender
        for tid in (
            qs.filter(tags__kind=TagKind.GENDER, tags__slug=gender_slug)
            .values_list("tags__id", flat=True)[:10]
        ):
            if tid:
                tag_counter[int(tid)] += 2

    if getattr(user, "age", None):
        age = user.age
        age_group = "adult"
        if age is not None and age < 15:
            age_group = "kids"
        elif age is not None and age < 20:
            age_group = "teen"
        for tid in (
            qs.filter(tags__kind=TagKind.AGE_GROUP, tags__slug=age_group)
            .values_list("tags__id", flat=True)[:10]
        ):
            if tid:
                tag_counter[int(tid)] += 2
    user_age_group = _age_group_for_user(user)

    # Determine a preferred gender to avoid cross-gender noise.
    preferred_gender: str | None = None
    if getattr(user, "gender", "") in {"men", "women"}:
        preferred_gender = user.gender
    else:
        recent_pids = [s.product_id for s in signals[:40]]
        recent_pids.extend([int(x) for x in wishlist_product_ids[:40]])
        recent_pids.extend([int(x) for x in cart_product_ids[:40]])
        recent_pids = list(dict.fromkeys([int(x) for x in recent_pids if x]))
        if recent_pids:
            slugs = list(
                Product.objects.filter(id__in=recent_pids, tags__kind=TagKind.GENDER)
                .values_list("tags__slug", flat=True)
            )
            # Ignore non-informative slugs
            slugs = [s for s in slugs if s in {"men", "women", "kids"}]
            c = Counter(slugs)
            # Only lock when there's a clear preference
            if c.get("women", 0) >= c.get("men", 0) + 1 and c.get("women", 0) >= 2:
                preferred_gender = "women"
            elif c.get("men", 0) >= c.get("women", 0) + 1 and c.get("men", 0) >= 2:
                preferred_gender = "men"
            elif c.get("kids", 0) >= 2:
                preferred_gender = "kids"

            # Still add soft boosts from inferred gender tags
            if preferred_gender in {"men", "women", "kids"}:
                for tid in (
                    qs.filter(tags__kind=TagKind.GENDER, tags__slug=preferred_gender)
                    .values_list("tags__id", flat=True)[:10]
                ):
                    if tid:
                        tag_counter[int(tid)] += 4

    top_tag_ids = [tid for tid, _ in tag_counter.most_common(25)]
    gender_filter_q = _gender_filter_for_slug(upcoming_slug, fallback_gender=preferred_gender)

    purchased_ids = set(
        Product.objects.filter(
            order_items__order__user=user,
            order_items__order__status__in=[OrderStatus.PLACED, OrderStatus.PAID, OrderStatus.SHIPPED],
        ).values_list("id", flat=True)
    )
    seed_ids = set(product_ids)

    recs = qs.exclude(id__in=purchased_ids | seed_ids)
    # Association-based (Apriori): use user's basket as seeds.
    assoc_seed_ids = list(dict.fromkeys([*wishlist_product_ids, *cart_product_ids, *ordered_product_ids]))
    assoc_ids = recommend_by_association(
        seed_product_ids=assoc_seed_ids,
        exclude_product_ids=set(purchased_ids),
        limit=max(0, min(6, limit)),
    )

    # Content-based (cosine): score products by cosine(user_tag_weights, product_tag_vector).
    cosine_ranked_ids: list[int] = []
    if tag_counter:
        # Evaluate a manageable candidate pool (recent + tag-matching).
        candidates = (
            recs.filter(tags__id__in=top_tag_ids).distinct().order_by("-created_at")[:400]
            if top_tag_ids
            else recs.order_by("-created_at")[:400]
        )
        scored = []
        for p in candidates:
            ptags = list(p.tags.values_list("id", flat=True))
            score = cosine_similarity_binary_weighted(product_tag_ids=ptags, user_tag_weights=tag_counter)
            if score > 0:
                scored.append((p.id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        cosine_ranked_ids = [pid for pid, _ in scored[: max(0, min(12, limit * 2))]]

    # Fallback overlap-based ranking (existing behavior)
    if top_tag_ids:
        recs_ranked = (
            recs.filter(tags__id__in=top_tag_ids)
            .annotate(overlap=Count("tags", filter=Q(tags__id__in=top_tag_ids), distinct=True))
            .order_by("-overlap", "-created_at")
            .distinct()
        )
    else:
        recs_ranked = recs.annotate(sales=Count("order_items")).order_by("-sales", "-created_at")
    if gender_filter_q:
        recs_ranked = recs_ranked.filter(gender_filter_q).distinct()

    # If an upcoming festival exists, try to surface matching items first.
    # This works as long as your product dataset uses the same slug convention.
    if upcoming_slug:
        fest_boost_qs = qs.filter(_seasonal_tag_q(upcoming_slug, upcoming_kind)).exclude(
            id__in=purchased_ids
        )
        if gender_filter_q:
            fest_boost_qs = fest_boost_qs.filter(gender_filter_q).distinct()
        fest_boost = fest_boost_qs.order_by("-created_at")[: max(0, min(6, limit))]
        # Merge while preserving order.
        merged = []
        seen = set()
        assoc_qs = _ordered_products(qs, assoc_ids)
        cosine_qs = _ordered_products(qs, cosine_ranked_ids)
        if gender_filter_q:
            assoc_qs = assoc_qs.filter(gender_filter_q).distinct()
            cosine_qs = cosine_qs.filter(gender_filter_q).distinct()
        assoc_products = list(assoc_qs)
        cosine_products = list(cosine_qs)
        # User activity should lead personalized recommendations; upcoming festivals are a secondary boost.
        for p in assoc_products + cosine_products + list(fest_boost) + list(recs_ranked):
            if p.id in seen:
                continue
            seen.add(p.id)
            merged.append(p)
            if len(merged) >= limit:
                break
        merged = _age_aware_order(merged, user_age_group=user_age_group)
        _attach_recommendation_reasons(merged, upcoming_slug=upcoming_slug, upcoming_kind=upcoming_kind, user_age_group=user_age_group)
        return merged

    # No upcoming festival: merge association + cosine + ranked.
    merged = []
    seen = set()
    assoc_qs = _ordered_products(qs, assoc_ids)
    cosine_qs = _ordered_products(qs, cosine_ranked_ids)
    if gender_filter_q:
        assoc_qs = assoc_qs.filter(gender_filter_q).distinct()
        cosine_qs = cosine_qs.filter(gender_filter_q).distinct()
    assoc_products = list(assoc_qs)
    cosine_products = list(cosine_qs)
    for p in assoc_products + cosine_products + list(recs_ranked):
        if p.id in seen:
            continue
        seen.add(p.id)
        merged.append(p)
        if len(merged) >= limit:
            break
    merged = _age_aware_order(merged, user_age_group=user_age_group)
    _attach_recommendation_reasons(merged, upcoming_slug=upcoming_slug, upcoming_kind=upcoming_kind, user_age_group=user_age_group)
    return merged


def _ordered_products(qs, ids: list[int]):
    ids = [int(pid) for pid in ids if pid]
    if not ids:
        return qs.none()
    ordering = Case(
        *[When(id=pid, then=Value(pos)) for pos, pid in enumerate(ids)],
        default=Value(len(ids)),
        output_field=IntegerField(),
    )
    return qs.filter(id__in=ids).annotate(_activity_rank=ordering).order_by("_activity_rank")


def similar_products(product: Product, *, limit: int = 8):
    """
    Similar items based on weighted cultural tag overlap.
    """
    product_tags = list(product.tags.all())
    tag_ids = [t.id for t in product_tags]
    if not product_tags:
        return Product.objects.filter(is_active=True).exclude(id=product.id).order_by("-created_at")[:limit]

    product_gender = {t.slug for t in product_tags if t.kind == TagKind.GENDER and t.slug in {"men", "women", "kids"}}
    strong_kinds = {TagKind.CASTE, TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION}
    tag_weights = {
        TagKind.CASTE: 5,
        TagKind.FESTIVAL: 5,
        TagKind.EVENT: 5,
        TagKind.OCCASION: 4,
        TagKind.CATEGORY: 3,
        TagKind.REGION: 2,
        TagKind.GENDER: 1,
        TagKind.AGE_GROUP: 1,
    }
    seed = {(t.kind, t.slug): tag_weights.get(t.kind, 1) for t in product_tags if t.slug != "all"}
    strong_seed = {key for key in seed if key[0] in strong_kinds}

    strict_gender_filter = _strict_gender_filter_for_product(product)
    candidates = (
        Product.objects.filter(is_active=True)
        .exclude(id=product.id)
        .filter(tags__id__in=tag_ids)
        .prefetch_related("tags", "images")
        .distinct()
    )
    if strict_gender_filter:
        candidates = candidates.filter(strict_gender_filter).distinct()
    candidates = candidates[:300]
    scored = []
    for candidate in candidates:
        ctags = list(candidate.tags.all())
        ckeys = {(t.kind, t.slug) for t in ctags if t.slug != "all"}
        candidate_gender = {t.slug for t in ctags if t.kind == TagKind.GENDER and t.slug in {"men", "women", "kids"}}
        score = sum(seed.get(key, 0) for key in ckeys)
        if strong_seed and not strong_seed.intersection(ckeys):
            score -= 4
        if product_gender and candidate_gender.intersection(product_gender):
            score += 2
        elif product_gender and candidate_gender:
            score -= 2
        if score > 0:
            scored.append((score, candidate.created_at, candidate))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [candidate for _, _, candidate in scored[:limit]]


def complete_outfit(product: Product, *, limit: int = 4):
    return complete_outfit_for_product(product, limit=limit)


def _tag_kind_for_event(kind: str | None) -> str:
    kind = (kind or "").strip().lower()
    if kind == "event":
        return TagKind.EVENT
    if kind == "occasion":
        return TagKind.OCCASION
    return TagKind.FESTIVAL


def _seasonal_tag_q(slug: str, kind: str | None) -> Q:
    primary = _tag_kind_for_event(kind)
    return Q(tags__kind=primary, tags__slug=slug) | Q(
        tags__kind__in=[TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION],
        tags__slug=slug,
    )


def _age_group_for_user(user) -> str | None:
    age = getattr(user, "age", None)
    if age is None:
        return None
    if age < 15:
        return "kids"
    if age < 20:
        return "teen"
    return "adult"


def _age_aware_order(products: list[Product], *, user_age_group: str | None) -> list[Product]:
    if user_age_group not in {"kids", "teen", "adult"}:
        return products

    def score(product: Product) -> int:
        tags = list(product.tags.all())
        slugs = {t.slug for t in tags}
        kinds = {(t.kind, t.slug) for t in tags}
        value = 0
        if (TagKind.AGE_GROUP, user_age_group) in kinds:
            value += 8
        if user_age_group == "kids" and ({"kids", "boys", "girls", "kids-wear"} & slugs):
            value += 6
        if user_age_group == "teen" and "bratabandha" in slugs:
            value += 5
        if user_age_group == "adult" and "adult" in slugs:
            value += 2
        if user_age_group == "kids" and "adult" in slugs and "kids" not in slugs:
            value -= 4
        return value

    return sorted(products, key=score, reverse=True)


def _attach_recommendation_reasons(
    products: list[Product],
    *,
    upcoming_slug: str | None = None,
    upcoming_kind: str | None = None,
    user_age_group: str | None = None,
) -> None:
    for product in products:
        tags = list(product.tags.all())
        tag_pairs = {(t.kind, t.slug) for t in tags}
        tag_names = {t.slug: t.name for t in tags}
        reason = ""
        if upcoming_slug and (
            (upcoming_kind, upcoming_slug) in tag_pairs
            or any((kind, upcoming_slug) in tag_pairs for kind in [TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION])
        ):
            reason = f"For {tag_names.get(upcoming_slug, upcoming_slug.replace('-', ' ').title())}"
        elif (TagKind.EVENT, "bratabandha") in tag_pairs:
            reason = "For Bratabandha"
        elif (TagKind.FESTIVAL, "janai-purnima") in tag_pairs:
            reason = "Matches Janai Purnima ritual wear"
        elif (TagKind.EVENT, "pasni") in tag_pairs:
            reason = "For Pasni ceremony wear"
        elif (TagKind.FESTIVAL, "krishna-janmastami") in tag_pairs:
            reason = "For Janmashtami kids programs"
        elif user_age_group and (TagKind.AGE_GROUP, user_age_group) in tag_pairs:
            reason = f"Fits {user_age_group} age group"
        elif any(t.kind == TagKind.FESTIVAL for t in tags):
            festival = next(t for t in tags if t.kind == TagKind.FESTIVAL)
            reason = f"For {festival.name}"
        elif any(t.kind == TagKind.EVENT for t in tags):
            event = next(t for t in tags if t.kind == TagKind.EVENT)
            reason = f"For {event.name}"
        product.recommendation_reason = reason or "Recommended from your activity"
