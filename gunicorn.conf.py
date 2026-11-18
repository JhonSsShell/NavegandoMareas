"""Configuración de Gunicorn (se carga automáticamente al ejecutar `gunicorn app:app`).

* Escucha en el puerto que asigna la plataforma (Railway/Render definen PORT).
* Un solo proceso con varios hilos: el estado del mapa vive en memoria, así
  todas las peticiones ven el mismo mapa (ver informe, sección de mejoras).
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60
accesslog = "-"
