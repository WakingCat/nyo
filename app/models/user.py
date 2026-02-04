from app import db
from datetime import datetime
from sqlalchemy import Index

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    nombre_puesto = db.Column(db.String(100), unique=True, nullable=False)
    departamento = db.Column(db.String(50), nullable=False)
    
    # RELACIÓN: Un rol tiene muchos usuarios.
    # El 'backref="role"' inyecta automáticamente la propiedad .role en la clase User.
    usuarios = db.relationship('User', backref='role', lazy=True)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    
    # Asignaciones
    wh_asignados = db.Column(db.String(50))   # Para WH: "1,2"
    containers_asignados = db.Column(db.Text) # Para Hydro: "1,2,3...100" (TEXT permite listas largas)
    
    is_active = db.Column(db.Boolean, default=False)
    token_verificacion = db.Column(db.String(100), unique=True)
    
    # NOTA: Borramos la línea "role = db.relationship..." porque ya la definimos arriba en Role.
    
    # Relación con Movimientos
    # El 'backref="usuario"' inyecta la propiedad .usuario en la clase Movimiento
    movimientos = db.relationship('Movimiento', backref='usuario', lazy='dynamic')
    
    # ==========================================
    # MÉTODOS HELPER PARA PERMISOS
    # ==========================================
    
    def has_warehouse_access(self, wh_id: int) -> bool:
        """
        Verifica si el usuario tiene acceso a un warehouse específico
        
        Args:
            wh_id: ID del warehouse a verificar
            
        Returns:
            True si tiene acceso, False si no
        """
        if not self.wh_asignados:
            return False
        
        try:
            wh_list = [int(x.strip()) for x in self.wh_asignados.split(',')]
            return wh_id in wh_list
        except (ValueError, AttributeError):
            return False
    
    def is_admin(self) -> bool:
        """
        Verifica si el usuario tiene rol administrativo
        
        Returns:
            True si es Site Manager, Coordinador o Manager
        """
        if not self.role:
            return False
        
        admin_keywords = ['Site Manager', 'Coordinador', 'Manager']
        return any(keyword in self.role.nombre_puesto for keyword in admin_keywords)
    
    def is_supervisor(self) -> bool:
        """
        Verifica si el usuario es Supervisor o superior
        
        Returns:
            True si es Supervisor, Coordinador o Manager
        """
        if not self.role:
            return False
        
        supervisor_keywords = ['Supervisor', 'Coordinador', 'Site Manager', 'Manager']
        return any(keyword in self.role.nombre_puesto for keyword in supervisor_keywords)
    
    def can_access_lab(self) -> bool:
        """
        Verifica si el usuario puede acceder a funciones de laboratorio
        
        Returns:
            True si es personal de Lab o admin global
        """
        if not self.role:
            return False
        
        return (
            self.role.departamento in ['Lab', 'Global'] or
            self.is_admin()
        )
    
    def can_approve_rma(self) -> bool:
        """
        Verifica si puede aprobar RMAs
        
        Returns:
            True si es Supervisor o superior
        """
        return self.is_supervisor()
    
    def get_assigned_warehouses(self) -> list:
        """
        Obtiene la lista de warehouses asignados
        
        Returns:
            Lista de IDs de warehouses (ej: [1, 2, 3])
        """
        if not self.wh_asignados:
            return []
        
        try:
            return [int(x.strip()) for x in self.wh_asignados.split(',')]
        except (ValueError, AttributeError):
            return []
    
    def __repr__(self):
        return f'<User {self.username}>'

class Movimiento(db.Model):
    __tablename__ = 'historial_movimientos'
    id = db.Column(db.Integer, primary_key=True)
    
    # CORRECCIÓN IMPORTANTE: La tabla se llama 'users', no 'usuarios'
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    accion = db.Column(db.String(255), nullable=False) # Ej: "ENVÍO RMA"
    referencia_miner = db.Column(db.String(100)) # Ej: "WH1-R5-10:2"
    datos_nuevos = db.Column(db.Text) # Detalles del cambio
    
    fecha_hora = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_fecha', 'fecha_hora'),
    )