import json

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as BaseLoginView, LogoutView as BaseLogoutView
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import FormView

from plays.models import Play
from scenarios.models import Favorite, Scenario

from .forms import AccountForm, LoginForm, SignUpForm
from .models import UserSetting


class SignUpView(FormView):
    form_class = SignUpForm
    template_name = "accounts/signup.html"

    def form_valid(self, form):
        user = form.save()
        UserSetting.objects.create(user=user)
        return JsonResponse({"ok": True}, status=201)

    def form_invalid(self, form):
        # フォームのエラーメッセージから最初の1つを取り出してJSに返す（field でやり直すステップを伝える）
        field, first_errors = next(iter(form.errors.items()))
        return JsonResponse({"ok": False, "error": first_errors[0], "field": field}, status=400)


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


def play_stats(user):
    """マイページの成績（クリア数・プレイ回数・最高スコア）

    プレイ回数は終わったプレイ（クリア・失敗）の数。中断とプレイ中は数えない
    （中断したプレイは履歴・ランキングに含めない、という設計書の扱いに合わせた）。
    """
    finished = Play.objects.filter(user=user, status__in=["cleared", "failed"])
    cleared = finished.filter(status="cleared")
    return {
        "clear_count": cleared.count(),
        "play_count": finished.count(),
        "best_score": cleared.aggregate(best=Max("score"))["best"] or 0,
    }


class MypageView(LoginRequiredMixin, View):
    """マイページ（成績の表示・アカウント情報の変更）。画面設計書 マイページ・イベント37"""
    login_url = reverse_lazy("accounts:login")
    template_name = "accounts/mypage.html"

    def render_page(self, request, form, status=200):
        first_error = next((errors[0] for errors in form.errors.values()), None) if form.is_bound else None
        context = {"form": form, "stats": play_stats(request.user), "first_error": first_error}
        return render(request, self.template_name, context, status=status)

    def get(self, request):
        form = AccountForm(request.user, initial={
            "username": request.user.username, "email": request.user.email,
        })
        return self.render_page(request, form)

    def post(self, request):
        form = AccountForm(request.user, request.POST)
        if not form.is_valid():
            return self.render_page(request, form, status=400)
        user = form.save()
        update_session_auth_hash(request, user)  # パスワードを変えてもログインを保つ
        messages.success(request, "更新が完了しました")
        return redirect("accounts:mypage")


class AccountDeleteView(LoginRequiredMixin, View):
    """アカウント削除（イベント54）：論理削除・is_active=False・メール匿名化・
    作成したシナリオを論理削除・お気に入りを物理削除 → ログアウトしてトップへ。"""
    login_url = reverse_lazy("accounts:login")

    def post(self, request):
        user = request.user
        try:
            with transaction.atomic():
                now = timezone.now()
                Scenario.objects.filter(creator=user, deleted_at__isnull=True).update(deleted_at=now)
                Favorite.objects.filter(user=user).delete()
                user.deleted_at = now
                user.is_active = False
                user.email = f"deleted-{user.pk}@invalid"  # 同じメールで再登録できるように
                user.save(update_fields=["deleted_at", "is_active", "email"])
        except Exception:
            messages.error(request, "削除に失敗しました")
            return redirect("accounts:mypage")
        logout(request)
        return redirect("kataruAI:index")


@method_decorator(ensure_csrf_cookie, name="dispatch")  # settings.js が X-CSRFToken で POST するため
class SettingsView(LoginRequiredMixin, View):
    """ゲーム設定（イベント47・48）。GET で画面、POST（非同期・JSON）で1項目ずつすぐ保存する。"""
    login_url = reverse_lazy("accounts:login")

    def get(self, request):
        setting, _ = UserSetting.objects.get_or_create(user=request.user)
        return render(request, "accounts/settings.html", {"setting": setting})

    def post(self, request):
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            data = None
        setting, _ = UserSetting.objects.get_or_create(user=request.user)
        if isinstance(data, dict) and data.get("text_speed") in UserSetting.TextSpeed.values:
            setting.text_speed = data["text_speed"]
        elif isinstance(data, dict) and isinstance(data.get("auto_save_chat"), bool):
            setting.auto_save_chat = data["auto_save_chat"]
        else:
            return JsonResponse(
                {"error": {"code": "BAD_REQUEST", "message": "保存に失敗しました"}}, status=400
            )
        setting.save()
        return JsonResponse({"text_speed": setting.text_speed, "auto_save_chat": setting.auto_save_chat})
