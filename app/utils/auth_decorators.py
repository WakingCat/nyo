from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # El chequeo y el url_for van AQUÍ ADENTRO
        if 'user_id' not in session:
            flash("Debes iniciar sesión para acceder.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Aquí también, todo adentro de la función anidada
        roles_permitidos = ['Coordinador', 'Supervisor', 'Manager', 'Site Manager']
        user_role = session.get('role', '')
        
        es_jefe = any(word in user_role for word in roles_permitidos)
        
        if not es_jefe:
            flash("No tienes permisos para acceder a esta sección.", "danger")
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function