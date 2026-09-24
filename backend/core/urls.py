from django.contrib import admin
from django.urls import path
from .views import status_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/status/', status_check, name='status_check'),
    path('', status_check, name='root_status'),
]
