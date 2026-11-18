from django.http import JsonResponse
from django.views.generic import CreateView, TemplateView
from .forms import SignUpForm
from .models import UserSetting


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "accounts/signup.html"

    def form_valid(self, form):
        user = form.save()
        UserSetting.objects.create(user=user)
        return JsonResponse({"ok": True}, status=201)

    def form_invalid(self, form):
        # フォームのエラーメッセージから最初の1つを取り出してJSに返す
        first_errors = next(iter(form.errors.values()))
        return JsonResponse({"ok": False, "error": first_errors[0]}, status=400)


class LoginView(TemplateView):
    template_name = "accounts/login.html"