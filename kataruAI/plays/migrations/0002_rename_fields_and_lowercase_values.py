# 手書き：テーブル設計図.drawio に合わせて、誤字のフィールド名を直し、status の値を小文字にそろえる
from django.db import migrations

STATUS_MAP = {"PLAYING": "playing", "CLEARED": "cleared", "FAILED": "failed", "ABORTED": "aborted"}


def forwards(apps, schema_editor):
    Play = apps.get_model("plays", "Play")
    for old, new in STATUS_MAP.items():
        Play.objects.filter(status=old).update(status=new)
    # save_chat_log を NOT NULL にする前に、NULL を「保存する」で埋める（設定の初期値と同じ）
    Play.objects.filter(save_chat_log__isnull=True).update(save_chat_log=True)


def backwards(apps, schema_editor):
    Play = apps.get_model("plays", "Play")
    for old, new in STATUS_MAP.items():
        Play.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):

    dependencies = [
        ("plays", "0001_initial"),
    ]

    operations = [
        migrations.RenameField("play", "supicion", "suspicion"),
        migrations.RenameField("play", "undestanding", "understanding"),
        migrations.RenameField("playturn", "delta_unserstanding", "delta_understanding"),
        migrations.RenameField("playturn", "create_at", "created_at"),
        migrations.RunPython(forwards, backwards),
    ]
