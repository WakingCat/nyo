from flask import Blueprint, render_template, request, session, jsonify, redirect, url_for
from app.utils.auth_decorators import login_required
from app.utils.permission_decorators import supervisor_or_admin_required
from app.services.transfer_service import transfer_service
from app.models.solicitud import SolicitudTraslado
from app.models.user import User
from app import db

transfers_bp = Blueprint('transfers', __name__, url_prefix='/traslados')


@transfers_bp.route('/panel')
@login_required
@supervisor_or_admin_required()
def panel():
    """Panel de aprobación de solicitudes - Solo Coordinadores y Site Manager"""
    sector = request.args.get('sector')  # 'WH' o 'Hydro'
    
    # Si no hay sector especificado, usar default según el rol del usuario
    if not sector:
        user_role = session.get('role', '')
        # Coordinador Hydro ve Hydro por default, todos los demás ven WH
        if 'Hydro' in user_role:
            sector = 'Hydro'
        else:
            sector = 'WH'
    
    solicitudes = transfer_service.get_pending_by_sector(sector)
    contadores = transfer_service.get_pending_count_by_sector()
    
    return render_template('traslados_panel.html',
                          solicitudes=solicitudes,
                          contadores=contadores,
                          sector_actual=sector)


@transfers_bp.route('/panel-partial')
@login_required
@supervisor_or_admin_required()
def panel_partial():
    """Partial HTMX para actualización automática del panel"""
    sector = request.args.get('sector')
    
    solicitudes = transfer_service.get_pending_by_sector(sector)
    
    return render_template('partials/solicitudes_table.html',
                          solicitudes=solicitudes)


@transfers_bp.route('/badge-count')
@login_required
def badge_count():
    """Partial HTMX para badge de notificación en sidebar"""
    contadores = transfer_service.get_pending_count_by_sector()
    total = contadores['total']
    
    if total > 0:
        return f'<span class="badge bg-danger rounded-pill">{total}</span>'
    return ''


@transfers_bp.route('/contadores-partial')
@login_required
@supervisor_or_admin_required()
def contadores_partial():
    """Partial HTMX para contadores en el panel"""
    contadores = transfer_service.get_pending_count_by_sector()
    return render_template('partials/contadores_traslado.html',
                         contadores=contadores)



@transfers_bp.route('/solicitar', methods=['POST'])
@login_required
def solicitar():
    """Crear nueva solicitud de traslado"""
    data = request.json
    
    try:
        solicitud = transfer_service.create_request(
            miner_id=data['miner_id'],
            destino=data.get('destino', 'LAB'),
            motivo=data['motivo'],
            solicitante_id=session['user_id']
        )
        
        return jsonify({
            'status': 'ok',
            'message': 'Solicitud creada exitosamente',
            'solicitud_id': solicitud.id
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400


@transfers_bp.route('/aprobar/<int:solicitud_id>', methods=['POST'])
@login_required
@supervisor_or_admin_required()
def aprobar(solicitud_id):
    """Aprobar una solicitud individual"""
    solicitud = SolicitudTraslado.query.get_or_404(solicitud_id)
    user = User.query.get(session['user_id'])
    
    # Verificar permisos
    if not transfer_service.can_user_approve(user, solicitud):
        return '<div class="alert alert-danger">No tienes permisos para aprobar esta solicitud</div>', 403
    
    comentario = request.form.get('comentario', '')
    
    # Guardar datos del miner ANTES de ejecutar el traslado (se limpian después)
    miner_data = {
        'wh': solicitud.origen_wh,
        'rack': solicitud.origen_rack,
        'fila': solicitud.origen_fila,
        'columna': solicitud.origen_columna
    }
    
    if transfer_service.approve_request(solicitud_id, session['user_id'], comentario):
        # Ejecutar traslado automáticamente
        transfer_service.execute_transfer(solicitud_id)
        
        # Crear respuesta con eventos HTMX personalizados para actualización en tiempo real
        from flask import make_response
        import json
        
        response = make_response('', 200)
        response.headers['HX-Trigger'] = json.dumps({
            'minerRemoved': miner_data,           # Para remover del dashboard
            'transferApproved': {'count': 1}      # Para actualizar badges
        })
        return response
    
    return '<div class="alert alert-danger">Error al aprobar</div>', 400


@transfers_bp.route('/rechazar/<int:solicitud_id>', methods=['POST'])
@login_required
@supervisor_or_admin_required()
def rechazar(solicitud_id):
    """Rechazar una solicitud individual"""
    solicitud = SolicitudTraslado.query.get_or_404(solicitud_id)
    user = User.query.get(session['user_id'])
    
    if not transfer_service.can_user_approve(user, solicitud):
        return '<div class="alert alert-danger">No tienes permisos</div>', 403
    
    comentario = request.form.get('comentario', 'Rechazado')
    
    if transfer_service.reject_request(solicitud_id, session['user_id'], comentario):
        # Crear respuesta con evento para actualizar badges
        from flask import make_response
        import json
        
        response = make_response('', 200)
        response.headers['HX-Trigger'] = json.dumps({
            'transferApproved': {'count': 1}  # Mismo evento para actualizar contadores
        })
        return response
    
    return '<div class="alert alert-danger">Error al rechazar</div>', 400


@transfers_bp.route('/aprobar-hydro/<int:solicitud_id>', methods=['POST'])
@login_required
@supervisor_or_admin_required()
def aprobar_hydro(solicitud_id):
    """Aprobación específica por Coordinador Hydro"""
    solicitud = SolicitudTraslado.query.get_or_404(solicitud_id)
    user = User.query.get(session['user_id'])
    
    # Verificar que sea Coordinador Hydro o Site Manager
    role_name = user.role.nombre_puesto if user.role else ''
    if 'Coordinador Hydro' not in role_name and 'Site Manager' not in role_name:
        return '<div class="alert alert-danger">Solo Coordinador Hydro puede aprobar esta solicitud</div>', 403
    
    # Guardar datos del miner ANTES de ejecutar (se limpian después)
    miner_data = {
        'wh': solicitud.origen_wh,
        'rack': solicitud.origen_rack,
        'fila': solicitud.origen_fila,
        'columna': solicitud.origen_columna
    }
    
    if transfer_service.hydro_coordinator_approve(solicitud_id, session['user_id']):
        # Ejecutar traslado automáticamente
        transfer_service.execute_transfer(solicitud_id)
        
        from flask import make_response
        import json
        
        response = make_response('', 200)
        response.headers['HX-Trigger'] = json.dumps({
            'minerRemoved': miner_data,
            'transferApproved': {'count': 1}
        })
        return response
    
    return '<div class="alert alert-danger">Error al aprobar</div>', 400


@transfers_bp.route('/aprobar-masivo', methods=['POST'])
@login_required
@supervisor_or_admin_required()
def aprobar_masivo():
    """Aprobar múltiples solicitudes a la vez"""
    ids = request.form.getlist('ids')
    
    if not ids:
        return '<div class="alert alert-warning">No se seleccionaron solicitudes</div>', 400
    
    # Convertir a integers
    solicitud_ids = [int(id) for id in ids]
    
    # Aprobar todas
    count = transfer_service.approve_bulk(solicitud_ids, session['user_id'])
    
    # Ejecutar traslados
    for sol_id in solicitud_ids:
        transfer_service.execute_transfer(sol_id)
    
    # Recargar tabla completa
    sector = request.args.get('sector')
    solicitudes = transfer_service.get_pending_by_sector(sector)
    
    return render_template('partials/solicitudes_table.html',
                          solicitudes=solicitudes)


@transfers_bp.route('/historial')
@login_required
@supervisor_or_admin_required()
def historial():
    """Ver historial de todas las solicitudes"""
    solicitudes = SolicitudTraslado.query.order_by(
        SolicitudTraslado.fecha_solicitud.desc()
    ).limit(100).all()
    
    return render_template('traslados_historial.html',
                          solicitudes=solicitudes)
