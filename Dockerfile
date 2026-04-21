# Use the official Python image
FROM python:3.12.10

# Set working directory
WORKDIR /app


# Copy requirements (to leverage Docker caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose Django port
EXPOSE 8000

# Start the application
CMD ["gunicorn", "chaoscps.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
