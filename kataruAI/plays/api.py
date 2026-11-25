"""プレイ画面用API（ゲスト・会員）。URL は plays/api_urls.py、マウント先は /api/plays/

POST /api/plays/              プレイ開始（お題を生成）
GET  /api/plays/{id}/         状態取得・再開
POST /api/plays/{id}/turns/   発言（body: text, turn_no）
POST /api/plays/{id}/give-up/ あきらめる
POST /api/plays/{id}/abort/   中断

ルール（AGENTS.md §6）：
- @csrf_exempt は使わない。React / JS は X-CSRFToken ヘッダーで送る。
- エラーは {"error": {"code": "...", "message": "..."}} の形で返す。
- 機嫌・疑い・理解度の数値はレスポンスに含めない。
- Gemini はトランザクションの外で呼ぶ。
- ゲストはセッション（guest_play.py）、会員はDB（member_play.py）で処理する。
"""
import functools
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import gemini, guest_play, member_play
from .guest_play import GUEST_DIFFICULTY, GUEST_SESSION_KEY, PlayError


def _error_response(error):
    """PlayError を JSON のレスポンスにする。extra（現在の状態など）は同じ階層に足す。"""
    body = {"error": {"code": error.code, "message": error.message}}
    body.update(error.extra)
    return JsonResponse(body, status=error.status)


def _api(view):
    """ビューの共通処理：PlayError をエラーレスポンスに変換する。"""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except PlayError as e:
            return _error_response(e)

    return wrapper


def _json_body(request):
    """リクエストの本文をJSON（dict）として読む。形が違えば BAD_REQUEST。"""
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise PlayError("BAD_REQUEST", "リクエストの形式が正しくありません。", 400)
    return data


def _save(request, play):
    """プレイをセッションに書き戻す（dict の中身を変えただけだとセッションが保存されないため）"""
    request.session[GUEST_SESSION_KEY] = play


@require_POST
@_api
def start(request):
    """プレイ開始。

    会員：body の scenario_id があればそのシナリオで（お題は生成しない）、
          なければ body の difficulty でランダムなお題を生成して開始する。
    ゲスト：難易度は初級固定なので、リクエストの difficulty は使わない（設計書 ①-a）。
    どちらも生成に成功してから、前のプレイを置き換える（設計書 ②-a：失敗時は前のプレイを残す）。
    """
    data = _json_body(request)
    if request.user.is_authenticated:
        if data.get("scenario_id") is not None:
            play = member_play.start_with_scenario(request.user, data["scenario_id"])
        else:
            play = member_play.start_random(
                request.user, data.get("difficulty"), gemini.generate_scenario
            )
        return JsonResponse(member_play.start_payload(play), status=201)

    try:
        scenario = gemini.generate_scenario(GUEST_DIFFICULTY)
    except gemini.GeminiError:
        # ブロックされた場合も、利用者の発言が原因ではないので同じ扱い（再試行を促す）
        raise PlayError("AI_ERROR", "お題を作れませんでした。もう一度ためしてね。", 502)

    play = guest_play.new_play(scenario, GUEST_DIFFICULTY, now=timezone.now())
    _save(request, play)
    return JsonResponse(
        {"play_id": play["id"], "play_url": guest_play.play_url(play["id"])}, status=201
    )


@require_GET
@_api
def detail(request, play_id):
    """状態取得：リロード時や再開時に、画面を復元するための情報を返す。"""
    if request.user.is_authenticated:
        return JsonResponse(member_play.public_view(member_play.find_play(request.user, play_id)))
    play = guest_play.find_play(request.session, play_id)
    return JsonResponse(guest_play.public_view(play))


@require_POST
@_api
def turn(request, play_id):
    """発言を処理して、キャラの返答と最新の様子を返す。"""
    data = _json_body(request)
    if request.user.is_authenticated:
        return JsonResponse(member_play.apply_turn(
            request.user, play_id, data.get("text"), data.get("turn_no"), gemini.generate_reply
        ))
    play = guest_play.find_play(request.session, play_id)
    payload = guest_play.apply_turn(
        play, data.get("text"), data.get("turn_no"), gemini.generate_reply, now=timezone.now()
    )
    _save(request, play)
    return JsonResponse(payload)


@require_POST
@_api
def give_up(request, play_id):
    """あきらめる：失敗（0点）にしてリザルトへ。"""
    if request.user.is_authenticated:
        return JsonResponse(member_play.give_up(request.user, play_id))
    play = guest_play.find_play(request.session, play_id)
    payload = guest_play.give_up(play, now=timezone.now())
    _save(request, play)
    return JsonResponse(payload)


@require_POST
@_api
def abort(request, play_id):
    """中断：プレイを中断にして、トップへ戻す。"""
    if request.user.is_authenticated:
        return JsonResponse(member_play.abort(request.user, play_id))
    play = guest_play.find_play(request.session, play_id)
    payload = guest_play.abort(play)
    _save(request, play)
    return JsonResponse(payload)
