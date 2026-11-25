"""会員用プレイの進行ロジック（DB の Scenario・Play・PlayTurn に保存する）

設計書「ユースケース記述_ゲームを開始する」の会員の流れ。guest_play.py と同じ形にそろえている。
  - Gemini はトランザクションの外で呼ぶ（AGENTS.md §6）
  - 新しく始めるときは、AI生成に成功してから1つのトランザクションで「前のプレイを中断 → 新規作成」
  - 機嫌・疑い・理解度の数値は画面に返さない。会話履歴はサーバー（DB）が持つ
  - 他人のプレイ・存在しないプレイは区別せず NOT_FOUND（IDOR対策）
  - チャット履歴の自動保存が OFF のプレイは、プレイ中だけ会話をDBに持ち、
    終わった時点（クリア・失敗・中断）で発言と返答を消す（2026-11-24 丸山の判断：案A）
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserSetting
from scenarios.images import image_url
from scenarios.models import Scenario

from . import game
from .gemini import GeminiError
from .guest_play import (
    DIFFICULTY_LABELS,
    INITIAL_EXPRESSION,
    INITIAL_STATE_TEXT,
    SCENARIO_KEYS,
    PlayError,
    _validate_message,
    play_url,
    result_url,
)
from .models import Play, PlayTurn

AI_ERROR_MESSAGE = "通信エラーが発生しました。もう一度ためしてね。"


# ---------- 作成 ----------
def start_random(user, difficulty, generate_scenario):
    """ランダムなお題で開始する（画面設計書 イベント12）。

    generate_scenario : gemini.generate_scenario と同じ引数の関数（テストで差し替えられるように）
    """
    if not isinstance(difficulty, str) or difficulty not in game.RULES:
        raise PlayError("BAD_REQUEST", "難易度を選んでください。", 400)
    # ① AIでお題を作る（トランザクションの外。失敗したら前のプレイはそのまま＝②-a）
    try:
        data = generate_scenario(difficulty)
    except GeminiError:
        raise PlayError("AI_ERROR", "お題を作れませんでした。もう一度ためしてね。", 502)
    # ② 成功したら、シナリオ（ランダム・非公開）を保存して、プレイを作る
    with transaction.atomic():
        scenario = Scenario.objects.create(
            creator=user,
            kind=Scenario.Kind.RANDOM,
            difficulty=difficulty,
            is_public=False,  # ランダムなお題は常に非公開
            share_code=None,  # 共有コードはユーザーが作成したシナリオだけに発行する
            **{key: data[key] for key in SCENARIO_KEYS},
        )
        return _create_play(user, scenario)


def start_with_scenario(user, scenario_id):
    """既存のシナリオで開始する（イベント22「もう一度挑戦する」・イベント29）。お題は生成しない。

    開始できるのは「未削除 かつ（公開中 または 作成者が本人）」のシナリオだけ（AGENTS.md §6）。
    """
    scenario = _playable_scenario(user, scenario_id)
    with transaction.atomic():
        return _create_play(user, scenario)


def _playable_scenario(user, scenario_id):
    not_found = PlayError("NOT_FOUND", "指定したシナリオは存在しないか、削除されています。", 404)
    if isinstance(scenario_id, bool):
        raise not_found
    try:
        pk = int(scenario_id)
    except (TypeError, ValueError):
        raise not_found
    scenario = Scenario.objects.filter(pk=pk, deleted_at__isnull=True).first()
    if scenario is None or not (scenario.is_public or scenario.creator_id == user.pk):
        raise not_found
    return scenario


def _create_play(user, scenario):
    """プレイ中のプレイを中断にしてから、新しいプレイを作る（トランザクションの中で呼ぶ）。"""
    # 同じユーザーの開始が同時に来ても1件にするため、ユーザーの行をロックする
    User.objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    for old in Play.objects.select_for_update().filter(user=user, status=game.PLAYING):
        _finish(old, game.ABORTED, None, now)
    setting, _ = UserSetting.objects.get_or_create(user=user)
    rules = game.get_rules(scenario.difficulty)
    return Play.objects.create(
        user=user,
        scenario=scenario,
        status=game.PLAYING,
        turn_limit=rules.turn_limit,
        save_chat_log=setting.auto_save_chat,  # 開始時の設定をコピーする
    )


def _finish(play, status, score, now):
    """プレイを終わらせる（クリア・失敗・中断）。自動保存OFFなら会話を消す。"""
    play.status = status
    play.score = score  # 中断は None（記録しない）
    play.finished_at = now
    play.save(update_fields=["status", "score", "finished_at"])
    if not play.save_chat_log:
        play.turns.update(user_message=None, ai_reply=None)


# ---------- 取得 ----------
def find_play(user, play_id):
    """ログインユーザー本人のプレイを取り出す。他人・存在しないものは NOT_FOUND。"""
    try:
        pk = int(play_id)
    except (TypeError, ValueError):
        pk = None
    play = (
        Play.objects.select_related("scenario", "user").filter(pk=pk, user=user).first()
        if pk is not None else None
    )
    if play is None:
        raise PlayError("NOT_FOUND", "プレイが見つかりません。", 404)
    return play


def _rules(play):
    return game.get_rules(play.scenario.difficulty)


def _state(play):
    return game.State(play.mood, play.suspicion, play.understanding, play.turns_used)


def _history(play):
    """Gemini と画面に渡す会話履歴（発言・返答が消されたターンは含めない）"""
    history = []
    for turn in play.turns.order_by("turn_no"):
        if turn.user_message is not None:
            history.append({"role": "user", "text": turn.user_message})
        if turn.ai_reply is not None:
            history.append({"role": "model", "text": turn.ai_reply})
    return history


def _scenario_dict(play):
    return {key: getattr(play.scenario, key) or "" for key in SCENARIO_KEYS}


def public_view(play):
    """画面に返してよい情報だけを集める（guest_play.public_view と同じ形）。数値は含めない。"""
    rules = _rules(play)
    scenario = play.scenario
    last = play.turns.order_by("-turn_no").first()
    setting, _ = UserSetting.objects.get_or_create(user_id=play.user_id)
    view = {
        "play_id": str(play.pk),
        "status": play.status,
        "title": scenario.title,
        "difficulty": rules.key,
        "turn_limit": play.turn_limit,
        "turns_left": game.remaining_turns(_state(play), rules),
        "character": {"name": scenario.character_name, "intro": scenario.character_intro},
        "description": scenario.description,
        "goal": scenario.goal,
        "condition": scenario.condition,
        "messages": _history(play),
        "state": last.state_text if last else INITIAL_STATE_TEXT,
        "expression": last.expression if last else INITIAL_EXPRESSION,
        "text_speed": setting.text_speed,
        "player_initial": play.user.username[:1],  # 自分の吹き出しのアイコン（ユーザー名の頭文字）
        # ユーザー作成シナリオは登録画像（なければ標準シルエット）を使う。ランダムなお題は表情のSVG
        "image_url": image_url(scenario) if scenario.kind == Scenario.Kind.USER else None,
    }
    if play.status in (game.CLEARED, game.FAILED):
        view["result_url"] = result_url(play.pk)
    return view


# ---------- ターン ----------
def apply_turn(user, play_id, text, turn_no, generate_reply):
    """1ターン分の発言を処理する。エラーのときはDBを変えない＝ターンを消費しない。"""
    play = find_play(user, play_id)
    if play.status != game.PLAYING:
        raise PlayError("NOT_PLAYING", "このプレイは終了しています。", 409)
    text = _validate_message(text)
    rules = _rules(play)
    state = _state(play)
    _check_turn_no(play, turn_no, state)

    # AIに返答を作らせる（トランザクションの外）
    try:
        ai = generate_reply(_scenario_dict(play), rules.key, _history(play), text, state)
    except GeminiError as e:
        if e.code == "BLOCKED":
            raise PlayError("BLOCKED", "その発言は送れないよ。言い方を変えてみてね（ターンは消費していません）", 400)
        raise PlayError("AI_ERROR", AI_ERROR_MESSAGE, 502)
    try:
        result = game.process_turn(state, ai["delta"], rules)
    except ValueError:
        raise PlayError("AI_ERROR", AI_ERROR_MESSAGE, 502)

    with transaction.atomic():
        # AIを待っている間に別の送信が処理されていないか、ロックしてもう一度確かめる
        locked = Play.objects.select_for_update().select_related("scenario").get(pk=play.pk)
        if locked.status != game.PLAYING:
            raise PlayError("NOT_PLAYING", "このプレイは終了しています。", 409)
        _check_turn_no(locked, turn_no, _state(locked))

        new = result.state
        PlayTurn.objects.create(
            play=locked,
            turn_no=new.turns_used,
            user_message=text,
            ai_reply=ai["reply"],
            delta_mood=result.delta["mood"],
            delta_suspicion=result.delta["suspicion"],
            delta_understanding=result.delta["understanding"],
            mood_after=new.mood,
            suspicion_after=new.suspicion,
            understanding_after=new.understanding,
            state_text=ai["state"],
            expression=ai["expression"],
            reason=ai.get("reason") or "",
        )
        locked.mood = new.mood
        locked.suspicion = new.suspicion
        locked.understanding = new.understanding
        locked.turns_used = new.turns_used
        locked.save(update_fields=["mood", "suspicion", "understanding", "turns_used"])
        if result.status != game.PLAYING:
            _finish(locked, result.status, result.score, timezone.now())

    payload = {
        "reply": ai["reply"],
        "state": ai["state"],
        "expression": ai["expression"],
        "turns_left": result.remaining_turns,
        "status": result.status,
    }
    if result.status != game.PLAYING:
        payload["result_url"] = result_url(play.pk)
    return payload


def _check_turn_no(play, turn_no, state):
    """turn_no がずれていたら処理せず、現在の状態を返す（二重送信・再送対策）"""
    if isinstance(turn_no, bool) or turn_no != state.turns_used + 1:
        raise PlayError(
            "TURN_MISMATCH", "ターン番号がずれています。最新の状態を読み込みます。", 409,
            extra={"play": public_view(play)},
        )


# ---------- あきらめる・中断 ----------
def _lock_playing(user, play_id):
    play = find_play(user, play_id)
    locked = Play.objects.select_for_update().get(pk=play.pk)
    if locked.status != game.PLAYING:
        raise PlayError("NOT_PLAYING", "このプレイは終了しています。", 409)
    return locked


def give_up(user, play_id):
    """あきらめる：失敗（0点）にしてリザルトへ（④-b）。"""
    with transaction.atomic():
        play = _lock_playing(user, play_id)
        _finish(play, game.FAILED, game.FAILED_SCORE, timezone.now())
    return {"result_url": result_url(play.pk)}


def abort(user, play_id):
    """中断：トップ(ログイン済み)へ戻す（④-c）。スコアは記録しない。"""
    with transaction.atomic():
        play = _lock_playing(user, play_id)
        _finish(play, game.ABORTED, None, timezone.now())
    return {"redirect_url": "/"}


# ---------- リザルト ----------
def today_rank(play):
    """今日のランキング順位（ランダムなお題をクリアしたときだけ。それ以外は None）

    数え方（2026-11-24 丸山の判断：案A）：今日（日本時間）に終了した、このプレイと同じ難易度の
    「ランダムなお題のクリア」のスコア合計で並べたときの、自分の順位。
    """
    if play.status != game.CLEARED or play.scenario.kind != Scenario.Kind.RANDOM:
        return None
    # ランキング画面と同じ集計（plays/ranking.py）を、このプレイを終えた日・同じ難易度で行う
    from . import ranking

    start = ranking.period_start("today", play.finished_at)
    rows = ranking.aggregate(start, play.scenario.difficulty, end=start + timedelta(days=1))
    return ranking.rank_of(play.user_id, rows)


def is_new_best(play):
    """自己ベスト更新か（ユーザー作成シナリオをクリアし、それまでの自分のクリアの最高点を超えたとき。
    はじめてのクリアも更新とみなす）。ランダムなお題は毎回別のお題なので対象外（画面設計書 リザルト No.9）"""
    if play.status != game.CLEARED or play.scenario.kind != Scenario.Kind.USER:
        return False
    previous = (
        Play.objects.filter(user_id=play.user_id, scenario_id=play.scenario_id, status=game.CLEARED,
                            finished_at__lt=play.finished_at)
        .exclude(pk=play.pk)
        .order_by("-score")
        .values_list("score", flat=True)
        .first()
    )
    return previous is None or play.score > previous


def result_view(play):
    """リザルト画面に渡す内容（guest_play.result_view と同じ形＋会員だけの項目）。"""
    rules = _rules(play)
    cleared = play.status == game.CLEARED
    seconds = None
    if cleared and play.started_at and play.finished_at:
        seconds = max(int((play.finished_at - play.started_at).total_seconds()), 0)
    return {
        "play_id": play.pk,
        "cleared": cleared,
        "score": play.score or 0,
        "title": play.scenario.title,
        "character_name": play.scenario.character_name,
        "difficulty": rules.key,
        "difficulty_label": DIFFICULTY_LABELS[rules.key],
        "turns_used": play.turns_used,
        "turn_limit": play.turn_limit,
        "clear_time_text": "—" if seconds is None else f"{seconds // 60}:{seconds % 60:02d}",
        "face_path": "img/face-happy.svg" if cleared else "img/face-angry.svg",
        # ユーザー作成シナリオは登録画像を出す（None ならテンプレートが face_path を使う）
        "image_url": image_url(play.scenario) if play.scenario.kind == Scenario.Kind.USER else None,
        "today_rank": today_rank(play),
        "new_best": is_new_best(play),
        # もう一度挑戦する（イベント22）：同じシナリオ。削除済みならボタンを無効化する
        "scenario_id": play.scenario_id,
        "can_retry": play.scenario.deleted_at is None,
    }


def start_payload(play):
    return {"play_id": str(play.pk), "play_url": play_url(play.pk)}
