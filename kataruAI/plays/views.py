import json
import time
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic.base import TemplateView
# from django.contrib.auth.mixins import LoginRequiredMixin

class Index(TemplateView, LoginRequiredMixin):
    template_name = "index.html"  # frontend/dist/index.html(npm run build で生成)

# Geminiが混雑(503)のときに試す最大回数
GEMINI_MAX_ATTEMPTS = 3


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