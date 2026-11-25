"""シナリオまわりの画面（会員だけ）

Phase 4a：シナリオ作成（イベント39〜42）、作成したシナリオ一覧（公開切替・論理削除。イベント44・46）
参照：ユースケース記述「シナリオを作成する」「自作シナリオを一覧表示する」「シナリオを公開する」「シナリオを削除する」、
画面設計書「シナリオ作成」「作成したシナリオ一覧」、Drive のモック scenario_create.html・my_scenarios.html
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from plays.guest_play import DIFFICULTY_LABELS

from . import ai
from .forms import ScenarioCreateForm
from .images import delete_image, image_url, save_image
from .models import Scenario

LOGIN_URL = reverse_lazy("accounts:login")
PER_PAGE = 20
FINISHED = ("cleared", "failed")


def _error(code, message, status):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def with_counts(scenarios):
    """プレイ回数（クリア・失敗で終わったプレイの数）とお気に入り数を付ける"""
    return scenarios.annotate(
        play_count=Count("play", filter=Q(play__status__in=FINISHED), distinct=True),
        favorite_count=Count("favorite", distinct=True),
    )


def card(scenario):
    """一覧・詳細で使う表示用の値"""
    return {
        "scenario": scenario,
        "image_url": image_url(scenario),
        "difficulty_label": DIFFICULTY_LABELS[scenario.difficulty],
    }


# ---------- シナリオ作成 ----------
@login_required(login_url=LOGIN_URL)
@ensure_csrf_cookie  # scenario-create.js が X-CSRFToken で POST するため
@require_http_methods(["GET", "POST"])
def create(request):
    if request.method == "GET":
        return render(request, "scenarios/create.html")

    form = ScenarioCreateForm(request.POST, request.FILES)
    if not form.is_valid():
        message = next(errors[0] for errors in form.errors.values())
        return _error("BAD_REQUEST", message, 400)
    data = form.cleaned_data

    # ⑤ AIで生成（トランザクションの外）。失敗しても入力内容は画面に残る
    try:
        generated = ai.generate_user_scenario(data["title"], data["difficulty"], data["description"])
    except ai.GeminiError as e:
        if e.code == "BLOCKED":
            return _error("BLOCKED", "この内容ではシナリオを作れませんでした。表現を変えてみてね。", 400)
        return _error("AI_ERROR", "シナリオの作成に失敗しました。もう一度ためしてね。", 502)

    # ⑥ 非公開で保存し、共有コードを発行する（共有コードはモデルの初期値で自動発行）
    path = None
    try:
        if data["character_image"]:
            path = save_image(data["character_image"])
        with transaction.atomic():
            scenario = Scenario.objects.create(
                creator=request.user,
                kind=Scenario.Kind.USER,
                difficulty=data["difficulty"],
                title=data["title"],
                description=data["description"],
                image=path,
                is_public=False,
                **generated,
            )
    except Exception:
        delete_image(path)
        return _error("SAVE_ERROR", "保存に失敗しました", 500)

    return JsonResponse({
        "scenario_id": scenario.pk,
        "title": scenario.title,
        "character_name": scenario.character_name,
        "character_intro": scenario.character_intro,
        "goal": scenario.goal,
        "condition": scenario.condition,
        "share_code": scenario.share_code,
        "image_url": image_url(scenario),
    }, status=201)


# ---------- 作成したシナリオ一覧 ----------
@login_required(login_url=LOGIN_URL)
@ensure_csrf_cookie  # 公開切替・削除を X-CSRFToken で POST するため
@require_GET
def mine(request):
    scenarios = with_counts(
        Scenario.objects.filter(creator=request.user, kind=Scenario.Kind.USER, deleted_at__isnull=True)
    ).order_by("-created_at", "-pk")
    page = Paginator(scenarios, PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "scenarios/mine.html", {
        "page": page,
        "cards": [card(s) for s in page.object_list],
    })


def _own_scenario(request, scenario_id):
    """本人が作った・削除されていないシナリオ。それ以外は None（存在を隠す）"""
    return Scenario.objects.filter(
        pk=scenario_id, creator=request.user, kind=Scenario.Kind.USER, deleted_at__isnull=True
    ).first()


@login_required(login_url=LOGIN_URL)
@require_POST
def toggle_public(request, scenario_id):
    """公開・非公開の切り替え（イベント44）。作成者本人だけ。"""
    scenario = _own_scenario(request, scenario_id)
    if scenario is None:
        return _error("NOT_FOUND", "指定したシナリオは存在しないか、削除されています。", 404)
    try:
        scenario.is_public = not scenario.is_public
        scenario.save(update_fields=["is_public", "updated_at"])
    except Exception:
        return _error(
            "SAVE_ERROR", "公開状態の変更に失敗しました。しばらくたってから再度お試しください。", 500
        )
    return JsonResponse({"is_public": scenario.is_public})


@login_required(login_url=LOGIN_URL)
@require_POST
def delete(request, scenario_id):
    """論理削除（イベント46）。作成者本人だけ。"""
    scenario = _own_scenario(request, scenario_id)
    if scenario is None:
        return _error("NOT_FOUND", "指定したシナリオは存在しないか、削除されています。", 404)
    scenario.deleted_at = timezone.now()
    scenario.save(update_fields=["deleted_at", "updated_at"])
    return JsonResponse({"deleted": True})
