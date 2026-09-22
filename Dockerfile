FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY sessoes.json .

RUN useradd --create-home veredito && mkdir -p /data && chown veredito /data
USER veredito

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \ 
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips=*"]