from django.contrib import admin
from django.urls import path, include
from .views import status_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/status/', status_check, name='status_check'),
    path('api/', include('api.urls')),
    # API del restaurante (app 'sevens').Va despues de api.urls para que las
    # rutas de la demo (api/items/) no pisen las del restaurante.
    path('api/', include('sevens.urls')),
    path('', status_check, name='root_status'),
]
