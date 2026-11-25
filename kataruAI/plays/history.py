"""プレイ履歴（一覧・詳細）の画面。会員だけが使う。

参照：ユースケース記述「履歴を表示する」「履歴詳細を表示する」、画面設計書「プレイ履歴」「プレイ履歴詳細」、
Drive のモック play_history.html・play_history_detail.html
  - 一覧：クリア・失敗・プレイ中を新しい順（中断は含めない）。難易度で絞り込み。1ページ20件
  - プレイ中の行はプレイ画面で再開（イベント51）、それ以外は詳細へ（イベント21）
  - 詳細：本人のプレイだけ。それ以外は「指定された履歴データが見つかりません」
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from . import game
from .guest_play import DIFFICULTY_LABELS, play_url
from .models import Play

PER_PAGE = 20
SHOWN_STATUSES = (game.CLEARED, game.FAILED, game.PLAYING)
FILTERS = (("all", "すべて"), ("beginner", "初級"), ("intermediate", "中級"), ("advanced", "上級"))
LOGIN_URL = reverse_lazy("accounts:login")
NOT_FOUND_MESSAGE = "指定された履歴データが見つかりません"


def _face(expression):
    return f"img/face-{expression or 'normal'}.svg"


def _row(play):
    last = play.turns.order_by("-turn_no").first()
    difficulty = play.scenario.difficulty
    return {
        "play": play,
        "url": play_url(play.pk) if play.status == game.PLAYING else f"/plays/history/{play.pk}/",
        "face_path": _face(last.expression if last else None),
        "difficulty": difficulty,
        "difficulty_label": DIFFICULTY_LABELS[difficulty],
    }


@login_required(login_url=LOGIN_URL)
@require_GET
def history_list(request):
    difficulty = request.GET.get("difficulty", "all")
    if difficulty not in dict(FILTERS):
        difficulty = "all"
    plays = (
        Play.objects.filter(user=request.user, status__in=SHOWN_STATUSES)
        .select_related("scenario")
        .order_by("-started_at", "-pk")
    )
    if difficulty != "all":
        plays = plays.filter(scenario__difficulty=difficulty)
    page = Paginator(plays, PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "plays/history.html", {
        "page": page,
        "rows": [_row(play) for play in page.object_list],
        "filters": FILTERS,
        "difficulty": difficulty,
    })


def _timeline(turns):
    """様子の変化：様子（state_text）が前のターンから変わったターンだけを並べる。最後のターンは必ず出す。"""
    items = []
    previous = None
    for i, turn in enumerate(turns):
        is_last = i == len(turns) - 1
        if turn.state_text != previous or is_last:
            items.append({"turn_no": turn.turn_no, "state": turn.state_text, "is_final": is_last})
        previous = turn.state_text
    return items


def _key_turn(turns):
    """解説：様子の変化が最も大きかったターン（3つの増減の絶対値の合計が最大。同じなら早いターン）"""
    best = None
    for turn in turns:
        size = abs(turn.delta_mood) + abs(turn.delta_suspicion) + abs(turn.delta_understanding)
        if best is None or size > best[0]:
            best = (size, turn)
    if best is None or not best[1].reason:
        return None
    return best[1]


@login_required(login_url=LOGIN_URL)
@ensure_csrf_cookie  # 「もう一度挑戦する」(top.js) が X-CSRFToken で POST するため
@require_GET
def history_detail(request, play_id):
    play = (
        Play.objects.filter(pk=play_id, user=request.user, status__in=SHOWN_STATUSES)
        .select_related("scenario")
        .first()
    )
    if play is None:
        return render(request, "plays/history_detail.html", {"not_found": NOT_FOUND_MESSAGE}, status=404)
    if play.status == game.PLAYING:
        return redirect(play_url(play.pk))  # プレイ中は続きから再開
    turns = list(play.turns.order_by("turn_no"))
    messages = []
    for turn in turns:
        if turn.user_message is not None:
            messages.append({"role": "user", "text": turn.user_message})
        if turn.ai_reply is not None:
            messages.append({"role": "model", "text": turn.ai_reply, "face_path": _face(turn.expression)})
    difficulty = play.scenario.difficulty
    return render(request, "plays/history_detail.html", {
        "play": play,
        "cleared": play.status == game.CLEARED,
        "difficulty": difficulty,
        "difficulty_label": DIFFICULTY_LABELS[difficulty],
        "face_path": "img/face-happy.svg" if play.status == game.CLEARED else "img/face-angry.svg",
        "messages_log": messages,
        "timeline": _timeline(turns),
        "key_turn": _key_turn(turns),
        "can_retry": play.scenario.deleted_at is None,
    })
