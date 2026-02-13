FROM python:3.12-slim

# Install wkhtmltopdf (required by pdfkit)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
