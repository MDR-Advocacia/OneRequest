# 1. Imagem base do Python
FROM python:3.10-slim

# 2. Define o diretório de trabalho (a raiz do projeto)
WORKDIR /app

# 3. Copia o requirements.txt DE DENTRO da pasta RPA
COPY ./RPA/requirements.txt .

# 4. Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia TODO o resto do projeto para dentro do /app
# Isso vai criar /app/server.py, /app/RPA/main.py, /app/bd/database.py, etc.
COPY . .

# 6. Expõe a porta do Flask
EXPOSE 5000