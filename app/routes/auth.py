from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.models.user import User
from app import db
from werkzeug.security import check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 1. Aquí definimos la variable como 'user'
        user = User.query.filter_by(email=email).first()
        
        # 2. Usamos 'user' para verificar la contraseña
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            
            # Verificamos que user.role exista antes de acceder
            if user.role:
                session['role'] = user.role.nombre_puesto
                session['depto'] = user.role.departamento
            else:
                session['role'] = 'Sin Rol'

            # --- NUEVA LÓGICA DE WH (Usando 'user') ---
            # El error estaba aquí: usábamos 'usuario' en vez de 'user'
            if user.wh_asignados:
                try:
                    # Convertimos el texto "1,2" en una lista [1, 2]
                    lista_wh = [int(x) for x in user.wh_asignados.split(',')]
                    session['mis_wh'] = lista_wh
                except ValueError:
                    # Si hay un error de formato (ej: "1, a"), dejamos lista vacía
                    session['mis_wh'] = []
            else:
                session['mis_wh'] = []
            # ------------------------------------------
            
            # --- NUEVA LÓGICA DE HYDRO ---
            if user.containers_asignados:
                try:
                    # Convertimos "1,2,3" en [1, 2, 3]
                    lista_containers = [int(x) for x in user.containers_asignados.split(',')]
                    session['mis_containers'] = lista_containers
                except ValueError:
                    session['mis_containers'] = []
            else:
                session['mis_containers'] = []
            
            return redirect(url_for('main.index'))
        
        flash('Correo o contraseña incorrectos', 'danger')
        
    return render_template('login.html')

@auth_bp.route('/verify/<token>')
def verify_token(token):
    user = User.query.filter_by(token_verificacion=token).first()
    
    if user:
        user.is_active = True
        user.token_verificacion = None
        db.session.commit()
        
        flash('¡Cuenta activada con éxito! Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))
    else:
        flash('El token es inválido o ya ha expirado.', 'danger')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))