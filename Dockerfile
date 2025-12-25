FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure .env is present in the image for Flask config
COPY .env .env

ENV FLASK_APP=wsgi.py
ENV FLASK_ENV=production

# Run the WSGI app object created in wsgi.py
CMD ["gunicorn", "-b", "0.0.0.0:5000", "wsgi:app", "--access-logfile", "-", "--error-logfile", "-"]
