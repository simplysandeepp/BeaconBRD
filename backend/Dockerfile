# Use Python 3.11 Bookworm for stability and up-to-date dependencies
FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set the working directory
WORKDIR /app

# Ensure we are running as root
USER root

# Install system dependencies
# Removed libharfbuzz-subset0 as it's not in Bullseye mirrors
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --prefer-binary

# Copy the rest of the application code
# This copies everything from your /backend folder into /app in the container
COPY . .

# Expose the API port
EXPOSE 8080

# Command to run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]