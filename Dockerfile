FROM python:3-alpine

WORKDIR /app

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY aoh aoh
COPY demo /aoh
COPY .env.docker .env

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "aoh:create_app()"]
