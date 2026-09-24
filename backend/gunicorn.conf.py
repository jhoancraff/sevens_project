"""
Gunicorn configuration file for Django project.
"""
import multiprocessing
import os

# Server socket
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")
backlog = 2048

# Worker processes
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
worker_connections = 1000
timeout = 60
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Process naming
proc_name = "sevens_django_gunicorn"

# WSGI Application entry point
wsgi_app = "core.wsgi:application"
