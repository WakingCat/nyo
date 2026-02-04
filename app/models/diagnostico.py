from app import db
from datetime import datetime

class Diagnostico(db.Model):
    __tablename__ = 'diagnosticos'
    
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    miner_id = db.Column(db.Integer, db.ForeignKey('mineros.id'))
    
    # Snapshot de ubicación al momento del diag
    warehouse_id = db.Column(db.Integer)
    rack_id = db.Column(db.Integer)
    fila = db.Column(db.Integer)
    columna = db.Column(db.Integer)
    
    # Datos técnicos
    ip_address = db.Column(db.String(50))
    sn_fisica = db.Column(db.String(100))
    sn_digital = db.Column(db.String(100))
    
    # Diagnóstico y Resolución
    falla = db.Column(db.String(100))  # Enum: Frecuencia, Fuente, CB, etc.
    observacion = db.Column(db.Text)
    solucion = db.Column(db.String(100)) # Enum: Reinicio, Firmware, etc.
    
    # Relaciones
    usuario = db.relationship('User', backref='diagnosticos_realizados')
    miner = db.relationship('Miner', backref='historial_diagnosticos')

    def to_dict(self):
        return {
            'id': self.id,
            'fecha': self.fecha.strftime('%d/%m/%Y %H:%M'),
            'usuario': self.usuario.username if self.usuario else 'Desconocido',
            'ubicacion': f"WH{self.warehouse_id}-R{self.rack_id} (F{self.fila}-C{self.columna})",
            'sn_fisica': self.sn_fisica,
            'sn_digital': self.sn_digital,
            'ip': self.ip_address,
            'falla': self.falla,
            'observacion': self.observacion,
            'solucion': self.solucion
        }
