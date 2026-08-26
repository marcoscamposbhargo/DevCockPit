# DevCockpit em container — **experimental, e com capacidade reduzida**.
#
# Este arquivo não é o caminho de distribuição do painel: esse é o executável
# gerado por `scripts/build_exe.ps1`. Ele existe para o cenário em que o
# DevCockpit roda num servidor Linux, contra projetos que vivem **nesse mesmo
# servidor**.
#
# O que o painel perde dentro de um container, e não é pouco:
#
#   - abrir VS Code, pasta e terminal: nenhum dos três existe aqui dentro
#   - varredura de projetos: os caminhos de `configs/roots.yml` são do host
#   - subir servidor de projeto: os projetos não estão neste sistema de arquivos
#   - verificação de porta: `localhost` aqui é o do container, não o da máquina
#     — todo serviço do host apareceria offline
#
# O que continua funcionando: cadastro, Git, leitura de Docker (com o socket
# montado), portas declaradas e o Cockpit AI.
#
# Ninguém roda testes contra este caminho. Tratar como rascunho, não como
# suportado.

# Multi-stage build for DevCockpit
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files only (for layer caching)
COPY pyproject.toml README.md ./

# Create wheels for all dependencies
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -e .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /build/wheels /wheels

# Install application from wheels
RUN pip install --upgrade pip && \
    pip install --no-cache /wheels/* && \
    rm -rf /wheels

# Copy application code
COPY app ./app
COPY frontend ./frontend
COPY migrations ./migrations
COPY alembic.ini .

# Create necessary directories with proper permissions
RUN mkdir -p data logs configs && \
    chmod 755 data logs configs

# Copy default configuration files
COPY .env.example .env
COPY configs configs/

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health').read()" || exit 1

# Expose port
EXPOSE 8765

# Run application
#
# 0.0.0.0 e nao 127.0.0.1: o bind aqui e DENTRO do namespace de rede do
# container. Com 127.0.0.1 o processo so aceita conexoes vindas do proprio
# container, e o proxy de porta do Docker — que chega pelo IP do container —
# nao alcanca ninguem: a porta responde por dentro e recusa por fora.
#
# Isso nao afrouxa a seguranca. Quem limita a exposicao real e o mapeamento
# do docker-compose.yml (`ports: "127.0.0.1:8765:8765"`), que publica a porta
# apenas no loopback do host. Para restringir o acesso, mexa la, nao aqui.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
