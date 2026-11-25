from django import forms

from .images import ALLOWED_FORMATS, IMAGE_ERROR, MAX_IMAGE_BYTES
from .models import Scenario

TITLE_MAX = 40
DESCRIPTION_MAX = 400


class ScenarioCreateForm(forms.Form):
    """シナリオ作成の入力（画面設計書 シナリオ作成・イベント39・41）。サーバー側の検証の本体。"""
    title = forms.CharField(max_length=TITLE_MAX, error_messages={
        "required": "タイトルを入力してね。",
        "max_length": f"タイトルは{TITLE_MAX}文字以内にしてね。",
    })
    difficulty = forms.ChoiceField(choices=Scenario.Level.choices, error_messages={
        "required": "難易度を選んでね。",
        "invalid_choice": "難易度を選んでね。",
    })
    description = forms.CharField(max_length=DESCRIPTION_MAX, error_messages={
        "required": "説明を入力してね。",
        "max_length": f"説明は{DESCRIPTION_MAX}文字以内にしてね。",
    })
    # ImageField（フォーム）で「本当に画像か」を Pillow で確かめる
    character_image = forms.ImageField(required=False, error_messages={
        "invalid_image": IMAGE_ERROR,
        "invalid": IMAGE_ERROR,
    })

    def clean_character_image(self):
        image = self.cleaned_data.get("character_image")
        if not image:
            return None
        fmt = getattr(getattr(image, "image", None), "format", None)
        if image.size > MAX_IMAGE_BYTES or fmt not in ALLOWED_FORMATS:
            raise forms.ValidationError(IMAGE_ERROR)
        return image
