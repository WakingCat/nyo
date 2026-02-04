from app import db
from datetime import datetime


class SolicitudTraslado(db.Model):
    __tablename__ = 'solicitudes_traslado'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Minero a trasladar
    miner_id = db.Column(db.Integer, db.ForeignKey('mineros.id'), nullable=False)
    
    # Ubicación origen
    origen_wh = db.Column(db.Integer)
    origen_rack = db.Column(db.Integer)
    origen_fila = db.Column(db.Integer)
    origen_columna = db.Column(db.Integer)
    
    # Destino
    destino = db.Column(db.String(50), nullable=False)  # 'LAB', 'WH2', etc.
    
    # Sector del minero
    sector = db.Column(db.Enum('WH', 'Hydro'), nullable=False)
    
    # Estado del workflow
    # pendiente_lab: Esperando aprobación del laboratorio
    # pendiente_coordinador_hydro: (Solo Hydro) Esperando aprobación del Coordinador Hydro
    # pendiente_coordinador: Esperando aprobación del Coordinador final
    # pendiente: Estado legacy, equivalente a pendiente_coordinador
    estado = db.Column(
        db.Enum('pendiente_lab', 'pendiente_coordinador', 'pendiente_coordinador_hydro', 'pendiente', 'aprobado', 'rechazado', 'rechazado_lab', 'ejecutado'),
        default='pendiente_lab'
    )
    
    # Datos de la solicitud
    motivo = db.Column(db.Text, nullable=False)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha_solicitud = db.Column(db.DateTime, default=datetime.now)
    
    # Datos de aprobación/rechazo
    aprobador_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    fecha_resolucion = db.Column(db.DateTime)
    comentario_resolucion = db.Column(db.Text)
    
    # Relaciones
    miner = db.relationship('Miner', backref='solicitudes_traslado')
    solicitante = db.relationship('User', foreign_keys=[solicitante_id], backref='solicitudes_creadas')
    aprobador = db.relationship('User', foreign_keys=[aprobador_id], backref='solicitudes_resueltas')
    
    def __repr__(self):
        return f'<SolicitudTraslado {self.id} - {self.estado}>'
    
    @property
    def puede_ser_aprobada(self):
        """Verifica si la solicitud puede ser aprobada"""
        return self.estado == 'pendiente'
    
    @property
    def origen_str(self):
        """Retorna string de origen formateado según sector"""
        if not self.origen_wh:
            return "Desconocido"
        
        # Hydro: Mostrar como C60-A-Fila-Col
        HYDRO_WH_ID = 100
        if self.origen_wh == HYDRO_WH_ID or self.sector == 'Hydro':
            container = (self.origen_rack + 1) // 2
            rack_letra = 'A' if self.origen_rack % 2 == 1 else 'B'
            return f"C{container}-{rack_letra}-{self.origen_fila}-{self.origen_columna}"
        
        # WH normal
        return f"WH{self.origen_wh}-R{self.origen_rack}"
