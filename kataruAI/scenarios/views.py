"""シナリオまわりの画面（会員だけ）

Phase 4a：シナリオ作成（イベント39〜42）、作成したシナリオ一覧（公開切替・論理削除。イベント44・46）
参照：ユースケース記述「シナリオを作成する」「自作シナリオを一覧表示する」「シナリオを公開する」「シナリオを削除する」、
画面設計書「シナリオ作成」「作成したシナリオ一覧」、Drive のモック scenario_create.html・my_scenarios.html
"""
import secrets

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
from .models import Favorite, Scenario

LOGIN_URL = reverse_lazy("accounts:login")
PER_PAGE = 20
RESAVE_SESSION_KEY = "scenario_resave_draft"  # 再保存用の一時保存（最新の1件だけ）
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

    # 再保存（ユースケース記述 ⑥-a）：前回 DB 保存に失敗した内容を、AI を呼ばずに保存し直す。
    # 生成した内容はサーバーのセッションにだけ持つ（画面から書き換えられないように）
    resave = request.POST.get("resave")
    if resave:
        draft = request.session.get(RESAVE_SESSION_KEY)
        if not isinstance(draft, dict) or draft.get("token") != resave:
            return _error("BAD_REQUEST", "再保存できませんでした。もう一度「AIでシナリオを作成」を押してね。", 400)
        fields = {key: draft[key] for key in ("title", "difficulty", "description")}
        generated = draft["generated"]
    else:
        fields = {key: data[key] for key in ("title", "difficulty", "description")}
        # ⑤ AIで生成（トランザクションの外）。失敗しても入力内容は画面に残る
        try:
            generated = ai.generate_user_scenario(fields["title"], fields["difficulty"], fields["description"])
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
                image=path,
                is_public=False,
                **fields,
                **generated,
            )
    except Exception:
        delete_image(path)
        # ⑥-a 生成した内容をセッションに一時保存し（最新の1件だけ）、再保存の番号を返す
        body = {"error": {"code": "SAVE_ERROR", "message": "保存に失敗しました"}}
        token = secrets.token_hex(16)
        request.session[RESAVE_SESSION_KEY] = dict(fields, generated=generated, token=token)
        try:
            # 500 の応答では Django がセッションを自動で保存しないので、ここで保存する。
            # セッションも DB に置いているので、DB が完全に止まっているときは保存できない → 再保存の番号は返さない
            request.session.save()
            body["resave_token"] = token
        except Exception:
            pass
        return JsonResponse(body, status=500)

    request.session.pop(RESAVE_SESSION_KEY, None)  # 保存できたら一時保存は消す
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


# ---------- シナリオ一覧・お気に入り一覧（Phase 4b・4c） ----------
SORTS = {
    "new": ("-created_at", "-pk"),                       # 新着＝作成日の降順
    "popular": ("-play_count", "-created_at", "-pk"),    # 人気＝プレイ回数の降順
    "favorites": ("-favorite_count", "-created_at", "-pk"),  # お気に入り数の降順
}
CODE_PATTERN = r"^[A-Za-z0-9]{8}$"
NOT_FOUND_SCENARIO = "指定したシナリオは存在しないか、削除されています。"


def public_scenarios():
    """一覧に出せるシナリオ：公開中・未削除・ユーザー作成（ランダムなお題は出さない）"""
    return Scenario.objects.filter(
        is_public=True, deleted_at__isnull=True, kind=Scenario.Kind.USER
    ).select_related("creator")


def self_best_text(user, scenario):
    """自己ベスト「{n}ターン／スコア{s}」。クリアしたことがなければ「-」"""
    from plays.models import Play  # plays は scenarios に依存しているので、ここで import する

    best = (
        Play.objects.filter(user=user, scenario=scenario, status="cleared")
        .order_by("-score", "turns_used").first()
    )
    return f"{best.turns_used}ターン／スコア{best.score}" if best else "-"


def detail_data(user, scenario, favorited):
    """詳細オーバーレイに出す値（一覧の行の data-* と、コード検索の JSON で共通）"""
    return {
        "id": scenario.pk,
        "title": scenario.title,
        "name": scenario.character_name or "",
        "level": scenario.difficulty,
        "desc": scenario.character_intro or "",
        "author": scenario.creator.username,
        "plays": scenario.play_count,
        "favorites": scenario.favorite_count,
        "best": self_best_text(user, scenario),
        "goal": scenario.goal or "",
        "cond": scenario.condition or "",
        "image": image_url(scenario),
        "fav": favorited,
    }


def _browse(request, favorites_only):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "new")
    allowed_sorts = ("new", "popular") if favorites_only else tuple(SORTS)
    if sort not in allowed_sorts:
        sort = "new"
    scenarios = with_counts(public_scenarios())
    my_favorites = set(
        Favorite.objects.filter(user=request.user).values_list("scenario_id", flat=True)
    )
    if favorites_only:
        scenarios = scenarios.filter(pk__in=my_favorites)
    if q:
        scenarios = scenarios.filter(Q(title__icontains=q) | Q(character_name__icontains=q))
    total = scenarios.count()
    page = Paginator(scenarios.order_by(*SORTS[sort]), PER_PAGE).get_page(request.GET.get("page"))
    rows = [
        dict(card(s), detail=detail_data(request.user, s, s.pk in my_favorites))
        for s in page.object_list
    ]
    if favorites_only:
        empty = "お気に入りに登録したシナリオはありません"
    elif not q and not public_scenarios().exists():
        empty = "公開されているシナリオはありません"
    else:
        empty = "条件に合うシナリオはありません"
    return render(request, "scenarios/list.html", {
        "page": page,
        "rows": rows,
        "q": q,
        "sort": sort,
        "sorts": [("new", "新着"), ("popular", "人気")] + ([] if favorites_only else [("favorites", "お気に入り数")]),
        "favorites_only": favorites_only,
        "total": total,
        "empty_message": empty,
    })


@login_required(login_url=LOGIN_URL)
@ensure_csrf_cookie  # お気に入り・開始を X-CSRFToken で POST するため
@require_GET
def browse(request):
    """シナリオ一覧（イベント23〜30・52）"""
    return _browse(request, favorites_only=False)


@login_required(login_url=LOGIN_URL)
@ensure_csrf_cookie
@require_GET
def favorites(request):
    """お気に入り一覧（シナリオ一覧とは別画面。お気に入り登録済み・公開中・未削除のみ）"""
    return _browse(request, favorites_only=True)


@login_required(login_url=LOGIN_URL)
@require_POST
def toggle_favorite(request, scenario_id):
    """お気に入りの登録・解除（イベント28）。解除は物理削除。"""
    scenario = public_scenarios().filter(pk=scenario_id).first()
    if scenario is None:
        return _error("NOT_FOUND", NOT_FOUND_SCENARIO, 404)
    try:
        with transaction.atomic():
            deleted, _ = Favorite.objects.filter(user=request.user, scenario=scenario).delete()
            if not deleted:
                Favorite.objects.create(user=request.user, scenario=scenario)
    except Exception:
        return _error("SAVE_ERROR", "保存に失敗しました", 500)
    return JsonResponse({
        "favorited": not deleted,
        "favorite_count": Favorite.objects.filter(scenario=scenario).count(),
    })


@login_required(login_url=LOGIN_URL)
@require_GET
def find_by_code(request, code):
    """コード検索（イベント52）：公開中・未削除のシナリオだけ見つかる"""
    import re

    if not re.match(CODE_PATTERN, code):
        return _error("BAD_REQUEST", "8桁の英数字で入力してね。", 400)
    scenario = with_counts(public_scenarios()).filter(share_code=code.upper()).first()
    if scenario is None:
        return _error("NOT_FOUND", "そのコードのシナリオは見つかりません", 404)
    favorited = Favorite.objects.filter(user=request.user, scenario=scenario).exists()
    return JsonResponse(detail_data(request.user, scenario, favorited))


@login_required(login_url=LOGIN_URL)
@require_GET
def detail(request, scenario_id):
    """シナリオ詳細（ユースケース記述「シナリオ詳細画面を表示する」、テスト仕様書 11）

    見せてよいのは、プレイ開始と同じ条件のシナリオだけ：ユーザー作成・未削除で、公開中または作成者本人。
    それ以外（存在しない・削除済み・他人の非公開）は区別せず NOT_FOUND（存在を隠す）。
    """
    scenario = (
        with_counts(Scenario.objects.filter(kind=Scenario.Kind.USER, deleted_at__isnull=True))
        .select_related("creator")
        .filter(Q(is_public=True) | Q(creator=request.user), pk=scenario_id)
        .first()
    )
    if scenario is None:
        return _error("NOT_FOUND", NOT_FOUND_SCENARIO, 404)
    favorited = Favorite.objects.filter(user=request.user, scenario=scenario).exists()
    return JsonResponse(detail_data(request.user, scenario, favorited))
