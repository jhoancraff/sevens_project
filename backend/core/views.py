"""
Vista de estado del backend.

Sirve para dos cosas: comprobar que todo responde y, sobre todo, decir QUE
entorno es el que esta conectado. El nombre sale de la variable de entorno
VITE_SEVENTS_AMBIENTE / SEVENS_AMBIENTE y la app lo lee al cargar, asi que
se ve en pantalla sin tener que adivinar por la URL.
"""
import os

import django
from django.db import connection
from django.http import JsonResponse


def status_check(request):
    db_status = "disconnected"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version();")
            row = cursor.fetchone()
            db_name, db_user, db_version = row[0], row[1], row[2]
            db_status = "connected"
    except Exception:
        db_name, db_user, db_version = None, None, "error de conexion"

    ambiente = (os.getenv("SEVENS_AMBIENTE", "") or "").strip()
    es_pruebas = ambiente.lower() in ("prueba", "pruebas", "test", "tests", "dev", "staging")

    return JsonResponse({
        "status": "online",
        "service": "Django + Gunicorn Backend",
        "django_version": django.get_version(),
        # Para que el frontend sepa pintar el aviso y el color de la barra.
        "ambiente": ambiente or "produccion",
        "es_pruebas": es_pruebas,
        "database": {
            "status": db_status,
            "engine": "PostgreSQL",
            "name": db_name,
            "user": db_user,
        },
    })
