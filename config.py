import os
from dotenv import load_dotenv
import secrets

# Cargar variables de entorno
load_dotenv()

class Config:
    """Configuración optimizada para producción con soporte de concurrencia"""
    
    # ============================================
    # BASE DE DATOS
    # ============================================
    
    # Construir URI desde variables individuales o usar URI completa
    if os.environ.get('DATABASE_URL'):
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    else:
        db_user = os.environ.get('DATABASE_USER', 'root')
        db_pass = os.environ.get('DATABASE_PASSWORD', 'root')
        db_host = os.environ.get('DATABASE_HOST', 'localhost')
        db_port = os.environ.get('DATABASE_PORT', '3306')
        db_name = os.environ.get('DATABASE_NAME', 'hive_mining_db')
        
        SQLALCHEMY_DATABASE_URI = f'mysql+mysqlconnector://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'
    
    # ✅ CONNECTION POOLING para 100+ usuarios concurrentes
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,              # Conexiones permanentes en el pool
        'pool_recycle': 3600,         # Reciclar conexiones cada hora
        'pool_pre_ping': True,        # Verificar conexión antes de usar (evita errores)
        'max_overflow': 20,           # Hasta 30 conexiones totales (10 + 20)
        'pool_timeout': 30,           # Timeout esperando conexión disponible
        'echo': False,                # No loguear queries SQL (performance)
    }
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ============================================
    # SEGURIDAD
    # ============================================
    
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # Generar una clave temporal si no está configurada
        # NOTA: Esto reiniciará las sesiones en cada deploy
        SECRET_KEY = secrets.token_hex(32)
        print("⚠️  ADVERTENCIA: Usando SECRET_KEY generada automáticamente.")
    
    # ============================================
    # SESIONES (REDIS)
    # ============================================
    
    SESSION_TYPE = 'redis'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'nyo_session:'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hora
    
    # Redis URL
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # ============================================
    # CACHÉ
    # ============================================
    
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/1')
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutos
    
    # ============================================
    # GOOGLE SHEETS
    # ============================================
    
    GOOGLE_SHEETS_CREDENTIALS = os.environ.get(
        'GOOGLE_SHEETS_CREDENTIALS',
        os.path.join(os.getcwd(), 'credentials.json')
    )
    SPREADSHEET_NAME = os.environ.get(
        'SPREADSHEET_NAME',
        'Planilla de Diagnóstico Hive'
    )
    
    # ============================================
    # FLASK
    # ============================================
    
    DEBUG = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    TESTING = False
    
    # ============================================
    # PRODUCCIÓN
    # ============================================
    
    # Límite de tamaño de archivos (si subes archivos)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    
    # JSON settings
    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = False  # Performance
