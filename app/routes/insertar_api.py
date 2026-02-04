from flask import Blueprint, request, jsonify, session
from app import db
from app.models.miner import Miner
from app.models.user import Movimiento
from app.utils.auth_decorators import login_required

insertion_bp = Blueprint('insertion', __name__)

@insertion_bp.route('/api/mineros/insertar', methods=['POST'])
@login_required
def insertar_minero():
    """Asigna ubicación final a un minero pendiente de colocación"""
    # HTMX o JSON
    data = request.get_json(silent=True) or request.form
    
    miner_id = data.get('id')
    wh = data.get('wh')
    rack = data.get('rack')
    fila = data.get('fila')
    columna = data.get('columna')
    
    if not all([miner_id, wh, rack, fila, columna]):
        return jsonify({'status': 'error', 'message': 'Faltan coordenadas'}), 400
        
    minero = Miner.query.get(miner_id)
    if not minero:
        return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404
        
    # Validar que si estaba pendiente, sea del mismo WH (opcional, pero buena práctica)
    if minero.warehouse_id and int(minero.warehouse_id) != int(wh):
        # Permitir mover entre WHs si es necesario, pero advertir o loguear
        pass
        
    # Verificar si el espacio está ocupado
    ocupante = Miner.query.filter_by(
        warehouse_id=wh, rack_id=rack, fila=fila, columna=columna
    ).first()
    
    if ocupante and ocupante.id != int(miner_id):
        return jsonify({'status': 'error', 'message': f'Lugar ocupado por {ocupante.sn_fisica}'}), 400
        
    # Actualizar
    minero.warehouse_id = wh
    minero.rack_id = rack
    minero.fila = fila
    minero.columna = columna
    minero.proceso_estado = 'operativo' # Ya está colocado
    
    # Log
    db.session.add(Movimiento(
        usuario_id=session['user_id'],
        accion="INSERCIÓN EN RACK",
        referencia_miner=f"SN: {minero.sn_fisica}",
        datos_nuevos=f"Ubicado en WH{wh}-R{rack}-F{fila}-C{columna}"
    ))
    db.session.commit()
    
    # Retornar el HTML del miner card para actualización en tiempo real
    from flask import render_template, make_response
    import json
    
    card_html = render_template('partials/miner_card.html',
                               m=minero, wh_actual=wh, rack_actual=rack, f=fila, c=columna)
    
    response = make_response(card_html, 200)
    # Disparar evento para actualizar lista de pendientes
    response.headers['HX-Trigger'] = json.dumps({
        'minerPlaced': {'id': miner_id}
    })
    return response
