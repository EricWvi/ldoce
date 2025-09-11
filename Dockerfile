FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project configuration
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/dict

# Expose port
EXPOSE 8000

# Run the server
CMD ["python", "server.py"]
