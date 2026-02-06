from app import db
from datetime import datetime
from sqlalchemy import Index
import re

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
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    
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

    def has_container_access(self, container_id: int) -> bool:
        """Verifica acceso a un contenedor específico de Hydro"""
        if not self.containers_asignados:
            # Si tiene WH 100 pero no contenedores específicos, ¿tiene acceso a todos?
            # Asumiremos que si no tiene contenedores definidos, NO tiene acceso a ninguno específico
            # salvo que sea Admin/Site Manager (que se valida antes)
            return False
            
        try:
            c_list = [int(x.strip()) for x in self.containers_asignados.split(',')]
            return container_id in c_list
        except (ValueError, AttributeError):
            return False

    def is_unauthorized_action(self, log_text: str) -> bool:
        """
        Detecta si la acción descrita en el log ocurrió en una ubicación 
        (WH o Contenedor) que el usuario NO tiene asignada.
        """
        if not log_text:
            return False
            
        # Roles exentos de alerta (tienen acceso global implícito)
        if self.role and self.role.nombre_puesto in ['Site Manager', 'Manager', 'Admin']:
            return False
            
        # Buscar patrón WH y posible Rack (Contenedor en Hydro)
        # Busca "WH1", "WH1-R5", "WH 100", etc.
        # Grupo 1: ID Warehouse
        # Grupo 2: ID Rack (Opcional, captura el dígito después de -R)
        matches = re.finditer(r'WH\s*(\d+)(?:-R(\d+))?', log_text, re.IGNORECASE)
        
        assigned_whs = self.get_assigned_warehouses()
        has_matches = False
        
        for m in matches:
            has_matches = True
            try:
                wh_id = int(m.group(1))
                
                # Caso 1: WH Normal (!= 100)
                if wh_id != 100:
                    if wh_id not in assigned_whs:
                        return True # Unauthorized!
                
                # Caso 2: Hydro (WH == 100)
                else:
                    # Si no tiene WH 100 asignado siquiera
                    if 100 not in assigned_whs:
                        return True
                        
                    # Si tiene WH 100, verificar contenedor (Rack)
                    container_id_str = m.group(2)
                    if container_id_str:
                        container_id = int(container_id_str)
                        if not self.has_container_access(container_id):
                            return True # Unauthorized Container!
            except ValueError:
                continue
                
        return False
    
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