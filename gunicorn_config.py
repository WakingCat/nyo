"""
Configuración de Gunicorn para Producción
Optimizado para manejar 100+ usuarios concurrentes
"""
import multiprocessing
import os

# ============================================
# WORKERS
# ============================================

# Fórmula recomendada: (2 × CPU_cores) + 1
# Para servidor con 4 cores = 9 workers
# Puedes ajustar según tu hardware
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

# Tipo de worker
# 'sync' - Para aplicaciones CPU-bound (tu caso)
# 'gevent' - Para I/O-bound (muchas llamadas a BD/APIs)
worker_class = 'sync'

# Threads por worker (opcional, mejora concurrencia)
threads = 2

# ============================================
# TIMEOUTS Y KEEPALIVE
# ============================================

# Timeout para requests (segundos)
# Aumentado porque tienes operaciones de Google Sheets que pueden tardar
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))

# Timeout para workers silenciosos
graceful_timeout = 30

# Keepalive connections
keepalive = 5

# ============================================
# BINDING
# ============================================

# Dirección y puerto
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5000')

# Backlog (cola de conexiones pendientes)
backlog = 2048

# ============================================
# LOGGING
# ============================================

# Crear directorio de logs si no existe
if not os.path.exists('logs'):
    os.makedirs('logs')

accesslog = 'logs/gunicorn_access.log'
errorlog = 'logs/gunicorn_error.log'
loglevel = 'info'

# Formato de logs de acceso
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ============================================
# PROCESO
# ============================================

# Nombre del proceso
proc_name = 'nyo_mining'

# PID file (útil para scripts de control)
pidfile = 'logs/gunicorn.pid'

# Usuario (cambiar en producción por seguridad)
# user = 'www-data'
# group = 'www-data'

# ============================================
# DESARROLLO
# ============================================

# Auto-reload cuando cambian archivos (SOLO DESARROLLO)
# ⚠️ Desactivar en producción
reload = os.environ.get('FLASK_ENV') == 'development'

# ============================================
# OPTIMIZACIONES
# ============================================

# Pre-load de la aplicación (compartir código entre workers)
# Reduce uso de memoria
preload_app = True

# Tiempo máximo de vida de un worker (previene memory leaks)
max_requests = 1000
max_requests_jitter = 50  # Aleatoridad para evitar reinicios simultáneos

# ============================================
# HOOKS (CALLBACKS)
# ============================================

def on_starting(server):
    """Ejecutado al iniciar Gunicorn"""
    print("🚀 Iniciando servidor Gunicorn...")
    print(f"Workers: {workers}")
    print(f"Threads por worker: {threads}")
    print(f"Bind: {bind}")

def when_ready(server):
    """Ejecutado cuando el servidor está listo"""
    print("✅ Servidor listo para recibir requests")

def on_reload(server):
    """Ejecutado al hacer reload"""
    print("🔄 Recargando código...")

def worker_int(worker):
    """Ejecutado cuando un worker recibe SIGINT"""
    print(f"⚠️  Worker {worker.pid} interrumpido")

def post_fork(server, worker):
    """Ejecutado después de crear un worker"""
    print(f"👷 Worker {worker.pid} iniciado")
