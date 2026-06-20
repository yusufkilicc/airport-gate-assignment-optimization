# Container image for Hugging Face Spaces (Docker SDK) or any container host.
# HF Spaces expects the app to listen on port 7860.
FROM python:3.11-slim

WORKDIR /app

# System libs sometimes needed by matplotlib/scipy wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=7860
EXPOSE 7860

CMD ["gunicorn", "--chdir", "src", "dashboard:server", \
     "--bind", "0.0.0.0:7860", "--workers", "1", "--timeout", "120"]
