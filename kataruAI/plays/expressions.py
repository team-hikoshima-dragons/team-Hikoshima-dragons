"""ランダムなお題の生成と、表情差分 SVG の生成を並行して行う（2026-11-25 丸山の判断）

- お題の生成に失敗したら GeminiError をそのまま上げる（呼び出し側で AI_ERROR にする）
- 表情 SVG の生成に失敗しても、ゲームは止めない（None を返し、画面は固定の SVG を使う）
- 2つを同時に呼ぶので、待ち時間はお題の生成だけのときと変わらない（最大25秒）
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from .gemini import EXPRESSIONS
from .svg_sanitize import to_data_url

logger = logging.getLogger(__name__)


def generate_scenario_and_expressions(difficulty, generate_scenario, generate_expressions):
    """(お題の dict, {表情: SVG} または None) を返す"""
    with ThreadPoolExecutor(max_workers=2) as pool:
        scenario_future = pool.submit(generate_scenario, difficulty)
        expressions_future = pool.submit(generate_expressions, difficulty)
        scenario = scenario_future.result()  # 失敗ならここで GeminiError
        try:
            expressions = expressions_future.result()
        except Exception as e:  # SVG の失敗はゲームを止めない
            logger.warning("expression svg generation failed: %s", getattr(e, "code", type(e).__name__))
            expressions = None
    return scenario, expressions


def image_urls(expressions):
    """{表情: SVG} → {表情: data URL}。4つそろっていなければ None（画面は固定の SVG を使う）"""
    if not expressions or any(not expressions.get(name) for name in EXPRESSIONS):
        return None
    return {name: to_data_url(expressions[name]) for name in EXPRESSIONS}
