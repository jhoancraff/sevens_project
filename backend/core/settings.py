import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('SECRET_KEY', 'insecure-default-key-change-in-production')

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]

# ------------------------------------------------------------------
# Red de seguridad entre produccion y pruebas
# ------------------------------------------------------------------
# Si el proceso se declara como entorno de pruebas, la base de datos tiene
# que ser la de pruebas. Se dio el caso de lo contrario (por el orden de
# precedencia de EnvironmentFile= sobre Environment= en systemd) y el
# resultado era una app de pruebas escribiendo sobre los datos reales del
# restaurante. Aqui se corta en seco en lugar de confiar en la config.
AMBIENTE = (os.getenv('SEVENS_AMBIENTE', '') or '').strip().lower()
ES_ENTORNO_PRUEBAS = AMBIENTE in ('prueba', 'pruebas', 'test', 'tests', 'dev', 'staging')
DB_ESPERADA_EN_PRUEBAS = os.getenv('DB_ESPERADA_EN_PRUEBAS', 'sevensdb_test')

if ES_ENTORNO_PRUEBAS and os.getenv('DB_NAME', '') == 'sevensdb':
    raise RuntimeError(
        'CONFIGURACION INVALIDA: el proceso dice ser de pruebas '
        f'(SEVENS_AMBIENTE={AMBIENTE}) pero esta apuntando a "sevensdb", '
        'la base de PRODUCCION con los datos reales del restaurante. '
        'Se detiene el arranque para no escribirlas por error.\n'
        '  Causa habitual: declarar EnvironmentFile= en el unit, que en '
        'systemd tiene mas prioridad que Environment=.\n'
        f'  Arreglo: quitar EnvironmentFile= y dejar que Django lea '
        f'{BASE_DIR / ".env"}, con DB_NAME={DB_ESPERADA_EN_PRUEBAS} en Environment=.'
    )

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party apps
    'corsheaders',
    'rest_framework',
    # Local apps
    'api',
    'sevens.apps.SevensConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS middleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database
# Connect to PostgreSQL using environment variables
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'sevensdb'),
        'USER': os.getenv('DB_USER', 'sevens'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-es'
# Venezuela (UTC-4), igual que Varagrill: los cortes por dia (cuadre de caja, reportes) y la hora impresa en
# los PDF deben ser la hora local. Con USE_TZ=True las fechas se siguen guardando en UTC.
TIME_ZONE = 'America/Caracas'

# Minutos que se respeta la tasa de una pre-factura al emitir la nota de entrega / factura de esos
# mismos pedidos (ver sevens/tasa_cuenta.py).
VENTANA_TASA_PREFACTURA_MIN = int(os.getenv('VENTANA_TASA_PREFACTURA_MIN', '60'))
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Archivos subidos por el usuario (fotos de productos).
# El catalogo publico los sirve por /api/productos/<id>/imagen/ (ver
# product_image_view), pero el admin tambien devuelve la URL cruda, asi que
# se expone /media/ para que Nginx la sirva directo.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'sevens.VGUsuario'
SESSION_COOKIE_NAME = os.getenv('SESSION_COOKIE_NAME', 'sessionid')

# CORS Settings
cors_origins_raw = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173')
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins_raw.split(',') if origin.strip()]
CORS_ALLOW_CREDENTIALS = True

# Impresora de CAJA: los tickets (nota de entrega, cuenta del cliente, nota de
# cobro, factura) salen como imagen con el logo y una tipografia de recibo (ver
# sevens/ticket_grafico.py). TICKET_CAJA_ANCHO_PUNTOS: 576 = papel de 80 mm
# (el de la impresora de caja), 384 = papel de 58 mm. TICKET_CAJA_GRAFICO=false
# vuelve al ticket de solo texto.
TICKET_CAJA_ANCHO_PUNTOS = int(os.getenv('TICKET_CAJA_ANCHO_PUNTOS', '576') or 576)
TICKET_CAJA_GRAFICO = os.getenv('TICKET_CAJA_GRAFICO', 'true').lower() in ('true', '1', 't')

# Largo (en dígitos) del número de orden de Cashea que teclea la cajera. Si escribe
# otro largo, el cobro pide una confirmación explícita (puede ser un dígito de más
# o de menos). 0 desactiva la comprobación.
CASHEA_ORDEN_DIGITOS = int(os.getenv('CASHEA_ORDEN_DIGITOS', '9') or 0)
