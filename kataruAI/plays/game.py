"""ゲームのルール計算（純Python。Django・DB・Gemini には依存しない）

仕様の出どころ：設計書「ユースケース記述_ゲームを開始する」の関連情報
  【難易度ごとの設定】【パラメータ】【スコア】
クリア判定とスコア計算はサーバー側のここだけで行う（AGENTS.md §6）。
AIの返答の内容ではクリアを判定しない。
"""
from dataclasses import dataclass, replace
from fractions import Fraction  # 小数の誤差を出さずに計算するために使う

# ---------- パラメータ ----------
PARAM_MIN = 0    # 機嫌・疑い・理解度の下限
PARAM_MAX = 100  # 機嫌・疑い・理解度の上限
DELTA_LIMIT = 15  # 1ターンあたりの増減の上限（−15〜＋15）

# 初期値は全難易度共通（設計書：機嫌50・疑い50・理解度0）
INITIAL_MOOD = 50
INITIAL_SUSPICION = 50
INITIAL_UNDERSTANDING = 0

# ---------- Play の status（AGENTS.md §6：この4つだけ） ----------
PLAYING = "playing"   # プレイ中
CLEARED = "cleared"   # クリア
FAILED = "failed"     # 失敗（ターン切れ・あきらめる）
ABORTED = "aborted"   # 中断（ロゴを押して抜けた）

FAILED_SCORE = 0  # 失敗は0点


@dataclass(frozen=True)
class Rules:
    """難易度ごとの設定（変更できないデータとして持つ）"""
    key: str                  # 難易度の名前（beginner など）
    turn_limit: int           # ターン上限
    clear_mood: int           # クリア条件：機嫌がこの値以上
    clear_understanding: int  # クリア条件：理解度がこの値以上
    clear_suspicion: int      # クリア条件：疑いがこの値以下
    coefficient: Fraction     # 難易度係数（1.5 などの誤差を避けるため Fraction）


# 設計書【難易度ごとの設定】の表をそのまま写したもの
RULES = {
    "beginner": Rules("beginner", 15, 70, 70, 30, Fraction(1)),
    "intermediate": Rules("intermediate", 12, 75, 75, 25, Fraction(3, 2)),
    "advanced": Rules("advanced", 10, 80, 80, 20, Fraction(2)),
}


def get_rules(difficulty):
    """難易度の名前から設定を返す。

    'beginner' でも 'BEGINNER'（モデルの値）でも受け取れるように小文字にそろえる。
    知らない名前のときは ValueError にする。
    """
    key = str(difficulty).lower()
    if key not in RULES:
        raise ValueError(f"unknown difficulty: {difficulty!r}")
    return RULES[key]


@dataclass(frozen=True)
class State:
    """プレイ中の状態（値を変えるときは新しい State を作る）"""
    mood: int = INITIAL_MOOD                    # 機嫌
    suspicion: int = INITIAL_SUSPICION          # 疑い
    understanding: int = INITIAL_UNDERSTANDING  # 理解度
    turns_used: int = 0                         # 使ったターン数


@dataclass(frozen=True)
class TurnResult:
    """1ターン処理した結果"""
    state: State             # 処理後の状態
    delta: dict              # ±15に丸めた後の増減（PlayTurn.delta_* に記録する値）
    status: str              # playing / cleared / failed のどれか
    remaining_turns: int     # 残りターン数
    score: object            # クリアなら点数、失敗なら0、プレイ中ならNone


def _clamp(value, low, high):
    """value を low〜high の範囲に収める"""
    return max(low, min(high, value))


def clamp_delta(value):
    """AIが返した増減値を −15〜＋15 に丸める。

    整数以外（文字列・小数・None・True/False）は ValueError にする。
    呼び出し側でこの例外を AI_ERROR として扱う。
    """
    # bool は int の仲間なので、True/False を弾くために先に調べる
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("delta must be int")
    return _clamp(value, -DELTA_LIMIT, DELTA_LIMIT)


def is_cleared(state, rules):
    """クリア条件を満たしているか（3つすべて満たす必要がある）"""
    return (
        state.mood >= rules.clear_mood                     # 機嫌が足りている
        and state.understanding >= rules.clear_understanding  # 理解度が足りている
        and state.suspicion <= rules.clear_suspicion       # 疑いが十分に低い
    )


def remaining_turns(state, rules):
    """残りターン数（0未満にはしない）"""
    return max(rules.turn_limit - state.turns_used, 0)


def calculate_score(state, rules):
    """クリア時のスコアを計算する（小数点以下切り捨て、最大1340点）

    基本点         = 機嫌×1.0 + 理解度×1.2 + (100−疑い)×1.5     （最大370）
    ターンボーナス = 残りターン ÷ ターン上限 × 300                （最大300）
    最終スコア     = (基本点 + ターンボーナス) × 難易度係数
    """
    # 1.2 や 1.5 を float で書くと誤差が出るので、分数（Fraction）で計算する
    base = (
        Fraction(state.mood)
        + Fraction(12, 10) * state.understanding
        + Fraction(15, 10) * (PARAM_MAX - state.suspicion)
    )
    # 早くクリアするほど高い点になる
    bonus = Fraction(remaining_turns(state, rules) * 300, rules.turn_limit)
    total = (base + bonus) * rules.coefficient
    # 分子 // 分母 で小数点以下を切り捨てる（値は常に正なので安全）
    return total.numerator // total.denominator


def process_turn(state, delta, rules):
    """1ターン分の処理をまとめて行う。

    手順：増減を±15に丸める → 0〜100に収めて加算 → 使用ターンを+1 → 判定
    delta は {"mood": int, "suspicion": int, "understanding": int}
    判定はクリアが先（最終ターンでクリア条件を満たしたらクリアにする）。
    """
    # AIの増減を±15に丸める（整数でなければここで ValueError）
    applied = {
        "mood": clamp_delta(delta["mood"]),
        "suspicion": clamp_delta(delta["suspicion"]),
        "understanding": clamp_delta(delta["understanding"]),
    }
    # 加算したあとに 0〜100 へ収め、使用ターンを1つ進めた新しい状態を作る
    new_state = replace(
        state,
        mood=_clamp(state.mood + applied["mood"], PARAM_MIN, PARAM_MAX),
        suspicion=_clamp(state.suspicion + applied["suspicion"], PARAM_MIN, PARAM_MAX),
        understanding=_clamp(
            state.understanding + applied["understanding"], PARAM_MIN, PARAM_MAX
        ),
        turns_used=state.turns_used + 1,
    )
    left = remaining_turns(new_state, rules)

    # ① クリア条件を満たした → クリア（スコアを計算する）
    if is_cleared(new_state, rules):
        return TurnResult(new_state, applied, CLEARED, left, calculate_score(new_state, rules))
    # ② 条件未達でターンが尽きた → 失敗（0点）
    if left == 0:
        return TurnResult(new_state, applied, FAILED, left, FAILED_SCORE)
    # ③ まだ続く
    return TurnResult(new_state, applied, PLAYING, left, None)
