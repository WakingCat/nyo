"""
Modelo de Inventario de Piezas para Depósito
"""
from app import db
from datetime import datetime
from sqlalchemy import Index

class InventarioPieza(db.Model):
    """
    Inventario de piezas del depósito.
    Gestiona stock de PSU, Fan, CB para S21+, S21hyd y Avalon.
    """
    __tablename__ = 'inventario_piezas'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Modelo de equipo: S21+, S21hyd, Avalon
    modelo_equipo = db.Column(db.String(50), nullable=False)
    
    # Tipo de pieza: PSU, FAN, CB
    tipo_pieza = db.Column(db.String(30), nullable=False)
    
    # Stock disponible
    cantidad = db.Column(db.Integer, default=0)
    
    # Umbral mínimo (para alertas)
    stock_minimo = db.Column(db.Integer, default=5)
    
    # Ubicación en depósito (ej. "Estante A3")
    ubicacion_deposito = db.Column(db.String(50))
    
    # Metadata
    ultima_actualizacion = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    actualizado_por = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Índice compuesto para búsquedas
    __table_args__ = (
        Index('idx_modelo_tipo', 'modelo_equipo', 'tipo_pieza', unique=True),
    )
    
    def __repr__(self):
        return f'<InventarioPieza {self.modelo_equipo} {self.tipo_pieza}: {self.cantidad}>'
    
    @property
    def bajo_stock(self):
        """Retorna True si el stock está por debajo del mínimo"""
        return self.cantidad < self.stock_minimo


class MovimientoPieza(db.Model):
    """
    Historial de movimientos de piezas (entradas/salidas)
    """
    __tablename__ = 'movimientos_piezas'
    
    id = db.Column(db.Integer, primary_key=True)
    pieza_id = db.Column(db.Integer, db.ForeignKey('inventario_piezas.id'), nullable=False)
    
    # ENTRADA, SALIDA, AJUSTE
    tipo_movimiento = db.Column(db.String(20), nullable=False)
    
    # Cantidad movida (positiva para entrada, negativa para salida)
    cantidad = db.Column(db.Integer, nullable=False)
    
    # Stock resultante después del movimiento
    stock_resultante = db.Column(db.Integer)
    
    # Referencia a solicitud de pieza (si aplica)
    solicitud_pieza_id = db.Column(db.Integer, db.ForeignKey('solicitudes_pieza.id'))
    
    # Detalles
    motivo = db.Column(db.Text)
    
    # Quién realizó el movimiento
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    
    # Relaciones
    pieza = db.relationship('InventarioPieza', backref='movimientos')
    usuario = db.relationship('User', backref='movimientos_piezas')
    solicitud = db.relationship('SolicitudPieza', backref='movimientos_pieza')
    
    __table_args__ = (
        Index('idx_mov_fecha', 'fecha'),
        Index('idx_mov_pieza', 'pieza_id', 'fecha'),
    )
    
    def __repr__(self):
        return f'<MovimientoPieza {self.tipo_movimiento} {self.cantidad}>'
