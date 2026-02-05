from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from flask_caching import Cache
from config import Config
import redis

db = SQLAlchemy()
cache = Cache()
sess = Session()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Inicializar extensiones
    db.init_app(app)
    
    # ✅ Configurar Redis para sesiones (compartidas entre workers)
    # ✅ Configurar Redis para sesiones (compartidas entre workers)
    redis_url = app.config.get('REDIS_URL')
    redis_connected = False
    
    if redis_url:
        try:
            redis_client = redis.from_url(redis_url, socket_timeout=2)
            redis_client.ping()
            app.config['SESSION_REDIS'] = redis_client
            redis_connected = True
            print("✅ Redis conectado - Sesiones compartidas entre workers")
        except Exception as e:
            print(f"⚠️  Redis no disponible: {e}")
    
    if not redis_connected:
        print("   Usando sesiones en memoria/archivo (no recomendado para producción)")
        app.config['SESSION_TYPE'] = 'filesystem'
        app.config['SESSION_REDIS'] = None # Asegurar que no intenta usarlo
    
    sess.init_app(app)
    
    # ✅ Configurar caché
    cache.init_app(app)

    with app.app_context():
        from app.models.miner import Miner
        from app.models.user import User, Role, Movimiento
        from app.models.solicitud import SolicitudTraslado
        from app.models.solicitud_pieza import SolicitudPieza
        from app.models.inventario_pieza import InventarioPieza, MovimientoPieza  # DEPOSITO
        from app.models.pieza_deposito import PiezaDeposito, MovimientoPiezaDeposito  # PIEZAS CON SN
        from app.models.diagnostico import Diagnostico
        db.create_all()
        print("✅ Base de datos sincronizada.")

    # REGISTRO DE RUTAS - NUEVOS MÓDULOS REFACTORIZADOS
    from app.routes.dashboard import dashboard_bp       # Dashboards refactorizados
    from app.routes.lab_views import lab_bp             # Lab views refactorizadas
    from app.routes.transactions import transactions_bp # APIs transaccionales
    
    # RUTAS LEGACY (mantener para compatibilidad)
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.api import api_bp
    from app.routes.transfers import transfers_bp
    from app.routes.insertar_api import insertion_bp
    from app.routes.conciliacion import conciliacion_bp
    from app.routes.deposito import deposito_bp
    from app.routes.lab_approvals import lab_approvals_bp
    from app.routes.lab_routes import lab_routes
    from app.routes.conciliacion_dashboard import conciliacion_dash_bp

    # Registrar nuevos blueprints refactorizados
    app.register_blueprint(dashboard_bp)        # / y /dashboard/*
    app.register_blueprint(lab_bp)              # /lab/*
    app.register_blueprint(transactions_bp)     # /api/* (transacciones)
    app.register_blueprint(conciliacion_dash_bp) # /conciliacion/*
    
    from app.routes.diagnostico_routes import diagnostico_bp
    app.register_blueprint(diagnostico_bp)
    
    # Mantener blueprints legacy para compatibilidad
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(transfers_bp)
    app.register_blueprint(insertion_bp)
    app.register_blueprint(conciliacion_bp)
    app.register_blueprint(deposito_bp)
    app.register_blueprint(lab_approvals_bp)
    app.register_blueprint(lab_routes)

    return app