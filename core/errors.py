"""Benutzerlesbare Fehler statt technischer Tracebacks in Dialogen."""


class HubError(Exception):
    pass


class Cancelled(HubError):
    def __init__(self):
        super().__init__("Vorgang abgebrochen. Die bisherigen gespeicherten Daten bleiben erhalten.")
