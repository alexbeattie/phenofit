FROM python:3.12-slim

WORKDIR /app

# Install deps first so they cache across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The platform injects $PORT and we listen on all interfaces. $PORT is set by
# the host at runtime; 8000 is only a local fallback.
ENV HOST=0.0.0.0
EXPOSE 8000

# --no-open: never try to launch a browser inside the container.
CMD ["python", "-m", "phenofit.webapp", "--no-open"]
