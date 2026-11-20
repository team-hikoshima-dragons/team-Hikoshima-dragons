#!/bin/sh
# ↑ このファイルは sh（シェル）で実行する、という宣言。必ず1行目に書く
# このファイルはコンテナが起動したときに最初に実行する「コマンド集」
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 60