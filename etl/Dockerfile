FROM python:3.12-slim
# libexpat1: dibutuhkan pyosmium (tidak ada di image slim)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir osmium==4.3.1 "psycopg[binary]==3.3.6"
ENV PYTHONUNBUFFERED=1
WORKDIR /etl
COPY load.py .
CMD ["python", "load.py"]
