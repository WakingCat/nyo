"""
Punto de entrada de la aplicación
Usa este archivo solo para desarrollo local
En producción, usar gunicorn con gunicorn_config.py
"""
from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Configuración para desarrollo
    debug_mode = os.environ.get('FLASK_DEBUG', 'True') == 'True'
    
    # IMPORTANTE: En producción usar gunicorn, no este servidor
    if not debug_mode:
        print("⚠️  ADVERTENCIA: No uses este servidor en producción")
        print("   Ejecuta: gunicorn -c gunicorn_config.py 'app:create_app()'")
    
    app.run(
        debug=debug_mode,
        host='127.0.0.1',  # Solo localhost (más seguro)
        port=5000,
        threaded=True  # Permite múltiples threads (mejor que single-threaded)
    )