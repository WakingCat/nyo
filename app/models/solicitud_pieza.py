from app import db
from datetime import datetime
from sqlalchemy import Index

class SolicitudPieza(db.Model):
    """
    Solicitud de pieza para conciliación.
    Flujo: Técnico WH -> Lab (aprueba) -> Depósito (despacha) -> Técnico WH (recibe)
    """
    __tablename__ = 'solicitudes_pieza'

    id = db.Column(db.Integer, primary_key=True)
    miner_id = db.Column(db.Integer, db.ForeignKey('mineros.id'), nullable=False)
    
    # ============================================
    # INFORMACIÓN DE LA SOLICITUD
    # ============================================
    
    # WH (In Situ) o LAB (Traslado)
    ubicacion_reparacion = db.Column(db.String(10), nullable=False) 
    
    # Pieza solicitada (PSU, HASHBOARD, FAN, CB, etc.)
    tipo_pieza = db.Column(db.String(50), nullable=False)
    
    # WH de origen del miner (para saber a dónde enviar la pieza)
    wh_origen = db.Column(db.Integer)
    
    # NUEVO: Tipo de Conciliación (WH=In-Situ, LAB=Prueba en Lab)
    tipo_conciliacion = db.Column(db.String(10), default='WH')
    
    # NUEVO: Link a solicitud de traslado (solo si tipo_conciliacion='LAB')
    solicitud_traslado_id = db.Column(db.Integer, db.ForeignKey('solicitudes_traslado.id'))
    
    # Detalles adicionales
    comentario = db.Column(db.Text)
    
    # ============================================
    # WORKFLOW STATUS
    # ============================================
    # Estados:
    # 1. pendiente_aprobacion_lab -> Lab debe aprobar
    # 2. pendiente_deposito -> Depósito debe preparar y enviar
    # 3. en_camino -> Pieza en tránsito
    # 4. recibido -> Técnico WH recibió la pieza
    # 5. finalizado -> Conciliación completada
    # 6. rechazado -> Lab o Depósito rechazó
    estado = db.Column(db.String(50), default='pendiente_aprobacion_lab')
    
    # ============================================
    # TRACKING DE USUARIOS Y FECHAS
    # ============================================
    
    # Quién solicitó (Técnico/Supervisor WH)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    fecha_solicitud = db.Column(db.DateTime, default=datetime.now)
    
    # Quién aprobó en el Lab
    aprobador_lab_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    fecha_aprobacion_lab = db.Column(db.DateTime)
    
    # Quién despachó en Depósito
    despachador_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    fecha_despacho = db.Column(db.DateTime)
    
    # Fecha de recepción por el solicitante
    fecha_recepcion = db.Column(db.DateTime)
    
    # ============================================
    # DATOS DEL PRODUCTO DESPACHADO
    # ============================================
    
    # Serial Number del producto despachado (ej: SN de PSU)
    producto_sn = db.Column(db.String(100))
    
    # Modelo del producto (ej: APW12, APW9+, etc.)
    producto_modelo = db.Column(db.String(100))
    
    # Cantidad (generalmente 1, pero puede ser más para fans)
    producto_cantidad = db.Column(db.Integer, default=1)
    
    # Notas del depósito
    notas_deposito = db.Column(db.Text)
    
    # ============================================
    # RELACIONES
    # ============================================
    
    miner = db.relationship('Miner', backref='solicitudes_pieza')
    solicitante = db.relationship('User', foreign_keys=[solicitante_id], 
                                  backref='solicitudes_pieza_creadas')
    aprobador_lab = db.relationship('User', foreign_keys=[aprobador_lab_id],
                                    backref='solicitudes_pieza_aprobadas')
    despachador = db.relationship('User', foreign_keys=[despachador_id],
                                  backref='solicitudes_pieza_despachadas')
    
    # Índices para búsquedas frecuentes
    __table_args__ = (
        Index('idx_solicitud_estado', 'estado'),
        Index('idx_solicitud_fecha', 'fecha_solicitud'),
    )

    def __repr__(self):
        return f'<SolicitudPieza {self.id} {self.tipo_pieza} ({self.estado})>'
    
    @property
    def solicitante_info(self):
        """Retorna info completa del solicitante"""
        if self.solicitante:
            return {
                'nombre': self.solicitante.username,
                'rol': self.solicitante.role.nombre_puesto if self.solicitante.role else 'N/A'
            }
        return {'nombre': 'N/A', 'rol': 'N/A'}
    
    @property
    def miner_info(self):
        """Retorna info del miner asociado"""
        if self.miner:
            ubicacion = f"WH{self.miner.warehouse_id}-R{self.miner.rack_id}" if self.miner.warehouse_id else "Sin ubicación"
            return {
                'sn': self.miner.sn_fisica,
                'modelo': self.miner.modelo,
                'ubicacion': ubicacion,
                'wh': self.miner.warehouse_id
            }
        return {'sn': 'N/A', 'modelo': 'N/A', 'ubicacion': 'N/A', 'wh': None}
