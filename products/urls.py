from django.urls import path

from . import views


app_name = "products"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("products/", views.ProductListView.as_view(), name="list"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="detail"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("browse/<slug:kind>/<slug:slug>/", views.tag_browse, name="browse_tag"),
    path("api/search-suggestions/", views.search_suggestions, name="search_suggestions"),
]
