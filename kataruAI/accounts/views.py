from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from django.contrib.auth.views import LoginView  as BaseLoginView, LogoutView as BaseLogoutView
from .forms import SignUpForm, LoginForm 
from .models import UserSetting, User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

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


class LoginView(BaseLoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"
    next_page = reverse_lazy("kataruAI:index")

    def form_valid(self, form):
        remember_me = self.request.POST.get("remember_me")
        if remember_me:
            self.request.session.set_expiry(1209600)  # 2週間保持
        else:
            self.request.session.set_expiry(0)        # ブラウザを閉じたら終了

        return super().form_valid(form)

class LogoutView(BaseLogoutView):
    next_page = reverse_lazy("kataruAI:index")

class MypageView(LoginRequiredMixin,TemplateView):
    template_name = "accounts/mypage.html"
    login_url = reverse_lazy("accounts:login")

# @method_decorator(login_required, name='dispatch')
# class UserUpdateView(UpdateView):
#     model = User
#     fields = ('first_name', 'last_name', 'email')
#     template_name = 'my_account.html'
#     success_url = reverse_lazy('my_account')