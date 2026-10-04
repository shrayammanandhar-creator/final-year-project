from django.urls import path

from . import views


app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/update/<int:product_id>/", views.update_cart_item, name="update_cart_item"),
    path("cart/offcanvas/", views.cart_offcanvas_fragment, name="cart_offcanvas_fragment"),
    path("cart/offcanvas/update/<int:product_id>/", views.update_cart_item_offcanvas, name="update_cart_item_offcanvas"),
    path("checkout/", views.checkout, name="checkout"),
]

