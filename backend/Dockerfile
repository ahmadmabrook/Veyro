FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.lock .
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock
COPY app ./app
RUN useradd --system --no-create-home veyro
USER veyro
EXPOSE 8000
CMD ["uvicorn", "--factory", "app.main:_default_app", "--host", "0.0.0.0", "--port", "8000"]
