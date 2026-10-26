from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Vaqtinchalik parol bilan kirgan foydalanuvchini parol almashtirishga majburlaydi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            path = request.path
            allowed = (reverse("password_change"), reverse("logout"))
            if path not in allowed and not path.startswith(("/static/", "/media/")):
                return redirect("password_change")
        return self.get_response(request)