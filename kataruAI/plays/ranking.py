"""ランキング（ユースケース記述「ランキングを閲覧する」、画面設計書「ランキング」、イベント43）

集計対象：ランダムなお題をクリアしたプレイだけ（ユーザー作成シナリオは対象外）。期間は終了日時で判定する。
ユーザーごとにクリア数とスコア合計を出し、合計の高い順に並べる。削除したアカウント（is_active=False）は除く。
"""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET

from scenarios.models import Scenario

from . import game
from .models import Play

TOP_N = 50
PERIODS = (("today", "本日"), ("week", "1週間"), ("month", "1か月"), ("year", "1年間"), ("all", "総合"))
DIFFICULTIES = (("all", "すべて"), ("beginner", "初級"), ("intermediate", "中級"), ("advanced", "上級"))


def period_start(period, now=None):
    """期間の始まり。本日＝今日（日本時間）の0時、1週間・1か月・1年間＝今から7・30・365日前、総合＝None"""
    now = now or timezone.now()
    if period == "today":
        return timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    days = {"week": 7, "month": 30, "year": 365}.get(period)
    return now - timedelta(days=days) if days else None


def aggregate(start=None, difficulty="all", end=None):
    """[{"user_id", "username", "clears", "total", "rank"}, ...] を合計の高い順で返す。

    順位は同点なら同じ順位（1, 2, 2, 4 …）。並びは合計 → クリア数 → ユーザー名の順。
    """
    plays = Play.objects.filter(
        status=game.CLEARED, scenario__kind=Scenario.Kind.RANDOM, user__is_active=True,
    )
    if start is not None:
        plays = plays.filter(finished_at__gte=start)
    if end is not None:
        plays = plays.filter(finished_at__lt=end)
    if difficulty != "all":
        plays = plays.filter(scenario__difficulty=difficulty)
    rows = list(
        plays.values("user_id", "user__username")
        .annotate(clears=Count("pk"), total=Sum("score"))
        .order_by("-total", "-clears", "user__username")
    )
    result = []
    for i, row in enumerate(rows):
        rank = result[-1]["rank"] if result and result[-1]["total"] == row["total"] else i + 1
        result.append({
            "user_id": row["user_id"], "username": row["user__username"],
            "clears": row["clears"], "total": row["total"], "rank": rank,
            "total_text": f"{row['total']:,}",  # 3桁カンマ区切り
        })
    return result


def rank_of(user_id, rows):
    return next((row["rank"] for row in rows if row["user_id"] == user_id), None)


@login_required(login_url=reverse_lazy("accounts:login"))
@require_GET
def ranking(request):
    period = request.GET.get("period", "week")
    if period not in dict(PERIODS):
        period = "week"
    difficulty = request.GET.get("difficulty", "all")
    if difficulty not in dict(DIFFICULTIES):
        difficulty = "all"
    rows = aggregate(period_start(period), difficulty)
    top = rows[:TOP_N]
    # 自分が50位より下なら、表の最後に自分の行を足す
    me = next((row for row in rows[TOP_N:] if row["user_id"] == request.user.pk), None)
    return render(request, "plays/ranking.html", {
        "rows": top,
        "me_below": me,
        "period": period,
        "difficulty": difficulty,
        "periods": PERIODS,
        "difficulties": DIFFICULTIES,
    })
