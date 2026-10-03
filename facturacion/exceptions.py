"""Errores de la capa de emisión."""


class EmisionError(Exception):
    """Falla al emitir o consultar un DTE ante el backend."""


class ConfiguracionError(EmisionError):
    """Falta configuración necesaria (API key, certificado, etc.)."""


class DatosInvalidosError(EmisionError):
    """El DTE no cumple los requisitos del SII; se detecta antes de enviarlo."""

    def __init__(self, errores: list[str]):
        self.errores = errores
        super().__init__("; ".join(errores))
