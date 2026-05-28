# Verwende ein leichtgewichtiges Python Image
FROM python:3.11-slim

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Installiere Git, curl, nodejs, npm und build-essential (wird für GitAgent, LSP-Server wie Pyright und System-Tools benötigt)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    nodejs \
    npm \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Kopiere Requirements und installiere sie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den restlichen Code
COPY . /app

# Konfiguriere den Standard-Einstiegspunkt
ENTRYPOINT ["python3", "mini_cli.py"]

# Standardbefehl (startet den REPL, wenn keine Argumente übergeben werden)
CMD []
