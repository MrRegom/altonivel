"""Consulta ante el SII el estado de los documentos enviados.

Pensado para ejecutarse periódicamente (cada 5-10 minutos) con el
Programador de tareas de Windows o cron. Cuando un documento queda
aceptado, se envía automáticamente al correo del cliente.
"""
import time

from django.core.management.base import BaseCommand

from facturacion.constants import EstadoSII
from facturacion.exceptions import EmisionError
from ventas import services
from ventas.models import DocumentoTributario

# OpenFactura permite 3 consultas por segundo.
PAUSA_SEGUNDOS = 0.4


class Command(BaseCommand):
    help = "Actualiza el estado ante el SII de los documentos enviados."

    def handle(self, *args, **options):
        pendientes = DocumentoTributario.objects.filter(
            estado_sii=EstadoSII.ENVIADO
        ).exclude(track_id="")
        if not pendientes:
            self.stdout.write("No hay documentos esperando respuesta del SII.")
            return
        for doc in pendientes:
            try:
                estado = services.actualizar_estado(doc)
                self.stdout.write(f"{doc}: {doc.get_estado_sii_display()}")
                if estado == EstadoSII.RECHAZADO:
                    self.stderr.write(self.style.ERROR(f"  ¡Rechazado por el SII! Revisar {doc}."))
            except EmisionError as exc:
                self.stderr.write(self.style.ERROR(f"{doc}: {exc}"))
            time.sleep(PAUSA_SEGUNDOS)
