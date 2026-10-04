from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils.text import slugify

from .models import Product, Tag, TagKind


_CROSS_MATCH_KINDS = {TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION}

CULTURAL_ALIASES = {
    "bratabanda": ["bratabandha"],
    "brata-banda": ["bratabandha"],
    "brata-bandha": ["bratabandha"],
    "brata bandha": ["bratabandha"],
    "bartabandha": ["bratabandha"],
    "bartabanda": ["bratabandha"],
    "upanayan": ["bratabandha"],
    "upanayana": ["bratabandha"],
    "sacred-thread-ceremony": ["bratabandha", "janai-purnima"],
    "sacred thread ceremony": ["bratabandha", "janai-purnima"],
    "rice-feeding": ["pasni"],
    "rice feeding": ["pasni"],
    "annaprashan": ["pasni"],
    "annaprashana": ["pasni"],
    "wedding": ["marriage"],
    "bihe": ["marriage"],
    "bibaha": ["marriage"],
    "vivaha": ["marriage"],
    "marriage ceremony": ["marriage"],
    "gunyo cholo ceremony": ["gunyo-cholo"],
    "guniu choli": ["gunyo-cholo"],
    "janmashtami": ["krishna-janmastami"],
    "krishna-janmashtami": ["krishna-janmastami"],
    "yomari-punhi": ["yomari-punhe"],
    "yomari punhi": ["yomari-punhe"],
    "chhath": ["chaath-parwa"],
    "chhath-parwa": ["chaath-parwa"],
}


def _parse_decimal(v: str | None) -> Decimal | None:
    if not v:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


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


def _strict_gender_filter_for_values(values: list[str]) -> Q | None:
    rules = _load_festival_rules()
    if not rules:
        return None
    gender_filters: list[Q] = []
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        slug = slugify(raw)
        rule = rules.get(raw) or rules.get(raw.lower()) or rules.get(slug)
        if not isinstance(rule, dict):
            continue
        gender_scope = str(rule.get("gender_scope") or "").strip().lower()
        strict_exclusion = bool(rule.get("strict_exclusion"))
        if strict_exclusion and gender_scope in {"men", "women", "kids"}:
            gender_filters.append(
                Q(tags__kind=TagKind.GENDER, tags__slug=gender_scope)
                | Q(tags__kind=TagKind.GENDER, tags__slug="all")
            )
    if not gender_filters:
        return None
    combined = gender_filters[0]
    for q in gender_filters[1:]:
        combined |= q
    return combined


def _to_npr(amount: Decimal, currency: str) -> Decimal:
    currency = (currency or "NPR").upper()
    if currency == "NPR":
        return amount
    rates = getattr(settings, "NW_CURRENCY_RATES", {"NPR": 1.0})
    rate = Decimal(str(rates.get(currency, 1.0)))
    if rate == 0:
        return amount
    # amount_currency = amount_npr * rate  => amount_npr = amount_currency / rate
    return (amount / rate)


def apply_product_filters(qs, params, *, currency: str = "NPR"):
    """
    Supported params:
    - q: search term (name + tag names)
    - type: single|package
    - gender, age_group, region, festival, event, occasion, caste: tag slugs or names
      (comma-separated allowed)
    - min_price, max_price: in selected currency (converted back to NPR for filtering)
    """
    qs = qs.filter(is_active=True).prefetch_related("tags", "images")

    q = (params.get("q") or "").strip()
    if q:
        # Prefer tag/category matches as strongly as name matches, with cultural
        # aliases for common spelling variants such as "bratabanda".
        search_q = Q()
        for term in _expand_search_values([q]):
            search_q |= Q(name__icontains=term) | Q(tags__name__icontains=term) | Q(tags__slug__icontains=term)
        qs = qs.filter(search_q).distinct()

    ptype = (params.get("type") or "").strip().lower()
    if ptype in {"single", "package"}:
        qs = qs.filter(type=ptype)

    def _values_for(key: str) -> list[str]:
        # Support both multi-select (checkbox) and comma-separated input.
        if hasattr(params, "getlist"):
            raw_list = [v for v in params.getlist(key) if v]
        else:
            raw_list = []
        raw_single = (params.get(key) or "").strip()
        out: list[str] = []
        for v in raw_list:
            out.extend([x.strip() for x in str(v).split(",") if x.strip()])
        if raw_single:
            out.extend([x.strip() for x in raw_single.split(",") if x.strip()])
        # de-dupe preserving order
        seen = set()
        uniq = []
        for v in out:
            if v in seen:
                continue
            seen.add(v)
            uniq.append(v)
        return uniq

    relevant_filter_values: list[str] = []
    for kind in [
        TagKind.GENDER,
        TagKind.AGE_GROUP,
        TagKind.REGION,
        TagKind.FESTIVAL,
        TagKind.EVENT,
        TagKind.OCCASION,
        TagKind.CASTE,
    ]:
        values = _values_for(kind)
        if not values:
            continue
        qs = qs.filter(_tag_filter_for(kind, values)).distinct()
        if kind in {TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION}:
            relevant_filter_values.extend(values)

    strict_gender_filter = _strict_gender_filter_for_values(relevant_filter_values)
    if strict_gender_filter:
        qs = qs.filter(strict_gender_filter).distinct()

    min_price = _parse_decimal(params.get("min_price"))
    max_price = _parse_decimal(params.get("max_price"))
    if min_price is not None:
        qs = qs.filter(base_price_npr__gte=_to_npr(min_price, currency))
    if max_price is not None:
        qs = qs.filter(base_price_npr__lte=_to_npr(max_price, currency))

    return qs


def _expand_festival_values(values: list[str]) -> list[str]:
    expanded: list[str] = []
    aliases = {
        "holi": ["fagu-purnima-pahad", "fagu-purnima-terai"],
        "fagu": ["fagu-purnima-pahad", "fagu-purnima-terai"],
        "fagu-purnima": ["fagu-purnima-pahad", "fagu-purnima-terai"],
        "rakhi": ["janai-purnima"],
        "raksha-bandhan": ["janai-purnima"],
        "janai": ["janai-purnima"],
        "bhai-tika": ["tihar-bhai-tika"],
        "bhaitika": ["tihar-bhai-tika"],
        "laxmi-puja": ["tihar-laxmi-puja"],
        "mha-puja": ["tihar-mha-puja"],
        "lhosar": ["tamu-lhosar", "sonam-lhosar", "gyalpo-lhosar"],
        "losar": ["tamu-lhosar", "sonam-lhosar", "gyalpo-lhosar"],
        "chhath": ["chaath-parwa"],
        "chhath-parwa": ["chaath-parwa"],
        "janmashtami": ["krishna-janmastami"],
        "krishna-janmashtami": ["krishna-janmastami"],
        "yomari-punhi": ["yomari-punhe"],
    }
    for value in values:
        raw = str(value).strip()
        slug = slugify(raw)
        expanded.extend([raw, slug])
        expanded.extend(aliases.get(slug, []))
        expanded.extend(CULTURAL_ALIASES.get(raw.lower(), []))
        expanded.extend(CULTURAL_ALIASES.get(slug, []))
        expanded.append(value)
        if slug.startswith("dashain"):
            expanded.extend(["dashain", "dashain-vijaya-dashami"])
        elif slug.startswith("tihar"):
            expanded.extend(["tihar", "tihar-laxmi-puja", "tihar-mha-puja", "tihar-bhai-tika"])
        elif slug.startswith("fagu-purnima"):
            expanded.extend(["fagu-purnima-pahad", "fagu-purnima-terai"])
    seen = set()
    out = []
    for value in expanded:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _expand_filter_values(kind: str, values: list[str]) -> list[str]:
    expanded: list[str] = []
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        slug = slugify(raw)
        expanded.extend([raw, raw.lower(), slug])
        expanded.extend(CULTURAL_ALIASES.get(raw.lower(), []))
        expanded.extend(CULTURAL_ALIASES.get(slug, []))
    if kind == TagKind.FESTIVAL:
        expanded = _expand_festival_values(expanded)
    seen = set()
    out = []
    for value in expanded:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _expand_search_values(values: list[str]) -> list[str]:
    expanded = _expand_filter_values(TagKind.CATEGORY, values)
    expanded = _expand_festival_values(expanded)
    seen = set()
    out = []
    for value in expanded:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _tag_filter_for(kind: str, values: list[str]) -> Q:
    """
    Convert user-facing filter values into a robust tag query.

    Exact checkbox values still match exactly, while text fields such as
    festival/caste/region also accept friendly names, hyphenated slugs, partial
    tag names, and common cultural aliases like "holi" -> Fagu Purnima.
    """
    expanded = _expand_filter_values(kind, values)
    match_q = Q(slug__in=expanded)

    fuzzy_safe_kinds = {
        TagKind.REGION,
        TagKind.FESTIVAL,
        TagKind.EVENT,
        TagKind.OCCASION,
        TagKind.CASTE,
        TagKind.CATEGORY,
    }
    for value in values:
        raw = str(value).strip()
        slug = slugify(raw)
        if not raw:
            continue
        match_q |= Q(name__iexact=raw)
        if kind in fuzzy_safe_kinds and len(slug) >= 3:
            match_q |= Q(slug__icontains=slug) | Q(name__icontains=raw)

    kind_scope = _CROSS_MATCH_KINDS if kind in _CROSS_MATCH_KINDS else {kind}
    matching_tag_ids = Tag.objects.filter(Q(kind__in=kind_scope) & match_q).values("id")
    return Q(tags__id__in=matching_tag_ids)


def rank_product_queryset(qs, params, *, upcoming_slug: str | None = None, upcoming_slugs: list[str] | None = None):
    """
    Rank filtered products by cultural relevance instead of raw recency.
    Exact festival/community/gender matches beat broad "all" matches.
    """
    qs = Product.objects.filter(pk__in=qs.values("pk")).prefetch_related("tags", "images")

    festival_values = []
    raw_festival_values = _param_values(params, "festival")
    if raw_festival_values:
        festival_values = _expand_festival_values(raw_festival_values)
    upcoming_values = list(upcoming_slugs or [])
    if upcoming_slug:
        upcoming_values.insert(0, upcoming_slug)
    if upcoming_values:
        festival_values = _expand_festival_values(upcoming_values) + festival_values
    festival_values = list(dict.fromkeys(festival_values))

    gender_values = _param_values(params, "gender")
    event_values = _expand_filter_values(TagKind.EVENT, _param_values(params, "event"))
    occasion_values = _expand_filter_values(TagKind.OCCASION, _param_values(params, "occasion"))

    qs = qs.annotate(
        festival_relevance=Count(
            "tags",
            filter=Q(tags__kind__in=_CROSS_MATCH_KINDS, tags__slug__in=festival_values),
            distinct=True,
        ),
        caste_relevance=Count(
            "tags",
            filter=Q(tags__kind=TagKind.CASTE) & ~Q(tags__slug="all"),
            distinct=True,
        ),
        exact_gender_relevance=Count(
            "tags",
            filter=Q(tags__kind=TagKind.GENDER, tags__slug__in=gender_values),
            distinct=True,
        ),
        broad_gender_relevance=Count(
            "tags",
            filter=Q(tags__kind=TagKind.GENDER, tags__slug="all"),
            distinct=True,
        ),
        gender_category_relevance=Count(
            "tags",
            filter=Q(tags__kind=TagKind.CATEGORY, tags__slug__in=_gender_categories(gender_values)),
            distinct=True,
        ),
        cultural_relevance=Count(
            "tags",
            filter=Q(tags__kind=TagKind.CATEGORY, tags__slug__in=["cultural-dress", "traditional"]),
            distinct=True,
        ),
        event_relevance=Count(
            "tags",
            filter=Q(tags__kind__in=_CROSS_MATCH_KINDS, tags__slug__in=event_values),
            distinct=True,
        ),
        occasion_relevance=Count(
            "tags",
            filter=Q(tags__kind__in=_CROSS_MATCH_KINDS, tags__slug__in=occasion_values),
            distinct=True,
        ),
    )
    qs = qs.annotate(
        broad_match_penalty=Case(
            When(caste_relevance=0, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    )
    return qs.order_by(
        "-festival_relevance",
        "-event_relevance",
        "-occasion_relevance",
        "broad_match_penalty",
        "-caste_relevance",
        "-exact_gender_relevance",
        "-gender_category_relevance",
        "-cultural_relevance",
        "-created_at",
    )


def _gender_categories(values: list[str]) -> list[str]:
    cats = []
    if "men" in values:
        cats.append("menswear")
    if "women" in values:
        cats.append("womenswear")
    if "kids" in values:
        cats.append("kids-wear")
    return cats


def _param_values(params, key: str) -> list[str]:
    raw_list = []
    if hasattr(params, "getlist"):
        raw_list.extend([v for v in params.getlist(key) if v])
    raw_single = (params.get(key) or "").strip()
    if raw_single:
        raw_list.append(raw_single)

    out = []
    seen = set()
    for value in raw_list:
        for part in str(value).split(","):
            part = part.strip()
            if not part or part in seen:
                continue
            seen.add(part)
            out.append(part)
    return out
