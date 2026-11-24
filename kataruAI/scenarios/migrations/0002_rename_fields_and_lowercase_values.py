# 手書き：テーブル設計図.drawio に合わせて、誤字のフィールド名を直し、選択肢の値を小文字にそろえる
from django.db import migrations

KIND_MAP = {"CREATE": "user", "NOT_CREATE": "random"}
LEVEL_MAP = {"BEGINNER": "beginner", "INTERMEDIATE": "intermediate", "ADVANCED": "advanced"}


def forwards(apps, schema_editor):
    Scenario = apps.get_model("scenarios", "Scenario")
    for old, new in KIND_MAP.items():
        Scenario.objects.filter(kind=old).update(kind=new)
    for old, new in LEVEL_MAP.items():
        Scenario.objects.filter(difficulty=old).update(difficulty=new)


def backwards(apps, schema_editor):
    Scenario = apps.get_model("scenarios", "Scenario")
    for old, new in KIND_MAP.items():
        Scenario.objects.filter(kind=new).update(kind=old)
    for old, new in LEVEL_MAP.items():
        Scenario.objects.filter(difficulty=new).update(difficulty=old)


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0001_initial"),
    ]

    operations = [
        migrations.RenameField("scenario", "creatoe", "creator"),
        migrations.RenameField("scenario", "update_at", "updated_at"),
        migrations.RenameField("scenario", "delete_at", "deleted_at"),
        migrations.RunPython(forwards, backwards),
    ]
