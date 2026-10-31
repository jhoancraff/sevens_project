from django.apps import AppConfig


class SevensConfig(AppConfig):
    name = 'sevens'
    label = 'sevens'

    def ready(self):
        from .costos_historial import conectar_senales
        conectar_senales()
