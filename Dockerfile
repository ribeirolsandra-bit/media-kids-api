FROM python:3.11-slim

# Travail dans /app
WORKDIR /app

# Copie des requirements et installation
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code et du dossier media
COPY app ./app
COPY media ./media

# Expose le port
EXPOSE 8000

# Lance l'API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
