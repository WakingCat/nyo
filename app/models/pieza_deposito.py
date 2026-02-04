"""
Modelo de Piezas del Depósito con tracking por Serial Number
"""
from app import db
from datetime import datetime
from sqlalchemy import Index

class PiezaDeposito(db.Model):
    """
    Pieza individual del depósito con Serial Number único.
    Permite tracking detallado de cada componente.
    """
    __tablename__ = 'piezas_deposito'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # ============================================
    # IDENTIFICACIÓN
    # ============================================
    
    # Serial Number único de la pieza
    sn = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # Tipo de pieza: PSU, FAN, CB, CALENTADOR, DISTRIBUIDOR, PDU
    tipo = db.Column(db.String(30), nullable=False)
    
    # Modelo de equipo compatible: S21+, S21hyd, Avalon, Buzzminer
    modelo_equipo = db.Column(db.String(50), nullable=False)
    
    # Modelo específico de la pieza (ej: APW12, APW9+)
    modelo_pieza = db.Column(db.String(50))
    
    # ============================================
    # UBICACIÓN FÍSICA
    # ============================================
    
    # Ubicación: STOCK, LAB, WH, REPARACION, BAJA
    ubicacion = db.Column(db.String(30), default='STOCK')
    
    # Número de caja donde está almacenada
    caja_numero = db.Column(db.Integer)
    
    # Número de pallet
    pallet_numero = db.Column(db.Integer)
    
    # Ubicación en estante (ej: "A3", "B1")
    estante = db.Column(db.String(20))
    
    # ============================================
    # ESTADO
    # ============================================
    
    # Si es pieza reparada (vs nueva)
    es_reparado = db.Column(db.Boolean, default=False)
    
    # Estado: DISPONIBLE, EN_USO, RESERVADO, DEFECTUOSO
    estado = db.Column(db.String(30), default='DISPONIBLE')
    
    # Notas/observaciones
    notas = db.Column(db.Text)
    
    # ============================================
    # TRACKING
    # ============================================
    
    # Fecha de ingreso al depósito
    fecha_ingreso = db.Column(db.DateTime, default=datetime.now)
    
    # Fecha de última salida
    fecha_salida = db.Column(db.DateTime)
    
    # Quién registró la pieza
    registrado_por = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Última modificación
    ultima_modificacion = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    modificado_por = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Si está asignada a una solicitud
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes_pieza.id'))
    
    # ============================================
    # RELACIONES
    # ============================================
    
    solicitud = db.relationship('SolicitudPieza', backref='pieza_asignada')
    
    # Índices para búsquedas frecuentes
    __table_args__ = (
        Index('idx_pieza_tipo_modelo', 'tipo', 'modelo_equipo'),
        Index('idx_pieza_ubicacion', 'ubicacion'),
        Index('idx_pieza_estado', 'estado'),
        Index('idx_pieza_caja', 'caja_numero'),
    )

    def __repr__(self):
        return f'<PiezaDeposito {self.sn} ({self.tipo} {self.modelo_equipo})>'
    
    @property
    def disponible(self):
        """Retorna True si la pieza está disponible"""
        return self.estado == 'DISPONIBLE' and self.ubicacion == 'STOCK'
    
    @property
    def info_completa(self):
        """Retorna diccionario con toda la info"""
        return {
            'id': self.id,
            'sn': self.sn,
            'tipo': self.tipo,
            'modelo_equipo': self.modelo_equipo,
            'modelo_pieza': self.modelo_pieza,
            'ubicacion': self.ubicacion,
            'caja': self.caja_numero,
            'pallet': self.pallet_numero,
            'es_reparado': self.es_reparado,
            'estado': self.estado,
            'disponible': self.disponible
        }


class MovimientoPiezaDeposito(db.Model):
    """
    Historial de movimientos de piezas individuales
    """
    __tablename__ = 'movimientos_piezas_deposito'
    
    id = db.Column(db.Integer, primary_key=True)
    pieza_id = db.Column(db.Integer, db.ForeignKey('piezas_deposito.id'), nullable=False)
    
    # Tipo: INGRESO, SALIDA, TRANSFERENCIA, REPARACION, BAJA
    tipo_movimiento = db.Column(db.String(30), nullable=False)
    
    # Ubicación anterior y nueva
    ubicacion_anterior = db.Column(db.String(30))
    ubicacion_nueva = db.Column(db.String(30))
    
    # Referencia a solicitud si aplica
    solicitud_pieza_id = db.Column(db.Integer, db.ForeignKey('solicitudes_pieza.id'))
    
    # Destino (WH #, etc)
    destino_wh = db.Column(db.Integer)
    
    # Detalles
    motivo = db.Column(db.Text)
    
    # Quién realizó el movimiento
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    
    # Relaciones
    pieza = db.relationship('PiezaDeposito', backref='movimientos')
    usuario = db.relationship('User', backref='movimientos_piezas_deposito')
    solicitud = db.relationship('SolicitudPieza', backref='movimientos_pieza_deposito')
    
    __table_args__ = (
        Index('idx_mov_deposito_fecha', 'fecha'),
        Index('idx_mov_deposito_pieza', 'pieza_id'),
    )

    def __repr__(self):
        return f'<MovimientoPiezaDeposito {self.tipo_movimiento} pieza:{self.pieza_id}>'


# Constantes para validación
TIPOS_PIEZA = ['PSU', 'FAN', 'CB', 'CALENTADOR', 'DISTRIBUIDOR', 'PDU', 'HASHBOARD']
MODELOS_EQUIPO = ['S21+', 'S21hyd', 'Avalon', 'Buzzminer']
UBICACIONES = ['STOCK', 'LAB', 'WH', 'REPARACION', 'BAJA', 'A_DETERMINAR']
ESTADOS = ['DISPONIBLE', 'EN_USO', 'RESERVADO', 'DEFECTUOSO']
