from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from products.models import Product, ProductImage, Tag


class Command(BaseCommand):
    help = "Import products from datasets/products.json (placeholder importer)."

    def handle(self, *args, **options):
        data_dir = Path(getattr(settings, "NW_DATA_DIR", Path(settings.BASE_DIR) / "datasets"))
        path = data_dir / "products.json"
        if not path.exists():
            self.stderr.write(self.style.ERROR(f"Missing dataset file: {path}"))
            return

        rows = json.loads(path.read_text(encoding="utf-8") or "[]")
        if not isinstance(rows, list):
            self.stderr.write(self.style.ERROR("products.json must be a JSON list."))
            return

        created = 0
        updated = 0

        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            sku = slugify(str(row.get("sku") or "").strip()) or None

            ptype = str(row.get("type", "single")).strip().lower() or "single"
            base_price_npr = Decimal(str(row.get("base_price_npr", "0")))
            stock_quantity = int(row.get("stock_quantity", 0) or 0)

            defaults = {
                "name": name,
                "type": ptype if ptype in {"single", "package"} else "single",
                "base_price_npr": base_price_npr,
                "stock_quantity": max(0, stock_quantity),
                "is_active": stock_quantity > 0,
            }
            if sku:
                product, was_created = Product.objects.update_or_create(sku=sku, defaults=defaults)
            else:
                product, was_created = Product.objects.update_or_create(name=name, defaults=defaults)

            tags = row.get("tags") or {}
            if isinstance(tags, dict):
                tag_objs = []
                for kind, values in tags.items():
                    if not values:
                        continue
                    if isinstance(values, (str, int)):
                        values = [str(values)]
                    if not isinstance(values, list):
                        continue
                    for v in values:
                        if isinstance(v, dict):
                            slug = str(v.get("slug") or "").strip()
                            tname = str(v.get("name") or slug).strip()
                        else:
                            slug = str(v).strip()
                            tname = slug.replace("-", " ").title()
                        if not slug:
                            continue
                        slug = slugify(slug)
                        tname = tname or slug.replace("-", " ").title()
                        tag, _ = Tag.objects.get_or_create(kind=str(kind).strip(), slug=slug, defaults={"name": tname})
                        if tag.name != tname and not tag.name:
                            tag.name = tname
                            tag.save(update_fields=["name"])
                        tag_objs.append(tag)

                if tag_objs:
                    product.tags.set(tag_objs)

            # Images (supports either filenames or {url, alt} objects)
            images = row.get("images") or []
            if isinstance(images, list):
                # Replace images on each import for deterministic results.
                ProductImage.objects.filter(product=product).delete()
                sort = 0
                for im in images:
                    sort += 1
                    if isinstance(im, str):
                        # legacy placeholder; keep empty source_url so template falls back to NW placeholder
                        ProductImage.objects.create(product=product, alt_text="", sort_order=sort)
                        continue
                    if isinstance(im, dict):
                        url = str(im.get("url") or "").strip()
                        alt = str(im.get("alt") or "").strip()
                        ProductImage.objects.create(
                            product=product, source_url=url, alt_text=alt, sort_order=sort
                        )

            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Import complete. Created: {created}, Updated: {updated}"))
