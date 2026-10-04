from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


app_name = "users"

urlpatterns = [
    path("login/", views.login_modal, name="login"),
    path("signup/", views.signup_modal, name="signup"),
    path("logout/", auth_views.LogoutView.as_view(next_page="products:home"), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("wishlist/add/<int:product_id>/", views.wishlist_add, name="wishlist_add"),
    path("wishlist/remove/<int:product_id>/", views.wishlist_remove, name="wishlist_remove"),
]

