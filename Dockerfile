FROM python:3.12-slim

WORKDIR /app

# Install system deps for protobuf compilation
RUN apt-get update && apt-get install -y \\
    gcc \\
    libffi-dev \\
    openssl \\
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Generate protobuf if needed
# RUN python -m grpc_tools.protoc -I proto --python_out=src/generated proto/messages.proto

# Generate TLS certs if not present
RUN bash certs/generate.sh || true

EXPOSE 8000 9090

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main"]