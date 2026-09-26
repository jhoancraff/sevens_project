"""
Crea (o actualiza) un usuario del restauranteIndicndole su rol.

Pensado para dar de alta al personal sin tener que abrir el panel de
Django. Acepta el rol por nombre con mayusculas/minusculas y no distingue
tildes, asi que "cajera", "CAJERA" y "cajera" funcionan igual.

Ejemplos:

    python manage.py crear_usuario --username jhoan --password Clave123 \
        --cedula 12345678 --rol mesero --nombre "Jhoan" --apellido Perez

    python manage.py crear_usuario --username ana --password Clave123 \
        --cedula 87654321 --rol cajera --email ana@varagrill.local

    # Ver los roles disponibles y cambiar el password de uno existente
    python manage.py crear_usuario --listar-roles
    python manage.py crear_usuario --username jhoan --password NuevaClave1
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sevens.models import VGRol, VGUsuario


def _normalizar(texto):
    """'Cajera' y 'cajéra' deben llegar al mismo rol."""
    return ''.join(
        c for c in texto.strip().lower()
        if c.isalnum() or c.isspace()
    ).replace(' ', '')


class Command(BaseCommand):
    help = 'Crea o actualiza un usuario del restaurante con su rol.'

    def add_arguments(self, parser):
        parser.add_argument('--username')
        parser.add_argument('--password', help='Omitirlo solo cambia el password.')
        parser.add_argument('--cedula', help='Unica y obligatoria para crear uno nuevo.')
        parser.add_argument('--rol', help='Nombre del rol (mesero, cajera, cocinero, contador, analista, administrador).')
        parser.add_argument('--nombre', dest='first_name', default='')
        parser.add_argument('--apellido', dest='last_name', default='')
        parser.add_argument('--email', default='')
        parser.add_argument('--telefono', default='')
        parser.add_argument('--activo', dest='is_active', action='store_true', default=None,
                            help='Fuerza is_active=True (por defecto queda activo).')
        parser.add_argument('--inactivo', dest='is_active', action='store_false',
                            help='Crea o deja el usuario inactivo (no puede entrar).')
        parser.add_argument('--staff', action='store_true', help='Da acceso al panel /admin/.')
        parser.add_argument('--superuser', action='store_true',
                            help='Superusuario de Django: entra a TODO, incluidas las pantallas '
                                 'reservadas al dueno (impresoras, datos fiscales, compras) y a /admin/.')
        parser.add_argument('--listar-roles', action='store_true',
                            help='Muestra los roles disponibles y sale.')

    def handle(self, *args, **options):
        if options['listar_roles']:
            self.stdout.write('Roles disponibles:')
            for rol in VGRol.objects.order_by('nombre_role'):
                self.stdout.write(f'  - {rol.nombre_role}')
            return

        username = (options['username'] or '').strip()
        if not username:
            raise CommandError('Falta --username (o usa --listar-roles para ver los disponibles).')

        # El rol se resuelve antes de tocar nada, para fallar con un mensaje
        # claro en vez de a mitad de la creacion.
        rol = None
        if options['rol']:
            deseado = _normalizar(options['rol'])
            rol = next(
                (r for r in VGRol.objects.all() if _normalizar(r.nombre_role) == deseado),
                None,
            )
            if rol is None:
                disponibles = ', '.join(r.nombre_role for r in VGRol.objects.order_by('nombre_role'))
                raise CommandError(
                    f'No existe el rol "{options["rol"]}". Disponibles: {disponibles}'
                )

        with transaction.atomic():
            usuario = VGUsuario.objects.filter(username__iexact=username).first()

            if usuario is None:
                cedula = (options['cedula'] or '').strip()
                if not cedula:
                    raise CommandError(
                        'Para crear un usuario nuevo hace falta --cedula (es única y obligatoria).'
                    )
                if VGUsuario.objects.filter(cedula=cedula).exists():
                    raise CommandError(f'Ya existe un usuario con la cédula {cedula}.')

                usuario = VGUsuario(username=username, cedula=cedula)
                self.stdout.write(self.style.WARNING(f'Usuario nuevo: {username}'))
            else:
                if options['cedula'] and options['cedula'].strip() != usuario.cedula:
                    if VGUsuario.objects.filter(cedula=options['cedula'].strip()).exists():
                        raise CommandError(f'Ya existe otro usuario con la cédula {options["cedula"]}.')
                    usuario.cedula = options['cedula'].strip()
                self.stdout.write(self.style.WARNING(f'Usuario existente: {usuario.username}'))

            # Rol (ya resuelto arriba)
            if rol is not None:
                usuario.id_role = rol

            if options['first_name']:
                usuario.first_name = options['first_name']
            if options['last_name']:
                usuario.last_name = options['last_name']
            if options['email']:
                usuario.email = options['email']
            if options['telefono']:
                usuario.telefono = options['telefono']
            if options['is_active'] is not None:
                usuario.is_active = options['is_active']
            else:
                usuario.is_active = True

            if options['staff']:
                usuario.is_staff = True

            # Un superusuario necesita is_staff Y is_superuser: Django le cierra
            # /admin/ sin is_staff, y la app reserva las pantallas del dueno
            # (ver _is_owner_user) a quien tenga cualquiera de los dos.
            if options['superuser']:
                usuario.is_staff = True
                usuario.is_superuser = True

            if options['password']:
                usuario.set_password(options['password'])

            usuario.save()

        self.stdout.write(self.style.SUCCESS(
            f'OK  {usuario.username}  id={usuario.id}  '
            f'rol={getattr(usuario.id_role, "nombre_role", None) or "sin rol"}  '
            f'activo={usuario.is_active}  staff={usuario.is_staff}  super={usuario.is_superuser}'
        ))
        if not options['password']:
            self.stdout.write('  (no se tocó el password)')
