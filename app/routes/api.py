from flask import Blueprint, request, jsonify
from app.models.miner import Miner
from app import db
from app.utils.auth_decorators import login_required

# El prefix '/api' ya está definido aquí
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/guardar_json', methods=['POST'])
@login_required
def guardar_json():
    """Ruta para guardado vía API JSON (no HTMX)"""
    data = request.json
    minero = Miner.query.filter_by(
        warehouse_id=data['wh'], rack_id=data['rack'],
        fila=data['fila'], columna=data['columna']
    ).first()

    if not minero:
        minero = Miner(warehouse_id=data['wh'], rack_id=data['rack'], 
                       fila=data['fila'], columna=data['columna'])

    minero.modelo = data['modelo']
    minero.sn_fisica = data['sn_fisica']
    minero.ths = float(data['ths']) if data['ths'] else 0
    db.session.add(minero)
    db.session.commit()
    return jsonify({"status": "success", "message": "Actualizado vía JSON"})

@api_bp.route('/vaciar', methods=['POST'])
@login_required
def vaciar():
    """Limpia una posición de la base de datos"""
    data = request.json
    minero = Miner.query.filter_by(
        warehouse_id=data['wh'], rack_id=data['rack'],
        fila=data['fila'], columna=data['columna']
    ).first()
    
    if minero:
        db.session.delete(minero)
        db.session.commit()
        return jsonify({"status": "success", "message": "Posición vaciada"})
    
    return jsonify({"status": "error", "message": "No hay minero en esta posición"}), 404

@api_bp.route('/personal/assign', methods=['POST'])
@login_required
def assign_personnel():
    """API para asignar personal a ubicaciones (WH/Hydro)"""
    from app.services.user_service import user_service
    from flask import session
    
    # Verificación de permisos de rol (Coordinador+)
    user_role = session.get('role', '')
    if not any(x in user_role for x in ['Coordinador', 'Site Manager', 'Manager']):
        return jsonify({'status': 'error', 'message': 'No tienes permisos para realizar esta acción'}), 403

    data = request.json
    user_id = data.get('user_id')
    wh_list = data.get('wh_list')
    hydro_list = data.get('hydro_list')
    
    # Validaciones específicas de departamento
    user_dept = session.get('depto', '')
    is_site = 'Site Manager' in user_role
    
    # Coordinador WH no puede tocar Hydro
    if not is_site and user_dept == 'WH' and hydro_list is not None:
         # Ignoramos lo que mande de hydro, o lanzamos error. Mejor ignorar para no borrar accidentalmente.
         hydro_list = None
         
    # Coordinador Hydro no puede tocar WH
    if not is_site and user_dept == 'Hydro' and wh_list is not None:
         wh_list = None

    success, msg = user_service.update_assignments(user_id, wh_list, hydro_list)
    
    if success:
        return jsonify({'status': 'ok', 'message': msg})
    else:
        return jsonify({'status': 'error', 'message': msg}), 500