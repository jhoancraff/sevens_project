from django.contrib import admin
from django.urls import path, include
from .views import status_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/status/', status_check, name='status_check'),
    path('api/', include('api.urls')),
    path('', status_check, name='root_status'),
]
