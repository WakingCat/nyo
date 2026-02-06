"""
API Routes
APIs de búsqueda y consulta de datos de mineros
"""
from flask import Blueprint, render_template, request, jsonify
from app.utils.auth_decorators import login_required
from app.services.miner_service import miner_service

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/buscar')
@login_required
def buscar_minero():
    """API de búsqueda de mineros usando MinerService"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'found': False})
    
    resultados = miner_service.search_miners(query)
    
    if resultados:
        return jsonify({
            'found': True,
            'total': len(resultados),
            'resultados': resultados
        })
    
    return jsonify({'found': False})


@api_bp.route('/get_miner/<int:wh>/<int:rack>/<int:f>/<int:c>')
@login_required
def get_miner_data(wh, rack, f, c):
    """API para obtener datos de un minero específico usando MinerService"""
    m = miner_service.get_miner_by_position(wh, rack, f, c)
    
    if m:
        # Check if there's a pending transfer request
        from app.models.solicitud import SolicitudTraslado
        traslado_pendiente = SolicitudTraslado.query.filter(
            SolicitudTraslado.miner_id == m.id,
            SolicitudTraslado.estado.in_(['pendiente_lab', 'pendiente_coordinador', 'pendiente_coordinador_hydro', 'pendiente', 'aprobado'])
        ).first() is not None
        
        return jsonify({
            'id': m.id,
            'modelo': m.modelo,
            'ths': m.ths,
            'ip_address': m.ip_address,
            'mac_address': m.mac_address,
            'sn_fisica': m.sn_fisica,
            'sn_digital': m.sn_digital or '',
            'psu_model': m.psu_model or '',
            'psu_sn': m.psu_sn,
            'cb_sn': m.cb_sn,
            'hb1_sn': m.hb1_sn or '',
            'hb2_sn': m.hb2_sn or '',
            'hb3_sn': m.hb3_sn or '',
            'estado': m.proceso_estado,
            'proceso_estado': m.proceso_estado,
            'diagnostico': m.diagnostico_detalle,
            'diagnostico_detalle': m.diagnostico_detalle,
            'log': m.log_detalle,
            'traslado_pendiente': traslado_pendiente
        })
    
    return jsonify({})


@api_bp.route('/check-miner/<int:wh>/<int:rack>/<int:f>/<int:c>')
@login_required
def check_miner(wh, rack, f, c):
    """Verifica si un miner existe en la posición - para auto-removal en tiempo real"""
    event_wh = request.args.get('event_wh', type=int)
    event_rack = request.args.get('event_rack', type=int)
    event_fila = request.args.get('event_fila', type=int)
    event_columna = request.args.get('event_columna', type=int)
    
    if event_wh == wh and event_rack == rack and event_fila == f and event_columna == c:
        m = miner_service.get_miner_by_position(wh, rack, f, c)
        if not m:
            return render_template('partials/miner_card.html',
                                 m=None, wh_actual=wh, rack_actual=rack, f=f, c=c)
    
    m = miner_service.get_miner_by_position(wh, rack, f, c)
    return render_template('partials/miner_card.html',
                         m=m, wh_actual=wh, rack_actual=rack, f=f, c=c)
