FROM python:3-alpine

WORKDIR /app

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY aoh aoh

RUN << EOF
echo 'AOH_PASSWORDS_FILE=/aoh/passwords.yml' >> .env
echo 'AOH_PLAYBOOKS_FILE=/aoh/playbooks.yml' >> .env
EOF

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "aoh:create_app()"]
