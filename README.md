# NepWears: Nepali Cultural Wear E-Commerce and Recommendation System

NepWears is a Django-based e-commerce and recommendation platform for Nepali traditional clothing. It helps users discover culturally appropriate products for festivals, ceremonies, occasions, and everyday wear by combining search, filtering, recommendation logic, and structured cultural metadata.

This project is useful for students, developers, and researchers who want to see how a real-world web application can combine e-commerce features with domain-specific logic. It is especially relevant for Nepali traditional attire, where product suitability depends on culture, religion, event, gender, age, community, and outfit context.

## 1. Project overview

NepWears is not just a product catalog. It is a cultural-aware shopping and recommendation system.

The core idea is simple:
- a user should not only find products by name or price
- the system should also suggest products that are suitable for a cultural context, such as Bratabandha, Janai Purnima, Pasni, Teej, Dashain, Tihar, or Janmashtami

The app implements this using:
- structured product tags
- cultural rules
- event and festival data
- user behavior signals
- curated outfit bundles
- explainable recommendation reasons

## 2. Problem statement

Traditional clothing shopping can be difficult because a product may be relevant for more than its visual design. In Nepali culture, suitability can depend on:

- the festival or ceremony
- the age of the wearer
- gender-based cultural expectations
- community or caste context
- region and tradition
- whether the item is part of a full outfit

A normal e-commerce system would often show unrelated products for these searches. NepWears tries to solve that by adding cultural intelligence to the recommendation flow.

## 3. Objectives

The main objectives of this project are to:

1. Build a complete Django-based e-commerce app for Nepali traditional wear.
2. Support cultural-aware product discovery using tags, filters, and aliases.
3. Recommend products based on user activity and cultural relevance.
4. Support seasonal and event-based recommendations.
5. Provide outfit-completion suggestions using curated bundles.
6. Make recommendations explainable so a user can understand why a product appears.
7. Provide a practical project structure that can be used for academic submission and further extension.

## 4. Scope of the project

The scope includes:

- browsing and listing products
- searching and filtering by cultural tags
- product detail view
- user accounts and wishlist
- cart and order flow
- recommendation engine
- event-based seasonal boosting
- cultural rule validation
- test coverage for core features

The project does not aim to be a full-scale enterprise store with payment gateways, live inventory, or AI-based visual search. Instead, it focuses on cultural-aware product discovery and recommendation logic.

## 5. Main features

### 5.1 Catalog and browsing
- product cards with image, price, and stock status
- detail pages for each product
- filter options for gender, age group, region, festival, event, occasion, caste, and price
- search support with cultural aliases and spelling variations

### 5.2 Cultural-aware filtering
- support for different event kinds such as festival, event, and occasion
- tag matching across related categories
- stricter handling for sensitive or gendered occasions
- validation commands to check catalog consistency

### 5.3 Recommendation system
- personalized recommendations for logged-in users
- seasonal recommendations based on upcoming events
- similar-product suggestions based on shared tags
- outfit-completion suggestions from curated bundles
- explanation labels for why a product is recommended

### 5.4 User accounts and shopping flow
- signup/login system
- wishlist support
- cart and order handling
- order history and user dashboard

### 5.5 Admin and data management
- Django admin support for products, tags, orders, and users
- import command for loading product data from JSON files
- validation command for cultural rules and tags

## 6. Technology stack

The project is built using the following technologies:

- Python
- Django
- SQLite (default local database)
- HTML, CSS, Django templates
- JSON-based datasets
- Django ORM
- Python test framework

## 7. Project architecture

The system is divided into apps, each with a clear responsibility:

- products: product catalog, tags, filtering, search, import logic, product views
- recommendations: user behavior tracking, similarity logic, seasonal boosting, bundles, explanation labels
- orders: cart, checkout, order handling, purchase tracking
- users: signup/login, profile fields, wishlist, dashboard

This separation helps keep the codebase organized and makes the system easier to extend.

## 8. Folder structure

```text
nepwears_project/
    manage.py
    requirements.txt
    db.sqlite3
    README.md
    datasets/
        products.json
        events_ad.json
        bundles.json
        festival_rules.json
    nepwears_project/
        settings.py
        urls.py
        wsgi.py
        asgi.py
    products/
        models.py
        views.py
        query.py
        tests.py
        management/commands/import_products.py
    recommendations/
        services.py
        association.py
        similarity.py
        bundles.py
        festival.py
        signals.py
    orders/
        models.py
        views.py
    users/
        models.py
        views.py
        forms.py
        wishlist_models.py
```

## 9. App-by-app explanation

### 9.1 products app
The products app is the core catalog layer.

It handles:
- product models
- tag models
- filtering logic
- search requests
- product detail pages
- import from JSON data
- price display and ranking

The most important files are:
- products/models.py
- products/query.py
- products/views.py
- products/management/commands/import_products.py

### 9.2 recommendations app
The recommendations app generates personalized suggestions.

It handles:
- user interaction tracking
- view/cart/purchase signals
- tag-based user profile building
- content-based similarity
- association-rule recommendations
- seasonal boosts from upcoming events
- outfit bundle completion

Important files:
- recommendations/services.py
- recommendations/similarity.py
- recommendations/association.py
- recommendations/bundles.py
- recommendations/festival.py

### 9.3 orders app
The orders app manages the shopping process.

It handles:
- cart logic
- checkout flow
- order creation
- order history
- purchase signal logging

### 9.4 users app
The users app handles account-related features.

It handles:
- user signup and login
- age and gender profile fields
- wishlist items
- dashboard views
- user-specific personalization

## 10. Data model overview

### Product
Stores product information such as:
- SKU
- name
- type
- base price
- stock quantity
- active status
- associated tags

### Tag
Stores structured metadata for matching and filtering.

Typical tag kinds include:
- gender
- age_group
- region
- festival
- event
- occasion
- caste
- category

### ProductImage
Stores the product images and their source information.

### Order and OrderItem
Store cart and order transactions.

### UserProductSignal
Tracks signals such as:
- viewed products
- carted products
- purchased products

### WishlistItem
Stores user wishlist entries.

## 11. Dataset structure

The system uses JSON datasets stored in the datasets folder.

### 11.1 products.json
Contains product seed data.

Important fields:
- sku
- name
- type
- base_price_npr
- stock_quantity
- tags
- images
- relevance_note
- source_urls

### 11.2 events_ad.json
Contains festival, event, and occasion calendar data.

Important fields:
- name
- kind
- date_ad
- tag_slug
- discount_percent
- image_url
- source

This dataset powers the homepage event section and seasonal recommendations.

### 11.3 bundles.json
Contains curated outfit and accessory associations.

This powers bundle-based recommendations and complete-outfit suggestions.

### 11.4 festival_rules.json
Stores cultural rules and guidance.

It helps the app make more careful decisions for events that are strongly gendered or culturally sensitive.

## 12. Core workflow

A typical user flow is:

1. The homepage loads featured products and upcoming events.
2. The user searches for a product or clicks an event card.
3. The query layer applies filters, aliases, and cultural tags.
4. Matching products are ranked by relevance.
5. The recommendation engine adds related items, seasonal picks, and bundle completions.
6. The user lands on product detail pages and can add items to cart or wishlist.

## 13. Recommendation logic

The recommendation system combines multiple signals.

### 13.1 Behavior-based signals
The system uses user behavior such as:
- views
- cart activity
- purchases
- wishlist activity

### 13.2 Tag-based similarity
Products that share similar tags are promoted.

### 13.3 Seasonal boosting
Products connected to an upcoming cultural event receive a ranking boost.

### 13.4 Bundle recommendations
If a product is part of a curated outfit, complementary items are suggested.

### 13.5 Explanation labels
The app adds short reasons to recommendations such as:
- For Bratabandha
- For Janai Purnima
- Matches Janai Purnima ritual wear
- Fits kids age group
- Recommended from your activity

## 14. Search and filtering details

The search system supports:
- free-text search
- tag-based filtering
- alias expansion for cultural spelling variants
- same-slug matching across related event kinds

Examples of alias handling include:
- bratabanda → bratabandha
- wedding → marriage
- rice feeding → pasni
- janmashtami → krishna-janmastami
- chhath → chaath-parwa

This is important because users often spell cultural names differently.

## 15. Cultural rule and validation system

The project includes a cultural rules layer and a validation command.

The validator checks whether products and tags align with the rules and reports potential issues. This makes the catalog easier to maintain and prevents obvious mismatches.

The validation command is:

```powershell
python manage.py validate_cultural_tags
```

## 16. Installation and setup

From the project root:

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py import_products
python manage.py validate_cultural_tags
python manage.py runserver
```

Open the site at:
- http://127.0.0.1:8000/

## 17. Useful commands

```powershell
python manage.py runserver
python manage.py import_products
python manage.py validate_cultural_tags
python manage.py test
python manage.py createsuperuser
python manage.py check
```

## 18. Testing

The project includes tests for:
- cultural filtering behavior
- event and occasion matching
- alias-based search and filter behavior
- recommendation logic
- product page and view stability

Run the full test suite with:

```powershell
python manage.py test
```

## 19. Example user journeys

### Example 1: Searching for Bratabandha wear
A user searches for bratabandha. The system expands the alias, finds relevant products, and ranks those that fit ceremony wear and the appropriate age/gender profile.

### Example 2: Viewing Janmashtami items
A user searches for Janmashtami. The system shows kids-themed Krishna or Radha costume products and relevant seasonal recommendations.

### Example 3: Buying a complete outfit
A user views a Daura Suruwal and sees complementary items such as a Dhaka Topi, waistcoat, or Janai Pack.

## 20. Deployment notes

The project currently uses SQLite for local development. For production deployment, the database and static files should be configured more carefully.

Typical production improvements include:
- switch to PostgreSQL or MySQL
- configure environment variables securely
- use a production web server such as Gunicorn or uWSGI
- serve static files properly
- configure a real media storage system if needed

## 21. Limitations

The project has some practical limitations:
- product images are partly external references
- currency handling is simple
- recommendation quality depends on data quality
- the rules layer is still based on curated metadata and may need expert review
- it is a hybrid rule-based system rather than a deep learning system

## 22. Future enhancements

Possible next steps:
- add payment integration
- add order tracking
- add reviews and ratings
- add multilingual support for Nepali and English
- add image-based recommendation
- add collaborative filtering once sufficient user data exists
- add recommendation evaluation metrics such as precision@k and click-through rate
- improve the cultural rules dataset with expert review and broader regional coverage

## 23. Why this project is valuable

This project is valuable because it combines e-commerce with cultural intelligence. Instead of treating heritage clothing as generic fashion, it respects the cultural, ceremonial, and social context behind each item.

It is also a strong academic project because it shows:
- practical Django development
- JSON-based data processing
- rule-based recommendation design
- domain-specific feature engineering
- test-driven refinement of important business logic

## 24. Short summary for presentation or report

NepWears is a Django-based e-commerce and recommendation system for Nepali traditional wear. It helps users discover products that are suitable for festivals, ceremonies, age groups, and cultural contexts. The project uses tags, cultural rules, search aliases, seasonal event data, and curated bundle associations to provide a more meaningful and explainable recommendation experience than simple product search.

