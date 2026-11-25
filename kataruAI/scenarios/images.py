"""キャラクター画像（シナリオ作成でアップロードする画像）の保存と表示

設計書：PNG／JPEG／WebP・2MBまで（イベント39）。サーバーでも画像か確認し、ファイル名は UUID にする。
Scenario.image（TextField。テーブル設計図どおり）には MEDIA_ROOT からの相対パスを入れる。NULL＝標準シルエット。
"""
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.templatetags.static import static

MAX_IMAGE_BYTES = 2 * 1024 * 1024
# Pillow が判定した形式 → 保存するときの拡張子
ALLOWED_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
IMAGE_ERROR = "PNG・JPEG・WebPで、2MB以内の画像を選んでね。"
UPLOAD_DIR = "scenario_images"


def save_image(image):
    """検証済みの画像を UUID のファイル名で保存して、相対パスを返す。"""
    ext = ALLOWED_FORMATS[image.image.format]
    image.seek(0)
    return default_storage.save(f"{UPLOAD_DIR}/{uuid.uuid4().hex}.{ext}", image)


def delete_image(path):
    if path:
        default_storage.delete(path)


def image_url(scenario):
    """表示用のURL。画像がなければ標準シルエット。"""
    if scenario.image:
        return f"/{settings.MEDIA_URL.strip('/')}/{scenario.image}"
    return static("img/silhouette.svg")
