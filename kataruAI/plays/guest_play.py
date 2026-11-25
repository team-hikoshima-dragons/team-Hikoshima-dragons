"""ゲスト用プレイの進行ロジック（純Python。Django の request には依存しない）

設計書「ゲームを開始する」③-a：ゲストのお題とプレイはサーバーのセッションに保持し、
Scenario・Play テーブルには保存しない（AGENTS.md §6）。

プレイの情報は dict 1つにまとめて、セッションに入れる。
  - 数値（機嫌・疑い・理解度）はサーバー側のセッションにだけある。画面には返さない。
  - 会話履歴もサーバーが持つ。フロントから受け取るのは今回の発言だけ。
このファイルの関数は、セッションの代わりに普通の dict でも動くので単体テストできる。
"""
import uuid
from dataclasses import asdict
from datetime import datetime

from . import game
from .gemini import GeminiError

GUEST_SESSION_KEY = "guest_play"  # セッションに入れるときのキー
GUEST_DIFFICULTY = "beginner"     # ゲストは初級固定（設計書 ①-a）
MAX_MESSAGE_LENGTH = 120          # 発言の上限（サーバー側でも必ず検証する）
INITIAL_STATE_TEXT = "迷っている"  # ゲーム開始直後の「いまの様子」
INITIAL_EXPRESSION = "normal"     # ゲーム開始直後の表情
DEFAULT_TEXT_SPEED = "normal"     # ゲストの設定は初期値（会員の設定は後で対応）

# お題として保存する項目
SCENARIO_KEYS = ("title", "description", "character_name", "character_intro", "goal", "condition")


class PlayError(Exception):
    """APIのエラー。{"error": {"code", "message"}} の形で返すための情報を持つ。

    code   : BLOCKED / AI_ERROR / TURN_MISMATCH / NOT_FOUND / NOT_PLAYING（AGENTS.md）
             ＋ BAD_REQUEST（入力の形が不正。AGENTS.md の一覧にないため要確認）
    status : HTTP ステータス
    extra  : エラーと一緒に返したい情報（TURN_MISMATCH のとき現在の状態）
    """

    def __init__(self, code, message, status, extra=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra or {}


# ---------- URL（設計書：プレイ画面 /plays/{id}/、リザルト /plays/{id}/result/） ----------
def play_url(play_id):
    return f"/plays/{play_id}/"


def result_url(play_id):
    return f"/plays/{play_id}/result/"


# ---------- 作成・取得 ----------
def new_play(scenario, difficulty=GUEST_DIFFICULTY, now=None):
    """お題から、ゲスト用の新しいプレイ（dict）を作る。数値は初期値から始める。

    now : 開始日時（timezone.now() の値）。クリアタイムの計算に使う。
          このファイルは Django に依存しないので、呼び出し側（api.py）から受け取る。
    """
    rules = game.get_rules(difficulty)
    return {
        "id": uuid.uuid4().hex,  # 推測されにくいID
        "difficulty": rules.key,
        "scenario": {key: scenario[key] for key in SCENARIO_KEYS},
        "state": asdict(game.State()),  # 機嫌50・疑い50・理解度0・使用ターン0
        "history": [],                  # [{"role": "user"|"model", "text": ...}]
        "state_text": INITIAL_STATE_TEXT,
        "expression": INITIAL_EXPRESSION,
        "status": game.PLAYING,
        "score": None,
        "started_at": _to_iso(now),   # 開始日時（ISO形式の文字列。セッションに入れられる形）
        "finished_at": None,          # 終了日時（クリア・失敗したときに入れる）
    }


def _to_iso(moment):
    """日時を文字列にする。日時が渡されなかったら None（時間は記録しない）"""
    return moment.isoformat() if moment else None


def find_play(session, play_id):
    """セッションから、指定IDの自分のプレイを取り出す。

    他人のプレイ・存在しないプレイは区別せず NOT_FOUND にする（存在を隠す。AGENTS.md §6 IDOR対策）。
    """
    play = session.get(GUEST_SESSION_KEY)
    if not isinstance(play, dict) or play.get("id") != play_id:
        raise PlayError("NOT_FOUND", "プレイが見つかりません。", 404)
    return play


def _state_of(play):
    return game.State(**play["state"])


# ---------- 画面に返す内容 ----------
def public_view(play):
    """画面に返してよい情報だけを集める。機嫌・疑い・理解度の数値は絶対に含めない。"""
    rules = game.get_rules(play["difficulty"])
    scenario = play["scenario"]
    view = {
        "play_id": play["id"],
        "status": play["status"],
        "title": scenario["title"],
        "difficulty": play["difficulty"],
        "turn_limit": rules.turn_limit,
        "turns_left": game.remaining_turns(_state_of(play), rules),
        "character": {"name": scenario["character_name"], "intro": scenario["character_intro"]},
        "description": scenario["description"],
        "goal": scenario["goal"],
        "condition": scenario["condition"],
        "messages": list(play["history"]),
        "state": play["state_text"],
        "expression": play["expression"],
        "text_speed": DEFAULT_TEXT_SPEED,
    }
    # 終わっているプレイにはリザルトのURLを付ける
    if play["status"] in (game.CLEARED, game.FAILED):
        view["result_url"] = result_url(play["id"])
    return view


# ---------- 発言の検証 ----------
def _validate_message(text):
    """発言を検証する（空・120文字超は不可）。問題なければ前後の空白を除いて返す。"""
    if not isinstance(text, str) or not text.strip():
        raise PlayError("BAD_REQUEST", "発言を入力してください。", 400)
    if len(text) > MAX_MESSAGE_LENGTH:
        raise PlayError("BAD_REQUEST", f"発言は{MAX_MESSAGE_LENGTH}文字以内で入力してください。", 400)
    return text.strip()


# ---------- ターンの処理 ----------
def apply_turn(play, text, turn_no, generate_reply, now=None):
    """1ターン分の発言を処理して、画面に返す内容を返す。

    generate_reply : gemini.generate_reply と同じ引数の関数（テストで差し替えられるようにしている）
    エラーのとき（BLOCKED / AI_ERROR など）は play を一切変更しない＝ターンを消費しない。
    """
    # ① プレイ中でなければ処理しない（クリア済みの二重送信など）
    if play["status"] != game.PLAYING:
        raise PlayError("NOT_PLAYING", "このプレイは終了しています。", 409)

    text = _validate_message(text)
    rules = game.get_rules(play["difficulty"])
    state = _state_of(play)

    # ② turn_no がずれていたら処理せず、現在の状態を返す（二重送信・再送対策）
    if isinstance(turn_no, bool) or turn_no != state.turns_used + 1:
        raise PlayError(
            "TURN_MISMATCH", "ターン番号がずれています。最新の状態を読み込みます。", 409,
            extra={"play": public_view(play)},
        )

    # ③ AIに返答を作らせる（失敗してもターンは消費しない）
    try:
        ai = generate_reply(play["scenario"], play["difficulty"], play["history"], text, state)
    except GeminiError as e:
        if e.code == "BLOCKED":
            raise PlayError("BLOCKED", "その発言は送れないよ。言い方を変えてみてね（ターンは消費していません）", 400)
        raise PlayError("AI_ERROR", "通信エラーが発生しました。もう一度ためしてね。", 502)

    # ④ 増減を丸めて加算し、クリア・失敗を判定する（判定はここ＝サーバー側だけ）
    try:
        result = game.process_turn(state, ai["delta"], rules)
    except ValueError:
        raise PlayError("AI_ERROR", "通信エラーが発生しました。もう一度ためしてね。", 502)

    # ⑤ ここまで成功したら、はじめて状態を書き換える
    play["history"] = play["history"] + [
        {"role": "user", "text": text},
        {"role": "model", "text": ai["reply"]},
    ]
    play["state"] = asdict(result.state)
    play["state_text"] = ai["state"]
    play["expression"] = ai["expression"]
    if result.status != game.PLAYING:
        play["status"] = result.status
        play["score"] = result.score  # クリア時は点数、失敗時は0
        play["finished_at"] = _to_iso(now)

    # ⑥ 画面に返す内容（数値は返さない）
    payload = {
        "reply": ai["reply"],
        "state": ai["state"],
        "expression": ai["expression"],
        "turns_left": result.remaining_turns,
        "status": result.status,
    }
    if result.status != game.PLAYING:
        payload["result_url"] = result_url(play["id"])
    return payload


# ---------- あきらめる・中断 ----------
def give_up(play, now=None):
    """あきらめる：失敗（0点）にして、リザルトのURLを返す。プレイ中でなければ何も変えない。"""
    if play["status"] != game.PLAYING:
        raise PlayError("NOT_PLAYING", "このプレイは終了しています。", 409)
    play["status"] = game.FAILED
    play["score"] = game.FAILED_SCORE
    play["finished_at"] = _to_iso(now)
    return {"result_url": result_url(play["id"])}


def abort(play):
    """中断：状態を中断にして、トップ(未ログイン)へ戻す。プレイ中でなければ何も変えない。"""
    if play["status"] != game.PLAYING:
        raise PlayError("NOT_PLAYING", "このプレイは終了しています。", 409)
    play["status"] = game.ABORTED
    return {"redirect_url": "/"}  # ゲストはトップ(未ログイン)へ


# ---------- リザルト画面に渡す内容 ----------
DIFFICULTY_LABELS = {"beginner": "初級", "intermediate": "中級", "advanced": "上級"}


def _clear_seconds(play):
    """開始から終了までの秒数。どちらかが記録されていなければ None"""
    if not play.get("started_at") or not play.get("finished_at"):
        return None
    elapsed = datetime.fromisoformat(play["finished_at"]) - datetime.fromisoformat(play["started_at"])
    return max(int(elapsed.total_seconds()), 0)


def result_view(play):
    """リザルト画面（result.html）に渡す内容を作る。数値（機嫌など）は含めない。

    クリアタイムはクリアしたときだけ表示する（失敗のときは None）。
    ゲストの結果はランキング・履歴に載せないので、順位やベスト記録は持たない。
    """
    rules = game.get_rules(play["difficulty"])
    cleared = play["status"] == game.CLEARED
    seconds = _clear_seconds(play) if cleared else None
    return {
        "cleared": cleared,
        "score": play["score"] or 0,
        "title": play["scenario"]["title"],
        "character_name": play["scenario"]["character_name"],
        "difficulty": play["difficulty"],
        "difficulty_label": DIFFICULTY_LABELS[play["difficulty"]],
        "turns_used": _state_of(play).turns_used,
        "turn_limit": rules.turn_limit,
        # 「4:32」（分:秒）の形。記録がなければ「—」。失敗のときは画面側でカードごと隠す
        "clear_time_text": "—" if seconds is None else f"{seconds // 60}:{seconds % 60:02d}",
        # 結果カードの顔：クリアは笑顔、失敗は怒り顔（モックの result.html に合わせた固定の2種類）
        "face_path": "img/face-happy.svg" if cleared else "img/face-angry.svg",
    }
