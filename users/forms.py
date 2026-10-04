from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Currency, User


class SignupForm(UserCreationForm):
    first_name = forms.CharField(label="Name", max_length=150)
    preferred_currency = forms.ChoiceField(choices=Currency.choices)
    age = forms.IntegerField(min_value=5, max_value=100, required=False)
    gender = forms.ChoiceField(choices=User.Gender.choices, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "preferred_currency", "age", "gender", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("first_name", "")
        user.preferred_currency = self.cleaned_data.get("preferred_currency") or user.preferred_currency
        user.age = self.cleaned_data.get("age")
        user.gender = self.cleaned_data.get("gender", "")
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    pass

