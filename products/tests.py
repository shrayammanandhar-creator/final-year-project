import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from products.models import Product, Tag, TagKind
from products.query import apply_product_filters
from recommendations.bundles import complete_outfit_for_product
from recommendations.services import recommend_for_user, similar_products


class ProductFilteringTests(TestCase):
    def setUp(self):
        self.bratabandha = Tag.objects.create(kind=TagKind.EVENT, slug="bratabandha", name="Bratabandha")
        self.marriage = Tag.objects.create(kind=TagKind.EVENT, slug="marriage", name="Marriage")
        self.teej = Tag.objects.create(kind=TagKind.FESTIVAL, slug="teej", name="Teej")
        Tag.objects.create(kind=TagKind.FESTIVAL, slug="empty-festival", name="Empty Festival")
        self.men = Tag.objects.create(kind=TagKind.GENDER, slug="men", name="Men")
        self.women = Tag.objects.create(kind=TagKind.GENDER, slug="women", name="Women")

        self.daura = Product.objects.create(
            name="Daura Suruwal",
            sku="bratabandha-daura-suruwal",
            base_price_npr=9800,
            stock_quantity=5,
            is_active=True,
        )
        self.daura.tags.set([self.bratabandha, self.men])

        self.sari = Product.objects.create(
            name="Red Sari + Blouse Set",
            sku="teej-red-sari",
            base_price_npr=12500,
            stock_quantity=5,
            is_active=True,
        )
        self.sari.tags.set([self.teej, self.women])

        self.wedding = Product.objects.create(
            name="Wedding Waistcoat",
            sku="wedding-waistcoat",
            base_price_npr=3600,
            stock_quantity=5,
            is_active=True,
        )
        self.wedding.tags.set([self.marriage, self.men])

    def test_search_accepts_bratabandha_spelling_aliases(self):
        for term in ["bratabandha", "bratabanda", "brata bandha", "bartabandha"]:
            with self.subTest(term=term):
                qs = apply_product_filters(Product.objects.all(), {"q": term})
                self.assertIn(self.daura, list(qs))

    def test_event_filter_accepts_common_aliases(self):
        qs = apply_product_filters(Product.objects.all(), {"event": "bratabanda"})
        self.assertEqual(list(qs), [self.daura])

        wedding_qs = apply_product_filters(Product.objects.all(), {"event": "wedding"})
        self.assertEqual(list(wedding_qs), [self.wedding])

    def test_registered_festival_and_gender_filters_return_relevant_items(self):
        self.assertEqual(list(apply_product_filters(Product.objects.all(), {"festival": "teej"})), [self.sari])
        self.assertCountEqual(
            list(apply_product_filters(Product.objects.all(), {"gender": "men"})),
            [self.daura, self.wedding],
        )

    def test_product_list_exposes_event_and_occasion_filters(self):
        response = self.client.get(reverse("products:list"))
        self.assertContains(response, "Any event")
        self.assertContains(response, "Bratabandha")
        self.assertContains(response, "Any occasion")
        self.assertNotContains(response, "Empty Festival")

    def test_search_suggestions_include_typo_tolerant_tag_names(self):
        response = self.client.get(reverse("products:search_suggestions"), {"q": "bratabanda"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Bratabandha", response.json()["suggestions"])


class RecommendationFeatureTests(TestCase):
    def setUp(self):
        self.bratabandha = Tag.objects.create(kind=TagKind.EVENT, slug="bratabandha", name="Bratabandha")
        self.janai = Tag.objects.create(kind=TagKind.FESTIVAL, slug="janai-purnima", name="Janai Purnima")
        self.teen = Tag.objects.create(kind=TagKind.AGE_GROUP, slug="teen", name="Teen")
        self.men = Tag.objects.create(kind=TagKind.GENDER, slug="men", name="Men")

        self.daura = Product.objects.create(
            name="Daura Suruwal",
            sku="bratabandha-daura-suruwal-teen-boy",
            base_price_npr=9800,
            stock_quantity=5,
            is_active=True,
        )
        self.daura.tags.set([self.bratabandha, self.janai, self.teen, self.men])

        self.topi = Product.objects.create(
            name="Dhaka Topi",
            sku="bratabandha-dhaka-topi-teen-boy",
            base_price_npr=1600,
            stock_quantity=5,
            is_active=True,
        )
        self.topi.tags.set([self.bratabandha, self.teen, self.men])

        self.waistcoat = Product.objects.create(
            name="Waistcoat",
            sku="bratabandha-waistcoat-men",
            base_price_npr=2600,
            stock_quantity=5,
            is_active=True,
        )
        self.waistcoat.tags.set([self.bratabandha, self.teen, self.men])

        self.janai_pack = Product.objects.create(
            name="Janai Pack",
            sku="janai-sacred-thread-pack",
            base_price_npr=350,
            stock_quantity=5,
            is_active=True,
        )
        self.janai_pack.tags.set([self.bratabandha, self.janai, self.teen, self.men])

    def test_complete_outfit_orders_requested_bratabandha_addons(self):
        outfit = complete_outfit_for_product(self.daura, limit=3)
        self.assertEqual([p.sku for p in outfit], [
            "bratabandha-dhaka-topi-teen-boy",
            "bratabandha-waistcoat-men",
            "janai-sacred-thread-pack",
        ])
        self.assertEqual(outfit[0].recommendation_reason, "Completes the Daura Suruwal look")

    def test_anonymous_recommendations_boost_upcoming_event_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "events_ad.json").write_text(
                json.dumps([
                    {
                        "name": "Bratabandha",
                        "kind": "event",
                        "date_ad": "2099-01-01",
                        "tag_slug": "bratabandha",
                    }
                ]),
                encoding="utf-8",
            )
            with override_settings(NW_DATA_DIR=data_dir):
                recs = list(recommend_for_user(None, limit=4))
        self.assertIn(self.daura, recs)
        self.assertEqual(getattr(recs[0], "recommendation_reason", ""), "For Bratabandha")

    def test_seasonal_boost_matches_same_slug_across_event_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "events_ad.json").write_text(
                json.dumps([
                    {
                        "name": "Janai Purnima",
                        "kind": "occasion",
                        "date_ad": "2099-01-01",
                        "tag_slug": "janai-purnima",
                    }
                ]),
                encoding="utf-8",
            )
            with override_settings(NW_DATA_DIR=data_dir):
                recs = list(recommend_for_user(None, limit=4))
        self.assertIn(self.janai_pack, recs[:2])
        self.assertEqual(getattr(recs[0], "recommendation_reason", ""), "For Janai Purnima")


class CulturalRuleEnforcementTests(TestCase):
    def setUp(self):
        self.teej = Tag.objects.create(kind=TagKind.FESTIVAL, slug="teej", name="Teej")
        self.mothers_day = Tag.objects.create(kind=TagKind.OCCASION, slug="mothers-day", name="Mother's Day")
        self.bratabandha = Tag.objects.create(kind=TagKind.EVENT, slug="bratabandha", name="Bratabandha")
        self.pasni = Tag.objects.create(kind=TagKind.EVENT, slug="pasni", name="Pasni")
        self.men = Tag.objects.create(kind=TagKind.GENDER, slug="men", name="Men")
        self.women = Tag.objects.create(kind=TagKind.GENDER, slug="women", name="Women")
        self.all_gender = Tag.objects.create(kind=TagKind.GENDER, slug="all", name="All")
        self.adult = Tag.objects.create(kind=TagKind.AGE_GROUP, slug="adult", name="Adult")

        self.women_teej = Product.objects.create(name="Women Teej Set", sku="women-teej-set", base_price_npr=5000, stock_quantity=5, is_active=True)
        self.women_teej.tags.set([self.teej, self.women, self.adult])

        self.men_teej = Product.objects.create(name="Men Teej Set", sku="men-teej-set", base_price_npr=5000, stock_quantity=5, is_active=True)
        self.men_teej.tags.set([self.teej, self.men, self.adult])

        self.women_mothers_day = Product.objects.create(name="Mother's Day Saree", sku="mothers-day-saree", base_price_npr=6000, stock_quantity=5, is_active=True)
        self.women_mothers_day.tags.set([self.mothers_day, self.women, self.adult])

        self.men_mothers_day = Product.objects.create(name="Father's Day Daura", sku="mothers-day-daura", base_price_npr=6000, stock_quantity=5, is_active=True)
        self.men_mothers_day.tags.set([self.mothers_day, self.men, self.adult])

        self.men_bratabandha = Product.objects.create(name="Bratabandha Daura", sku="bratabandha-daura", base_price_npr=7000, stock_quantity=5, is_active=True)
        self.men_bratabandha.tags.set([self.bratabandha, self.men, self.adult])

        self.women_bratabandha = Product.objects.create(name="Bratabandha Sari", sku="bratabandha-sari", base_price_npr=7000, stock_quantity=5, is_active=True)
        self.women_bratabandha.tags.set([self.bratabandha, self.women, self.adult])

        self.men_pasni = Product.objects.create(name="Pasni Boy Set", sku="pasni-boy-set", base_price_npr=6500, stock_quantity=5, is_active=True)
        self.men_pasni.tags.set([self.pasni, self.men, self.adult])

        self.women_pasni = Product.objects.create(name="Pasni Girl Set", sku="pasni-girl-set", base_price_npr=6500, stock_quantity=5, is_active=True)
        self.women_pasni.tags.set([self.pasni, self.women, self.adult])

    def _recommend_for_slug(self, slug, *, user=None):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "events_ad.json").write_text(
                json.dumps([{"name": slug.replace("-", " ").title(), "kind": "festival", "date_ad": "2099-01-01", "tag_slug": slug}]),
                encoding="utf-8",
            )
            (data_dir / "festival_rules.json").write_text(
                json.dumps({
                    "teej": {"gender_scope": "women", "strict_exclusion": True, "primary_age_group": "adult", "confidence": "verified", "note": "Women commonly wear red festive attire for Teej.", "sources": []},
                    "mothers-day": {"gender_scope": "women", "strict_exclusion": True, "primary_age_group": "adult", "confidence": "verified", "note": "Mother's Day is used here as a women-focused gifting/occasion cue.", "sources": []},
                    "bratabandha": {"gender_scope": "men", "strict_exclusion": True, "primary_age_group": "teen", "confidence": "needs_review", "note": "Ceremonial wear is commonly male-coded in the dataset, but regional variation exists.", "sources": []},
                    "pasni": {"gender_scope": "mixed", "strict_exclusion": False, "primary_age_group": "kids", "confidence": "needs_review", "note": "Pasni commonly includes boys and girls in distinct ceremonial wear.", "sources": []},
                }),
                encoding="utf-8",
            )
            with override_settings(NW_DATA_DIR=data_dir):
                return list(recommend_for_user(user, limit=6))

    def test_teej_recommendations_exclude_opposite_gender_items(self):
        User = get_user_model()
        user = User.objects.create_user(username="teej-user", email="teej@example.com")
        user.gender = "women"
        user.age = 25
        user.save(update_fields=["gender", "age"])
        recs = self._recommend_for_slug("teej", user=user)
        self.assertIn(self.women_teej, recs)
        self.assertNotIn(self.men_teej, recs)

    def test_strict_gender_rules_filter_out_opposite_gender_items_in_product_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "festival_rules.json").write_text(
                json.dumps({
                    "teej": {"gender_scope": "women", "strict_exclusion": True, "primary_age_group": "adult", "confidence": "verified", "note": "Women commonly wear red festive attire for Teej.", "sources": []},
                }),
                encoding="utf-8",
            )
            with override_settings(NW_DATA_DIR=data_dir):
                qs = apply_product_filters(Product.objects.all(), {"festival": "teej"})
        self.assertIn(self.women_teej, list(qs))
        self.assertNotIn(self.men_teej, list(qs))

    def test_similar_products_handles_strict_gender_rules_without_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "festival_rules.json").write_text(
                json.dumps({
                    "teej": {"gender_scope": "women", "strict_exclusion": True, "primary_age_group": "adult", "confidence": "verified", "note": "Women commonly wear red festive attire for Teej.", "sources": []},
                }),
                encoding="utf-8",
            )
            with override_settings(NW_DATA_DIR=data_dir):
                recs = similar_products(self.women_teej, limit=4)
        self.assertNotIn(self.men_teej, recs)

    def test_mothers_day_recommendations_exclude_opposite_gender_items(self):
        User = get_user_model()
        user = User.objects.create_user(username="mothers-day-user", email="mothers@example.com")
        user.gender = "women"
        user.age = 25
        user.save(update_fields=["gender", "age"])
        recs = self._recommend_for_slug("mothers-day", user=user)
        self.assertIn(self.women_mothers_day, recs)
        self.assertNotIn(self.men_mothers_day, recs)

    def test_bratabandha_recommendations_exclude_opposite_gender_items(self):
        User = get_user_model()
        user = User.objects.create_user(username="bratabandha-user", email="brata@example.com")
        user.gender = "men"
        user.age = 25
        user.save(update_fields=["gender", "age"])
        recs = self._recommend_for_slug("bratabandha", user=user)
        self.assertIn(self.men_bratabandha, recs)
        self.assertNotIn(self.women_bratabandha, recs)

    def test_pasni_recommendations_keep_both_gendered_variants_for_mixed_rules(self):
        User = get_user_model()
        user = User.objects.create_user(username="pasni-user", email="pasni@example.com")
        user.gender = "women"
        user.age = 14
        user.save(update_fields=["gender", "age"])
        recs = self._recommend_for_slug("pasni", user=user)
        self.assertIn(self.men_pasni, recs)
        self.assertIn(self.women_pasni, recs)
