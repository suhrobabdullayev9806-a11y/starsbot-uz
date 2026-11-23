# ===================================================================
# Dockerfile - Auto Stars bot konteyner tasviri
# Build:   docker build -t auto-stars-bot .
# Run:     docker compose up -d
# ===================================================================

FROM python:3.12-slim

# Non-interaktiv o'rnatish
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Xavfsizlik: root bo'lmagan foydalanuvchi
RUN useradd --create-home --shell /usr/sbin/nologin botuser

# Qaramliklar avval (Docker caching uchun)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha fayllari
COPY src ./src
COPY assets ./assets

# Ma'lumotlar bazasi papkasi
RUN mkdir -p data && chown -R botuser:botuser /app
USER botuser

# WebApp admin panel porti
EXPOSE 8080

# Botni ishga tushirish
CMD ["python", "-m", "src.main"]