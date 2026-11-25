from django.views.generic.base import TemplateView
# from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from . import game, guest_play, member_play

class Index(TemplateView):
    template_name = "index.html"  # frontend/dist/index.html(npm run build で生成)

@method_decorator(ensure_csrf_cookie, name='dispatch')
class PlayPage(TemplateView):
    template_name = "index.html"


@ensure_csrf_cookie  # 「もう一度挑戦する」(top.js) が X-CSRFToken で POST するため
@require_GET
def result(request, play_id):
    """リザルト画面。ゲストはセッション、会員はDBからプレイを取り出す。

    - 他人のプレイ・存在しないプレイ・中断したプレイは 404（存在を隠す。AGENTS.md §6）
    - まだプレイ中ならプレイ画面へ戻す
    """
    if request.user.is_authenticated:
        try:
            play = member_play.find_play(request.user, play_id)
        except guest_play.PlayError:
            raise Http404
        if play.status == game.PLAYING:
            return redirect(guest_play.play_url(play.pk))
        if play.status not in (game.CLEARED, game.FAILED):
            raise Http404
        return render(request, "plays/result.html", {"result": member_play.result_view(play)})
    try:
        play = guest_play.find_play(request.session, play_id)
    except guest_play.PlayError:
        raise Http404
    if play["status"] == game.PLAYING:
        return redirect(guest_play.play_url(play_id))
    if play["status"] not in (game.CLEARED, game.FAILED):
        raise Http404
    return render(request, "plays/result.html", {"result": guest_play.result_view(play)})
