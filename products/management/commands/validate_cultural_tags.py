from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from products.models import Product, Tag, TagKind


class Command(BaseCommand):
    help = "Validate cultural tags against the festival rules dataset and print warnings for mismatches."

    def handle(self, *args, **options):
        data_dir = Path(getattr(settings, "NW_DATA_DIR", Path(settings.BASE_DIR) / "datasets"))
        rules_path = data_dir / "festival_rules.json"
        rules = {}
        if rules_path.exists():
            try:
                rules = json.loads(rules_path.read_text(encoding="utf-8") or "{}")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Unable to parse rules file: {exc}"))
                return

        if not isinstance(rules, dict):
            self.stdout.write(self.style.WARNING("festival_rules.json must contain an object."))
            return

        products = Product.objects.filter(is_active=True).prefetch_related("tags")
        total = 0
        warnings = 0
        notes = 0
        for product in products:
            tags = list(product.tags.all())
            relevant_slugs = {t.slug for t in tags if t.kind in {TagKind.FESTIVAL, TagKind.EVENT, TagKind.OCCASION, TagKind.CASTE}}
            if not relevant_slugs:
                continue
            total += 1
            for slug in sorted(relevant_slugs):
                rule = rules.get(slug)
                if not isinstance(rule, dict):
                    continue
                gender_scope = str(rule.get("gender_scope") or "").strip().lower()
                strict_exclusion = bool(rule.get("strict_exclusion"))
                confidence = str(rule.get("confidence") or "").strip().lower()
                if confidence == "needs_review":
                    notes += 1
                    self.stdout.write(self.style.WARNING(f"NOTE [{slug}] {product.sku or product.name}: {rule.get('note', '')}"))
                    continue
                product_genders = {t.slug for t in tags if t.kind == TagKind.GENDER and t.slug in {"men", "women", "kids"}}
                if gender_scope in {"men", "women", "kids"} and strict_exclusion and product_genders and gender_scope not in product_genders:
                    warnings += 1
                    self.stdout.write(self.style.WARNING(f"WARNING [{slug}] {product.sku or product.name}: expects {gender_scope} but found {sorted(product_genders)}"))
                elif gender_scope == "mixed" and strict_exclusion is False and product_genders and len(product_genders) == 1:
                    warnings += 1
                    self.stdout.write(self.style.WARNING(f"WARNING [{slug}] {product.sku or product.name}: mixed rule but only one gender tag present ({sorted(product_genders)})"))

        self.stdout.write(self.style.SUCCESS(f"Validated {total} culturally relevant products; warnings={warnings}; notes={notes}"))
