FROM python:3.12-slim
RUN pip install --no-cache-dir "psycopg[binary]==3.3.6"
ENV PYTHONUNBUFFERED=1
WORKDIR /etl
COPY load.py .
CMD ["python", "load.py"]
