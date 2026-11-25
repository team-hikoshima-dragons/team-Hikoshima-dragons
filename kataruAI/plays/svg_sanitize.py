"""AI が作った表情 SVG のサニタイズ（ユースケース記述「ゲームを開始する」【表情】）

方針：「許可したもの以外はすべて消す」。図形の要素と、色・座標などの属性だけを残す。
  - script・style・foreignObject・image・use などの要素は捨てる（中身ごと）
  - on〜属性・href・style 属性・url(...) や javascript: を含む値は捨てる（外部参照・スクリプト対策）
  - DOCTYPE／ENTITY を含むもの、大きすぎるもの、XML として読めないものは不採用（None）
パッケージを増やさないため、標準の xml.etree を使う（DOCTYPE を先に弾くので、実体展開の攻撃は受けない）。
表示は img タグ（data URL）で行うので、ブラウザ側でもスクリプトは動かない（二重の対策）。
"""
import base64
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_CHARS = 8000  # これより長いものは不採用（顔のアイコンには十分）

ALLOWED_TAGS = {"svg", "g", "circle", "ellipse", "rect", "path", "line", "polyline", "polygon"}
ALLOWED_ATTRS = {
    "viewbox", "width", "height", "x", "y", "cx", "cy", "r", "rx", "ry",
    "x1", "y1", "x2", "y2", "points", "d", "transform",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-linecap",
    "stroke-linejoin", "stroke-opacity", "opacity",
}
# 属性の値として許す文字（数字・英字・空白・記号の一部）。url( や : を含む値はここで落ちる
_SAFE_VALUE = re.compile(r"^[#0-9A-Za-z.,\-\s%()]*$")
_FORBIDDEN_IN_VALUE = ("url(", "javascript", "expression(", "data")


def _local(name):
    """'{namespace}tag' → 'tag'"""
    return name.rsplit("}", 1)[-1]


def _clean(element):
    """許可した要素・属性だけを持つ、新しい要素を作る。許可しない要素なら None"""
    tag = _local(element.tag).lower()
    if tag not in ALLOWED_TAGS:
        return None
    new = ET.Element(tag)
    for name, value in element.attrib.items():
        key = _local(name).lower()
        lowered = value.lower()
        if (
            key in ALLOWED_ATTRS
            and _SAFE_VALUE.match(value)
            and not any(bad in lowered for bad in _FORBIDDEN_IN_VALUE)
        ):
            new.set("viewBox" if key == "viewbox" else key, value)
    for child in element:
        cleaned = _clean(child)
        if cleaned is not None:
            new.append(cleaned)
    return new


def sanitize_svg(text):
    """サニタイズ済みの SVG 文字列を返す。使えないものは None"""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_SVG_CHARS:
        return None
    if re.search(r"<!(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        return None
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError:
        return None
    if _local(root.tag).lower() != "svg":
        return None
    cleaned = _clean(root)
    if cleaned is None or len(cleaned) == 0:  # 図形が1つも残らなければ不採用
        return None
    cleaned.set("xmlns", SVG_NS)
    return ET.tostring(cleaned, encoding="unicode")


def to_data_url(svg):
    """img タグの src に入れられる data URL にする"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
