FROM python:3.11-slim

# Установка ffmpeg
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ставим setuptools с pkg_resources и pip
RUN pip install --upgrade pip "setuptools<75.0.0" wheel

COPY requirements.txt .

# Whisper требует pkg_resources, отключаем build isolation
RUN pip install --no-cache-dir --no-build-isolation -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
