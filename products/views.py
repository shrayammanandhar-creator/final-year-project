from __future__ import annotations

import difflib
import json
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, TemplateView

from recommendations.models import ProductView
from recommendations.signals import log_signal
from recommendations.festival import get_upcoming_festival, list_upcoming_events
from recommendations.services import complete_outfit, recommend_for_user, similar_products
from .models import Product, Tag, TagKind
from .pricing import convert_from_npr, currency_symbol
from .promotions import active_sale, attach_sale_prices
from .query import apply_product_filters, rank_product_queryset, _expand_search_values


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


def _fallback_products_for_event(qs, slug: str, *, params=None, currency: str = "NPR"):
    rules = _load_festival_rules()
    rule = rules.get(slug) if isinstance(rules, dict) else None
    if not isinstance(rule, dict):
        return qs.none()
    gender_scope = str(rule.get("gender_scope") or "").strip().lower()
    strict_exclusion = bool(rule.get("strict_exclusion"))
    if not strict_exclusion or gender_scope not in {"men", "women", "kids"}:
        return qs.none()

    base_params = params.copy() if params is not None else {}
    for key in ["festival", "event", "occasion"]:
        try:
            base_params.pop(key, None)
        except Exception:
            pass
    fallback = apply_product_filters(qs, base_params, currency=currency)
    gender_q = Q(tags__kind=TagKind.GENDER, tags__slug=gender_scope) | Q(tags__kind=TagKind.GENDER, tags__slug="all")
    category_q = Q(
        tags__kind=TagKind.CATEGORY,
        tags__slug__in=["traditional", "cultural-dress", "womenswear", "menswear", "kurta", "kurta-suruwal", "saree", "dhoti", "daura-suruwal", "unisex"],
    )
    return fallback.filter(gender_q).filter(category_q).distinct()


def _user_currency(request) -> str:
    if request.user.is_authenticated:
        return (request.user.preferred_currency or "NPR").upper()
    return (request.GET.get("currency") or "NPR").upper()


class HomeView(TemplateView):
    template_name = "products/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        currency = _user_currency(self.request)
        products = list(Product.objects.filter(is_active=True).prefetch_related("images", "tags")[:12])
        recommended = recommend_for_user(self.request.user, limit=12)
        upcoming_events = list_upcoming_events(limit=5)
        sale_event = active_sale()
        discount_percent = sale_event.discount_percent if sale_event else 0
        sale_products = Product.objects.filter(is_active=True).prefetch_related("images", "tags")
        if sale_event:
            sale_kind = _tag_kind_for_upcoming_event(sale_event.kind)
            sale_products = sale_products.filter(
                Q(tags__kind=sale_kind, tags__slug=sale_event.slug)
                | Q(
                    tags__kind__in=[TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION],
                    tags__slug=sale_event.slug,
                )
            ).distinct()
            if not sale_products.exists():
                sale_products = _fallback_products_for_event(
                    Product.objects.filter(is_active=True).prefetch_related("images", "tags"),
                    sale_event.slug,
                )
        sale_products = list(sale_products[:8])
        attach_sale_prices(products, sale=sale_event)
        attach_sale_prices(recommended, sale=sale_event)
        attach_sale_prices(sale_products, sale=sale_event)
        ctx.update(
            {
                "currency": currency,
                "currency_symbol": currency_symbol(currency),
                "products": products,
                "recommended": recommended,
                "upcoming_events": upcoming_events[:3],
                "sale_event": sale_event,
                "sale_discount_percent": discount_percent,
                "sale_products": sale_products,
            }
        )
        return ctx


class ProductListView(ListView):
    model = Product
    template_name = "products/product_list.html"
    context_object_name = "products"
    paginate_by = 24

    def get_queryset(self):
        currency = _user_currency(self.request)
        qs = Product.objects.all()
        filtered = apply_product_filters(qs, self.request.GET, currency=currency)
        upcoming_events = list_upcoming_events(limit=5)

        if not filtered.exists():
            selected_slug = None
            for key in ["festival", "event", "occasion"]:
                slug = (self.request.GET.get(key) or "").strip().lower()
                if slug:
                    selected_slug = slug
                    break
            if selected_slug:
                fallback = _fallback_products_for_event(qs, selected_slug, params=self.request.GET, currency=currency)
                if fallback.exists():
                    filtered = fallback
        return rank_product_queryset(filtered, self.request.GET, upcoming_slugs=[e.slug for e in upcoming_events])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        currency = _user_currency(self.request)
        attach_sale_prices(ctx["products"])
        ctx["currency"] = currency
        ctx["currency_symbol"] = currency_symbol(currency)
        ctx["kinds"] = [k for k, _ in TagKind.choices]
        ctx["selected"] = {
            "gender": self.request.GET.getlist("gender"),
            "age_group": self.request.GET.getlist("age_group"),
            "region": self.request.GET.getlist("region"),
            "festival": self.request.GET.get("festival", ""),
            "event": self.request.GET.get("event", ""),
            "occasion": self.request.GET.get("occasion", ""),
            "caste": self.request.GET.get("caste", ""),
            "type": self.request.GET.get("type", ""),
        }
        active_tag_count = Count("products", filter=Q(products__is_active=True), distinct=True)
        ctx["festival_options"] = (
            Tag.objects.filter(kind=TagKind.FESTIVAL)
            .annotate(active_products=active_tag_count)
            .filter(active_products__gt=0)
            .order_by("name")
        )
        ctx["event_options"] = (
            Tag.objects.filter(kind=TagKind.EVENT)
            .annotate(active_products=active_tag_count)
            .filter(active_products__gt=0)
            .order_by("name")
        )
        ctx["occasion_options"] = (
            Tag.objects.filter(kind=TagKind.OCCASION)
            .annotate(active_products=active_tag_count)
            .filter(active_products__gt=0)
            .order_by("name")
        )
        ctx["caste_options"] = (
            Tag.objects.filter(kind=TagKind.CASTE)
            .exclude(slug="all")
            .annotate(active_products=active_tag_count)
            .filter(active_products__gt=0)
            .order_by("name")
        )
        ctx["festival_quick_filters"] = [
            ("holi", "Holi"),
            ("rakhi", "Rakhi / Janai Purnima"),
            ("bhai tika", "Bhai Tika"),
            ("chhath", "Chhath"),
            ("dashain", "Dashain"),
            ("tihar", "Tihar"),
        ]
        ctx["event_quick_filters"] = [
            ("bratabandha", "Bratabandha"),
            ("pasni", "Pasni"),
            ("marriage", "Marriage"),
        ]
        return ctx


class ProductDetailView(DetailView):
    model = Product
    template_name = "products/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related("tags", "images")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        currency = _user_currency(self.request)
        tags = list(self.object.tags.all())
        attach_sale_prices([self.object])
        ctx["currency"] = currency
        ctx["currency_symbol"] = currency_symbol(currency)
        ctx["similar"] = similar_products(self.object, limit=8)
        ctx["complete_outfit"] = complete_outfit(self.object, limit=4)
        ctx["detail_summary"] = _product_detail_summary(self.object, tags)
        ctx["detail_points"] = _product_detail_points(tags)
        ctx["size_options"] = _size_options(tags)
        if self.request.user.is_authenticated:
            ProductView.objects.create(user=self.request.user, product=self.object)
            log_signal(self.request.user, self.object, kind="view")
        return ctx


def tag_browse(request, kind: str, slug: str):
    kind = (kind or "").strip().lower()
    tag = get_object_or_404(Tag, kind=kind, slug=slug)
    url = reverse("products:list")
    return redirect(f"{url}?{tag.kind}={tag.slug}")


def search_suggestions(request):
    """
    Basic auto-suggestions + typo tolerance.
    Returns { suggestions: [..] } for a query string.
    """
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"suggestions": []})

    names = list(
        Product.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=q)
            | Q(tags__name__icontains=q)
            | Q(tags__slug__in=_expand_search_values([q]))
        )
        .distinct()
        .values_list("name", flat=True)[:10]
    )
    if len(names) < 10:
        tag_names = list(
            Tag.objects.filter(
                Q(name__icontains=q)
                | Q(slug__in=_expand_search_values([q]))
            )
            .values_list("name", flat=True)
            .distinct()[: 10 - len(names)]
        )
        names.extend([name for name in tag_names if name not in names])

    if len(names) < 10:
        # typo tolerance fallback: close matches to known names
        universe = list(
            Product.objects.filter(is_active=True).values_list("name", flat=True)[:500]
        )
        names.extend(
            [m for m in difflib.get_close_matches(q, universe, n=10, cutoff=0.72) if m not in names]
        )

    return JsonResponse({"suggestions": names[:10]})


class ContactView(TemplateView):
    template_name = "pages/contact.html"


class AboutView(TemplateView):
    template_name = "pages/about.html"


def _tag_names(tags, kind: str) -> list[str]:
    return [t.name for t in tags if t.kind == kind and t.slug != "all"]


def _product_detail_summary(product: Product, tags) -> str:
    communities = _tag_names(tags, TagKind.CASTE)
    regions = _tag_names(tags, TagKind.REGION)
    festivals = _tag_names(tags, TagKind.FESTIVAL)
    categories = _tag_names(tags, TagKind.CATEGORY)

    parts = [f"{product.name} is a NepWears pick for traditional and cultural dressing."]
    if communities or regions:
        focus = ", ".join(communities[:2] + regions[:1])
        parts.append(f"It is especially suited to {focus} styles.")
    if festivals:
        parts.append(f"Recommended for {', '.join(festivals[:3])}.")
    elif categories:
        parts.append(f"Best for {', '.join(categories[:3]).lower()} looks.")
    return " ".join(parts)


def _product_detail_points(tags) -> list[str]:
    points = []
    festivals = _tag_names(tags, TagKind.FESTIVAL)
    categories = _tag_names(tags, TagKind.CATEGORY)
    regions = _tag_names(tags, TagKind.REGION)
    if festivals:
        points.append(f"Occasion: {', '.join(festivals[:3])}")
    if regions:
        points.append(f"Regional style: {', '.join(regions[:2])}")
    if categories:
        points.append(f"Style tags: {', '.join(categories[:4])}")
    points.append("Shipping estimate and final measurements can be confirmed during checkout.")
    return points


def _size_options(tags) -> list[str]:
    slugs = {t.slug for t in tags}
    if "kids" in slugs or "kids-wear" in slugs:
        return ["Kids 4-6", "Kids 7-9", "Kids 10-12", "Teen"]
    if "dhaka-topi" in slugs or "topi" in slugs or "accessory" in slugs:
        return ["Standard", "Small", "Medium", "Large"]
    return ["S", "M", "L", "XL", "Custom measurement"]


def _tag_kind_for_upcoming_event(kind: str | None) -> str:
    kind = (kind or "").strip().lower()
    if kind == "event":
        return TagKind.EVENT
    if kind == "occasion":
        return TagKind.OCCASION
    return TagKind.FESTIVAL
