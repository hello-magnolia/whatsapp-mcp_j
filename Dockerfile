FROM golang:1.22-bookworm AS bridge-builder

WORKDIR /src/whatsapp-bridge
COPY whatsapp-bridge/go.mod whatsapp-bridge/go.sum ./
RUN go mod download
COPY whatsapp-bridge/ ./
RUN go build -o /out/whatsapp-bridge .

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install Python dependencies
WORKDIR /app/whatsapp-mcp-server
RUN pip install --no-cache-dir -e .

# Copy bridge binary
COPY --from=bridge-builder /out/whatsapp-bridge /app/whatsapp-bridge/whatsapp-bridge

# Prepare runtime directories
RUN mkdir -p /app/whatsapp-bridge/store /tmp/whatsapp-api-uploads \
    && chmod +x /app/start.sh

EXPOSE 8000

WORKDIR /app
CMD ["/app/start.sh"]
