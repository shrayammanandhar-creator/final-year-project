from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthenticationWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="member", email="member@example.com", password="SafePass123!"
        )

    def test_login_and_sign_out_work_with_post(self):
        response = self.client.post(reverse("users:login"), {
            "username": self.user.username,
            "password": "SafePass123!",
            "next": reverse("users:dashboard"),
        })
        self.assertRedirects(response, reverse("users:dashboard"))
        self.assertEqual(str(self.client.get(reverse("users:dashboard")).wsgi_request.user), self.user.username)

        response = self.client.post(reverse("users:logout"))
        self.assertRedirects(response, reverse("products:home"))
        self.assertFalse(self.client.get(reverse("users:dashboard")).wsgi_request.user.is_authenticated)

    def test_login_does_not_redirect_to_an_external_next_url(self):
        response = self.client.post(reverse("users:login"), {
            "username": self.user.username,
            "password": "SafePass123!",
            "next": "https://example.invalid/steal-session",
        })
        self.assertRedirects(response, reverse("products:home"))
