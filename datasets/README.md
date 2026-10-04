## NepWears datasets

This folder contains the structured data used by the Django app. The project reads these files through the settings-based data directory, so updates here can directly influence catalog browsing, filters, and recommendations.

## Dataset files

### events_ad.json
Purpose:
- Stores upcoming festivals, events, and occasions for the homepage and seasonal recommendations

Expected structure:

```json
[
  {
    "name": "Dashain",
    "kind": "festival",
    "date_ad": "2026-10-19",
    "tag_slug": "dashain-vijaya-dashami",
    "discount_percent": 20,
    "image_url": "https://example.com/dashain.jpg",
    "source": "https://example.com"
  }
]
```

### products.json
Purpose:
- Main product catalog used to populate the database

Import with:

```powershell
python manage.py import_products
```

Expected structure:

```json
[
  {
    "sku": "daura-suruwal-classic-set",
    "name": "Daura Suruwal",
    "type": "single",
    "base_price_npr": 5500,
    "stock_quantity": 10,
    "tags": {
      "gender": ["men"],
      "age_group": ["teen"],
      "region": ["hilly"],
      "festival": ["janai-purnima"],
      "event": ["bratabandha"],
      "caste": ["bahun-chettri"],
      "category": ["daura-suruwal", "traditional"]
    },
    "images": [
      {"url": "https://example.com/image.jpg", "alt": "Daura Suruwal"}
    ],
    "relevance_note": "Useful for Bratabandha and Janai Purnima",
    "source_urls": ["https://example.com/source"]
  }
]
```

### bundles.json
Purpose:
- Curated product associations for outfit-completion and bundle recommendations

Example fields:
- name
- product_names
- product_skus
- strength
- reason
- source_urls

### festival_rules.json
Purpose:
- Stores cultural guidance for festivals and occasions

Example fields:
- gender_scope
- strict_exclusion
- primary_age_group
- confidence
- note
- sources

This file helps the app make gender-aware recommendation decisions more carefully for occasions such as Teej, Bratabandha, Janai Purnima, and Mother’s Day.

## Data guidelines

- Keep product names clean and customer-facing.
- Put recommendation signals in tags rather than in the name.
- Keep SKU stable so updates can be applied safely.
- Add source URLs and relevance notes where possible for traceability.
- Validate rules and cultural tags after changing the datasets.

## Validation workflow

After updating the datasets, run:

```powershell
python manage.py validate_cultural_tags
```

This helpfully reports notes and warnings for cultural-matching issues in the dataset.
