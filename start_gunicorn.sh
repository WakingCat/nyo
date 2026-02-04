#!/bin/bash

# Script rápido para probar Gunicorn
# Este script inicia el servidor en modo desarrollo/prueba

echo "🚀 Iniciando servidor con Gunicorn..."

# Activar entorno virtual
source venv/bin/activate

# Detener cualquier instancia previa
pkill -f gunicorn 2>/dev/null || true
sleep 2

# Crear directorio de logs
mkdir -p logs

# Iniciar Gunicorn
echo "Ejecutando: gunicorn -c gunicorn_config.py 'app:create_app()'"
gunicorn -c gunicorn_config.py "app:create_app()"
