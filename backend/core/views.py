from django.http import JsonResponse
from django.db import connection
import django

def status_check(request):
    db_status = "disconnected"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version();")
            row = cursor.fetchone()
            db_name, db_user, db_version = row[0], row[1], row[2]
            db_status = "connected"
    except Exception as e:
        db_name, db_user, db_version = None, None, str(e)

    return JsonResponse({
        "status": "online",
        "service": "Django + Gunicorn Backend",
        "django_version": django.get_version(),
        "database": {
            "status": db_status,
            "engine": "PostgreSQL",
            "name": db_name,
            "user": db_user,
        }
    })
