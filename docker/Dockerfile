FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy the Supabase Explorer requirements and install them
COPY supabase_explorer/requirements.txt ./supabase_explorer_requirements.txt
RUN pip install --no-cache-dir -r supabase_explorer_requirements.txt

# Copy the rest of the application
COPY . .

# Expose the ports the app runs on, 8001 for the API and 8501 for the Explorer
EXPOSE 8001
EXPOSE 8501

# Command to run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"] 