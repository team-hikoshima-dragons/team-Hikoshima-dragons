FROM python:3.12

# pycファイルの生成を禁止
ENV PYTHONDONTWRITEBYTECODE=1

ENV PYTHONUNBUFFERED=1

WORKDIR /KataruAI_work

COPY requirements.txt /KataruAI_work/

# requirements.txtから必要なライブラリを一気にインストール
RUN pip install -r requirements.txt

COPY . /KataruAI_work/

RUN chmod 755 entrypoint.sh