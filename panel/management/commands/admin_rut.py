"""Deja un superadministrador que ingresa con su RUT.

    python manage.py admin_rut 12345678-9                 # convierte o crea
    python manage.py admin_rut 12345678-9 --usuario juan  # convierte a "juan"

- Con --usuario: ese usuario pasa a ingresar con el RUT indicado.
- Sin --usuario: si hay un único superadministrador cuyo usuario no es
  un RUT, se convierte ese. Si no hay ninguno, se crea uno nuevo y se
  pide la contraseña en la terminal.
"""
from getpass import getpass

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.rut import RutInvalidoError, es_valido, normalizar


class Command(BaseCommand):
    help = "Deja un superadministrador que ingresa con su RUT."

    def add_arguments(self, parser):
        parser.add_argument("rut")
        parser.add_argument("--usuario", help="Usuario existente que pasará a ingresar con el RUT.")
        parser.add_argument("--nombre", default="", help="Nombre (solo al crear uno nuevo).")

    def handle(self, rut, usuario=None, nombre="", **options):
        Usuario = get_user_model()
        try:
            rut = normalizar(rut)
        except RutInvalidoError:
            raise CommandError("El RUT no es válido.")

        existente = Usuario.objects.filter(username=rut).first()
        if usuario:
            try:
                objetivo = Usuario.objects.get(username=usuario)
            except Usuario.DoesNotExist:
                raise CommandError(f"No existe el usuario {usuario!r}.")
        elif existente:
            objetivo = existente
        else:
            sin_rut = [u for u in Usuario.objects.filter(is_superuser=True) if not es_valido(u.username)]
            if len(sin_rut) > 1:
                nombres = ", ".join(u.username for u in sin_rut)
                raise CommandError(f"Hay varios superadministradores ({nombres}). Indica cuál con --usuario.")
            objetivo = sin_rut[0] if sin_rut else None

        if existente and objetivo and existente.pk != objetivo.pk:
            raise CommandError("Ese RUT ya pertenece a otro usuario.")

        if objetivo is None:
            objetivo = Usuario(username=rut, first_name=nombre)
            clave = getpass("Contraseña: ")
            if clave != getpass("Repetir contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")
            try:
                password_validation.validate_password(clave, objetivo)
            except ValidationError as exc:
                raise CommandError(" ".join(exc.messages))
            objetivo.set_password(clave)
            accion = "Creado"
        else:
            anterior = objetivo.username
            accion = f"Actualizado (antes: {anterior})" if anterior != rut else "Actualizado"

        objetivo.username = rut
        objetivo.is_superuser = True
        objetivo.is_staff = True
        objetivo.is_active = True
        objetivo.save()
        self.stdout.write(self.style.SUCCESS(f"{accion}: el superadministrador ingresa con el RUT {rut}."))
