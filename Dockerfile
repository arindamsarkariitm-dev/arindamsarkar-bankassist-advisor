FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY data/ data/
COPY prompts/ prompts/
COPY vectorstore/ vectorstore/
COPY app.py .

# .env is intentionally NOT copied -- it's supplied at run time (docker-compose's
# env_file, or -e / --env-file on `docker run`), never baked into the image.

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
