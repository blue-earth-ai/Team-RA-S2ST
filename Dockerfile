# ベースイメージ
FROM python:3.12-slim

# 作業ディレクトリ
WORKDIR /app

# 必要なパッケージのインストール
# ffmpeg: 音声処理(pydub/moviepy等)で必須
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリのコピー
COPY . .

# 権限設定 (Coolify/Dockerでの書き込み権限用)
RUN chmod -R 777 /app

# ポート公開 (Coolifyの設定に合わせて5000)
EXPOSE 5000

# 起動コマンド
# ★修正ポイント: timeoutを300秒に延長し、メモリ節約のためワーカーを2に設定
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "--timeout", "300", "app:app"]