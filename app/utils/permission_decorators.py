"""
Decoradores de Permisos Granulares
Proporciona control de acceso basado en roles, departamentos y warehouses
"""
from functools import wraps
from flask import session, redirect, url_for, flash, abort
from app.models.user import User


def department_required(allowed_departments: list):
    """
    Requiere que el usuario pertenezca a uno de los departamentos especificados
    
    Args:
        allowed_departments: Lista de departamentos permitidos (ej: ['WH', 'Lab', 'Global'])
        
    Uso:
        @department_required(['Lab', 'Global'])
        def vista_laboratorio():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verificar que el usuario esté logueado
            if 'user_id' not in session:
                flash("Debes iniciar sesión para acceder.", "warning")
                return redirect(url_for('auth.login'))
            
            # Site Manager tiene acceso a todos los departamentos
            user_role = session.get('role', '')
            if 'Site Manager' in user_role:
                return f(*args, **kwargs)
            
            # Obtener departamento del usuario desde la sesión
            user_dept = session.get('depto', '')
            
            # Verificar si el departamento del usuario está en la lista permitida
            if user_dept not in allowed_departments:
                flash(f"Acceso denegado. Esta sección es solo para: {', '.join(allowed_departments)}", "danger")
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(allowed_roles: list):
    """
    Requiere que el usuario tenga uno de los roles especificados
    
    Args:
        allowed_roles: Lista de nombres de roles permitidos
        
    Uso:
        @role_required(['Site Manager', 'Coordinador WH', 'Supervisor WH'])
        def aprobar_movimiento():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Debes iniciar sesión para acceder.", "warning")
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role', '')
            
            # Verificar si el rol del usuario está en la lista permitida
            if user_role not in allowed_roles:
                flash(f"No tienes permisos suficientes. Se requiere uno de: {', '.join(allowed_roles)}", "danger")
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def warehouse_permission_required():
    """
    Verifica que el usuario tenga acceso al warehouse especificado en la ruta
    
    Este decorador espera que la función de vista tenga un parámetro 'wh' (warehouse id)
    
    Uso:
        @warehouse_permission_required()
        def dashboard(wh, rack):
            # Solo usuarios con acceso a ese WH pueden ver este dashboard
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Debes iniciar sesión para acceder.", "warning")
                return redirect(url_for('auth.login'))
            
            # Obtener el warehouse_id del parámetro de la ruta
            wh = kwargs.get('wh') or args[0] if args else None
            
            if wh is None:
                # Si no hay wh en la ruta, permitir acceso (no aplica restricción)
                return f(*args, **kwargs)
            
            # Verificar si es admin (acceso total)
            user_role = session.get('role', '')
            if 'Site Manager' in user_role or 'Coordinador' in user_role:
                # Admins tienen acceso a todos los warehouses
                return f(*args, **kwargs)
            
            # Verificar acceso específico al warehouse
            mis_wh = session.get('mis_wh', [])
            
            if wh not in mis_wh:
                flash(f"No tienes acceso al Warehouse {wh}. Tus warehouses asignados: {', '.join(map(str, mis_wh))}", "danger")
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def supervisor_or_admin_required():
    """
    Requiere que el usuario sea Supervisor o superior (Coordinador, Site Manager)
    
    Uso:
        @supervisor_or_admin_required()
        def aprobar_rma():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Debes iniciar sesión para acceder.", "warning")
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role', '')
            
            # Lista de roles permitidos
            allowed_keywords = ['Supervisor', 'Coordinador', 'Site Manager', 'Manager']
            
            # Verificar si alguna palabra clave está en el rol
            has_permission = any(keyword in user_role for keyword in allowed_keywords)
            
            if not has_permission:
                flash("Solo supervisores y administradores pueden acceder a esta función.", "danger")
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def lab_technician_required():
    """
    Requiere que el usuario sea técnico de laboratorio o superior
    
    Uso:
        @lab_technician_required()
        def lab_solicitudes():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Debes iniciar sesión para acceder.", "warning")
                return redirect(url_for('auth.login'))
            
            user_dept = session.get('depto', '')
            user_role = session.get('role', '')
            
            # Permitir acceso a personal de Lab o Admins globales
            allowed = (
                user_dept == 'Lab' or 
                user_dept == 'Global' or
                'Site Manager' in user_role or
                'Coordinador' in user_role
            )
            
            if not allowed:
                flash("Esta sección es solo para personal de Laboratorio.", "danger")
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def api_permission_check(required_action: str):
    """
    Decorador para APIs que verifica permisos basados en la acción
    Retorna JSON en vez de redirect para APIs
    
    Args:
        required_action: Tipo de acción ('read', 'write', 'delete', 'admin')
    
    Uso:
        @api_permission_check('write')
        def api_guardar():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return {'error': 'No autenticado', 'status': 'unauthorized'}, 401
            
            user_role = session.get('role', '')
            
            # Definir niveles de permisos
            if required_action == 'admin':
                # Solo Site Manager y Coordinadores
                if not any(x in user_role for x in ['Site Manager', 'Coordinador']):
                    return {'error': 'Permisos insuficientes', 'status': 'forbidden'}, 403
            
            elif required_action == 'delete':
                # Supervisores y superiores
                if not any(x in user_role for x in ['Supervisor', 'Coordinador', 'Site Manager']):
                    return {'error': 'Solo supervisores pueden eliminar', 'status': 'forbidden'}, 403
            
            elif required_action == 'write':
                # Todos pueden escribir (pero se loguea)
                pass
            
            # Si pasa todas las verificaciones
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def coordinator_or_higher_required():
    """
    Requiere que el usuario sea Supervisor, Coordinador, Site Manager o Admin
    Usado para acciones críticas como traslados al laboratorio
    
    Uso:
        @coordinator_or_higher_required()
        def enviar_a_laboratorio():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Debes iniciar sesión para acceder.", "warning")
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role', '')
            
            # Lista de roles con permisos (ampliada para incluir Supervisores)
            allowed_keywords = ['Supervisor', 'Coordinador', 'Site Manager', 'Admin', 'Manager']
            
            # Verificar si alguna palabra clave está en el rol
            has_permission = any(keyword in user_role for keyword in allowed_keywords)
            
            if not has_permission:
                flash("Solo personal de supervisión o superior puede autorizar traslados al laboratorio.", "danger")
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

