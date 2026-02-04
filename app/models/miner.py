from app import db
from datetime import datetime
from sqlalchemy import Index

# ======================================================
# 1. TABLA DE CATÁLOGO (Para definir Aire vs Hydro)
# ======================================================
class MinerModel(db.Model):
    __tablename__ = 'miner_models'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) # Ej: "Antminer S19 XP"
    cooling_type = db.Column(db.String(20), default='AIRE')       # 'AIRE' o 'HYDRO'
    
    def __repr__(self):
        return f'<Modelo {self.name}>'

# ======================================================
# 2. TABLA PRINCIPAL DE INVENTARIO
# ======================================================
class Miner(db.Model):
    __tablename__ = 'mineros'
    
    # --- Identificadores ---
    id = db.Column(db.Integer, primary_key=True)
    
    # IMPORTANTE: nullable=True permite que estén vacíos cuando van al Laboratorio
    warehouse_id = db.Column(db.Integer, nullable=True)
    rack_id = db.Column(db.Integer, nullable=True)
    fila = db.Column(db.Integer, nullable=True)
    columna = db.Column(db.Integer, nullable=True)
    
    # --- Datos Básicos ---
    # Por ahora seguimos usando String hasta que migres todo al Catálogo
    modelo = db.Column(db.String(50)) 
    
    ths = db.Column(db.Float)
    # CAMPO LEGACY: La IP ahora se captura solo al enviar a RMA (ip_rma en formulario)
    # Este campo se mantiene para compatibilidad histórica pero ya no se usa activamente
    ip_address = db.Column(db.String(50), nullable=True)
    mac_address = db.Column(db.String(50))
    
    # --- Identificación ---
    # IMPORTANTE: unique=True refleja el cambio que hicimos en MySQL
    sn_fisica = db.Column(db.String(100), unique=True, nullable=True)
    
    sn_digital = db.Column(db.String(100))
    sn_antiguo = db.Column(db.String(100)) # Para guardar el SN viejo si hubo cambio
    
    # --- Garantía ---
    garantia_vence = db.Column(db.Date, nullable=True)
    
    # --- Componentes Internos ---
    psu_model = db.Column(db.String(100))
    psu_sn = db.Column(db.String(100))
    cb_sn = db.Column(db.String(100))
    hb1_sn = db.Column(db.String(100))
    hb2_sn = db.Column(db.String(100))
    hb3_sn = db.Column(db.String(100))

    # --- Estado y Procesos ---
    # Estados posibles: 'operativo', 'en_laboratorio', 'en_reparacion', 'stock_lab', 'baja_definitiva', 'donante_piezas'
    proceso_estado = db.Column(db.String(50), default='operativo') 
    responsable = db.Column(db.String(100))
    
    # --- Diagnóstico ---
    fecha_diagnostico = db.Column(db.DateTime)
    diagnostico_detalle = db.Column(db.Text)
    log_detalle = db.Column(db.Text)
    observaciones = db.Column(db.Text)

    # --- Auditoría ---
    fecha_registro = db.Column(db.DateTime, default=datetime.now)

    # --- Índices de Velocidad ---
    __table_args__ = (
        Index('idx_ubicacion', 'warehouse_id', 'rack_id'), # Dashboard rápido
        Index('idx_sn', 'sn_fisica'),                      # Buscador rápido
        Index('idx_ip', 'ip_address'),                     # Búsqueda por IP
    )

    def __repr__(self):
        return f'<Miner {self.sn_fisica}>'