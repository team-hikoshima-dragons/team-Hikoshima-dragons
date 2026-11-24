import json
import time
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic.base import TemplateView
# from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from . import game, guest_play

class Index(TemplateView):
    template_name = "index.html"  # frontend/dist/index.html(npm run build で生成)

# Geminiが混雑(503)のときに試す最大回数
GEMINI_MAX_ATTEMPTS = 3

@method_decorator(ensure_csrf_cookie, name='dispatch')
class PlayPage(TemplateView):
    template_name = "index.html"


@ensure_csrf_cookie  # 「もう一度挑戦する」(top.js) が X-CSRFToken で POST するため
@require_GET
def result(request, play_id):
    """リザルト画面（ゲスト用）。プレイはセッションから取り出す。

    - 他人のプレイ・存在しないプレイ・中断したプレイは 404（存在を隠す。AGENTS.md §6）
    - まだプレイ中ならプレイ画面へ戻す
    """
    try:
        play = guest_play.find_play(request.session, play_id)
    except guest_play.PlayError:
        raise Http404
    if play["status"] == game.PLAYING:
        return redirect(guest_play.play_url(play_id))
    if play["status"] not in (game.CLEARED, game.FAILED):
        raise Http404
    return render(request, "plays/result.html", {"result": guest_play.result_view(play)})


@csrf_exempt      # 開発用:CSRFチェックを省略する(公開時は対策が必要)
@require_POST     # POST以外(ブラウザで直接開くなど)は拒否する
def chat(request):
    # APIキーが設定されているか確認
    if not settings.GEMINI_API_KEY:
        return JsonResponse(
            {"error": "GEMINI_API_KEY が設定されていません"}, status=500
        )

    try:
        # Reactから届いた会話履歴を取り出す
        data = json.loads(request.body)
        messages = data.get("messages", [])

        # Geminiが読める形に変換する(assistant側は "model" という名前)
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["text"]}]})

        # Gemini API を呼ぶ
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + settings.GEMINI_MODEL
            + ":generateContent"
        )
        for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
            res = requests.post(
                url,
                headers={
                    "x-goog-api-key": settings.GEMINI_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"contents": contents},
                timeout=60,
            )
            # 混雑(503)は一時的なので、少し待ってやり直す
            if res.status_code != 503 or attempt == GEMINI_MAX_ATTEMPTS:
                break
            time.sleep(attempt)
        res.raise_for_status()
        result = res.json()

        # 返事のテキストを取り出す
        candidates = result.get("candidates")
        if not candidates:
            return JsonResponse({"reply": "回答を生成できませんでした。"})

        parts = candidates[0].get("content", {}).get("parts", [])
        reply = "".join(p.get("text", "") for p in parts)
        return JsonResponse({"reply": reply})

    except requests.HTTPError as e:
        return JsonResponse(
            {"error": "Gemini APIエラー: " + e.response.text}, status=502
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)