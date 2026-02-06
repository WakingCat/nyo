"""
Lab Views Routes
Vistas del laboratorio (dashboards, solicitudes, stock, etc.)
"""
from flask import Blueprint, render_template, request, session, jsonify
from app.utils.auth_decorators import login_required
from app.utils.permission_decorators import lab_technician_required
from app.services.repair_service import repair_service
from app.models.miner import Miner
from app.models.user import Movimiento
from app import db

lab_bp = Blueprint('lab', __name__, url_prefix='/lab')


@lab_bp.route('/')
@login_required
@lab_technician_required()
def dashboard():
    """Dashboard central de laboratorio usando RepairService"""
    from app.services.transfer_service import transfer_service
    
    stats = repair_service.get_lab_stats()
    
    # Contador de traslados pendientes de validación del lab
    # Contador de traslados pendientes de validación del lab
    traslados_pendientes = transfer_service.get_pending_lab_approval()
    c_traslados_lab = len(traslados_pendientes)
    
    # NUEVO: Contador de conciliaciones pendientes (piezas)
    from app.models.solicitud_pieza import SolicitudPieza
    conciliaciones_pendientes = SolicitudPieza.query.filter_by(estado='pendiente_aprobacion_lab').count()
    
    return render_template('lab_hub.html', 
                           c_pendientes=stats['c_pendientes'],
                           c_reparacion=stats['c_reparacion'],
                           c_stock=stats['c_stock'],
                           c_scrap=stats['c_scrap'],
                           c_traslados_lab=c_traslados_lab,
                           c_conciliaciones=conciliaciones_pendientes)


@lab_bp.route('/validar-piezas')
@login_required
@lab_technician_required()
def validar_piezas():
    """Vista para aprobar/rechazar solicitudes de repuestos para conciliación"""
    from app.models.solicitud_pieza import SolicitudPieza
    pendientes = SolicitudPieza.query.filter_by(estado='pendiente_aprobacion_lab').order_by(SolicitudPieza.fecha_solicitud.asc()).all()
    return render_template('lab_validar_piezas.html', solicitudes=pendientes)


@lab_bp.route('/api/aprobar-pieza/<id>', methods=['POST'])
@login_required
@lab_technician_required()
def aprobar_pieza(id):
    """Aprueba la solicitud de pieza. Pasa a Depósito o aprueba traslado."""
    from app.models.solicitud_pieza import SolicitudPieza
    from app.models.solicitud import SolicitudTraslado
    from datetime import datetime
    
    try:
        solicitud = SolicitudPieza.query.get(id)
        if not solicitud:
            return jsonify({'status': 'error', 'message': 'No encontrado'}), 404
            
        solicitud.aprobador_lab_id = session['user_id']
        solicitud.fecha_aprobacion_lab = datetime.now()
        
        # Log approval
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="APROBACIÓN PIEZA LAB",
            referencia_miner=f"{solicitud.miner.sn_fisica}",
            datos_nuevos=f"Pieza {solicitud.tipo_pieza} aprobada para conciliación {solicitud.tipo_conciliacion}"
        ))
        
        if solicitud.tipo_conciliacion == 'WH':
            # In-Situ: Pasa a depósito para envío
            solicitud.estado = 'pendiente_deposito'
            
        elif solicitud.tipo_conciliacion == 'LAB':
            # En Lab: Aprueba la pieza Y avanza el traslado vinculado
            solicitud.estado = 'pendiente_deposito' # La pieza igual se pide al depósito
            
            if solicitud.solicitud_traslado_id:
                traslado = SolicitudTraslado.query.get(solicitud.solicitud_traslado_id)
                if traslado:
                    # Avanzar traslado a Coordinador
                    traslado.estado = 'pendiente_coordinador_hydro' if traslado.sector == 'Hydro' else 'pendiente_coordinador'
                    db.session.add(Movimiento(
                        usuario_id=session['user_id'],
                        accion="VALIDACIÓN TRASLADO LAB",
                        referencia_miner=f"Traslado #{traslado.id}",
                        datos_nuevos="Traslado validado por Lab (Conciliación). Pasa a Coordinador."
                    ))

        db.session.commit()
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@lab_bp.route('/api/rechazar-pieza/<id>', methods=['POST'])
@login_required
@lab_technician_required()
def rechazar_pieza(id):
    """Rechaza la solicitud de pieza."""
    from app.models.solicitud_pieza import SolicitudPieza
    from app.models.solicitud import SolicitudTraslado
    
    try:
        solicitud = SolicitudPieza.query.get(id)
        if not solicitud:
            return jsonify({'status': 'error', 'message': 'No encontrado'}), 404
            
        solicitud.estado = 'rechazado'
        
        # Si tenía traslado vinculado, ¿también se rechaza? Sí.
        if solicitud.solicitud_traslado_id:
            traslado = SolicitudTraslado.query.get(solicitud.solicitud_traslado_id)
            if traslado:
                traslado.estado = 'rechazado_lab'
                traslado.comentario_resolucion = "Rechazo automático por rechazo de pieza de conciliación."
        
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="RECHAZO PIEZA LAB",
            referencia_miner=f"{solicitud.miner.sn_fisica}",
            datos_nuevos=f"Solicitud rechazada."
        ))
        
        db.session.commit()
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@lab_bp.route('/solicitudes')
@login_required
@lab_technician_required()
def solicitudes():
    """Vista de solicitudes pendientes usando RepairService"""
    solicitudes = repair_service.get_pending_requests()
    return render_template('lab_solicitudes.html', solicitudes=solicitudes)


@lab_bp.route('/solicitudes-partial')
@login_required
@lab_technician_required()
def solicitudes_partial():
    """Partial HTMX para actualización automática de solicitudes"""
    solicitudes = repair_service.get_pending_requests()
    return render_template('partials/lab_solicitudes_body.html', solicitudes=solicitudes)


@lab_bp.route('/stock')
@login_required
@lab_technician_required()
def stock():
    """Stock de laboratorio con filtros por sector"""
    sector = request.args.get('sector')
    stock = repair_service.get_stock_lab(sector)
    return render_template('lab_stock.html', stock=stock, sector=sector)


@lab_bp.route('/stock-partial')
@login_required
@lab_technician_required()
def stock_partial():
    """Partial HTMX para actualización automática del stock"""
    sector = request.args.get('sector')
    stock = repair_service.get_stock_lab(sector)
    return render_template('partials/stock_grid.html', stock=stock, sector=sector)


@lab_bp.route('/cementerio')
@login_required
@lab_technician_required()
def cementerio():
    """Cementerio - equipos dados de baja"""
    scrap_list = repair_service.get_cemetery()
    return render_template('lab_scrap.html', lista=scrap_list)


@lab_bp.route('/reparacion')
@login_required
def reparacion():
    """Vista de mesa de trabajo usando RepairService"""
    en_mesa = repair_service.get_in_repair()
    return render_template('lab_reparacion.html', equipos=en_mesa)


@lab_bp.route('/reparacion-partial')
@login_required
@lab_technician_required()
def reparacion_partial():
    """Partial HTMX para actualización automática de mesa de trabajo"""
    equipos = repair_service.get_in_repair()
    return render_template('partials/lab_reparacion_grid.html', equipos=equipos)


@lab_bp.route('/stats-partial')
@login_required
def stats_partial():
    """Partial para actualización HTMX de estadísticas usando RepairService"""
    stats = repair_service.get_lab_stats()
    
    return render_template('partials/lab_stats.html', 
                           c_pendientes=stats['c_pendientes'],
                           c_reparacion=stats['c_reparacion'],
                           c_stock=stats['c_stock'],
                           c_scrap=stats['c_scrap'])


# ==========================================
# APIs DE LABORATORIO
# ==========================================

@lab_bp.route('/api/iniciar', methods=['POST'])
@login_required
@lab_technician_required()
def iniciar_reparacion():
    """Mueve equipo de Solicitudes a Mesa de Trabajo"""
    data = request.get_json(silent=True) or request.form
    miner_id = data.get('id')
    
    if not miner_id:
        miner_id = request.args.get('id')
    
    success = repair_service.start_repair(miner_id)
    
    if success:
        minero = Miner.query.get(miner_id)
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="INICIO REPARACIÓN",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos="Equipo en mesa de trabajo."
        ))
        db.session.commit()
        return '', 200
    
    return jsonify({'status': 'error'}), 404


@lab_bp.route('/api/terminar', methods=['POST'])
@login_required
@lab_technician_required()
def terminar_reparacion():
    """Finaliza reparación moviendo a Stock Lab"""
    data = request.get_json(silent=True) or request.form
    miner_id = data.get('id')
    solucion = data.get('solucion', 'Reparación estándar')
    
    success = repair_service.finish_repair(miner_id, solucion)
    
    if success:
        minero = Miner.query.get(miner_id)
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="REPARACIÓN FINALIZADA",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos=f"Equipo pasa a STOCK LAB. Solución: {solucion}"
        ))
        db.session.commit()
        return '', 200
    
    return jsonify({'status': 'error'}), 404


@lab_bp.route('/api/scrap', methods=['POST'])
@login_required
@lab_technician_required()
def scrap_equipo():
    """Da de baja un equipo"""
    data = request.get_json(silent=True) or request.form
    
    miner_id = data.get('id')
    tipo = data.get('tipo')
    motivo = data.get('motivo', 'Sin motivo irreparable')
    
    if tipo == 'basura':
        tipo_bd = 'baja_definitiva'
        accion_log = "BAJA (DESECHO)"
        msg_extra = "Equipo desechado/reciclado."
    else:
        tipo_bd = 'donante_piezas'
        accion_log = "BAJA (DESGUACE)"
        msg_extra = "Equipo almacenado como donante de repuestos."
    
    success = repair_service.scrap_miner(miner_id, tipo_bd, motivo)
    
    if success:
        minero = Miner.query.get(miner_id)
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion=accion_log,
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos=f"Motivo: {motivo}. {msg_extra}"
        ))
        db.session.commit()
        return jsonify({'status': 'ok'})
    
    return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404


@lab_bp.route('/api/reinstalar', methods=['POST'])
@login_required
@lab_technician_required()
def reinstalar_equipo():
    """Reinstala un equipo del stock lab a un warehouse"""
    data = request.get_json(silent=True) or request.form
    
    miner_id = data.get('id')
    wh = data.get('wh')
    
    rack = data.get('rack')
    fila = data.get('fila')
    columna = data.get('columna')
    
    if not miner_id or not wh:
        return jsonify({'status': 'error', 'message': 'Datos incompletos'}), 400
    
    def to_int_or_none(val):
        return int(val) if val and val != '' else None
        
    rack = to_int_or_none(rack)
    fila = to_int_or_none(fila)
    columna = to_int_or_none(columna)
    
    result = repair_service.return_to_warehouse(
        int(miner_id),
        int(wh),
        rack,
        fila,
        columna
    )
    
    if result.get('success'):
        minero = Miner.query.get(miner_id)
        
        if rack:
            destino_str = f"WH{wh}-R{rack}-F{fila}-C{columna}"
        else:
            destino_str = f"WH{wh} (Pendiente de colocación)"
            
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="REINSTALACIÓN",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos=f"Reinstalado en {destino_str}"
        ))
        db.session.commit()
        
        return jsonify({'status': 'ok', 'message': 'Equipo reinstalado exitosamente'})
    
    error_msg = result.get('error', 'Error al reinstalar')
    return jsonify({'status': 'error', 'message': error_msg}), 400


@lab_bp.route('/api/reinstalar-origen', methods=['POST'])
@login_required
@lab_technician_required()
def reinstalar_al_origen():
    """Reinstala un equipo Hydro a su posición original antes del traslado"""
    data = request.get_json(silent=True) or request.form
    
    miner_id = data.get('id')
    
    if not miner_id:
        return jsonify({'status': 'error', 'message': 'ID de minero requerido'}), 400
    
    minero = Miner.query.get(miner_id)
    if not minero:
        return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404
    
    # Usar servicio con use_origin=True
    result = repair_service.return_to_warehouse(
        int(miner_id),
        wh=100,  # Hydro WH ID
        use_origin=True
    )
    
    if result.get('success'):
        # Obtener ubicación actual
        destino_str = minero.ubicacion_str if minero.warehouse_id else "Origen"
            
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="REINSTALACIÓN ORIGEN",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos=f"Reinstalado en {destino_str}"
        ))
        db.session.commit()
        
        return jsonify({'status': 'ok', 'message': f'Equipo reinstalado en posición original'})
    
    error_msg = result.get('error', 'Error al reinstalar')
    return jsonify({'status': 'error', 'message': error_msg}), 400
