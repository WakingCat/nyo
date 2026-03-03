"""
Lab Views Routes
Vistas del laboratorio (dashboards, solicitudes, stock, etc.)
"""
from flask import Blueprint, render_template, request, session, jsonify, redirect, url_for, flash
from flask import Response
from app.utils.auth_decorators import login_required
from app.utils.permission_decorators import lab_technician_required
from app.services.repair_service import repair_service
from app.models.miner import Miner
from app.models.solicitud import SolicitudTraslado
from app.models.user import Movimiento
from app import db
import csv
import io
from datetime import datetime

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
        
        tipo_conciliacion = (solicitud.tipo_conciliacion or 'WH').upper()

        if tipo_conciliacion == 'WH':
            # In-Situ: Pasa directo a Depósito
            solicitud.estado = 'pendiente_deposito'
            
        elif tipo_conciliacion == 'LAB':
            # En Lab: primero Coordinador, luego Depósito
            solicitud.estado = 'pendiente_coordinador'
            
            if solicitud.solicitud_traslado_id:
                traslado = SolicitudTraslado.query.get(solicitud.solicitud_traslado_id)
                if traslado:
                    # Avanzar traslado a Coordinador (Hydro mantiene su coordinador específico)
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
    current_month = datetime.now().strftime('%Y-%m')
    return render_template('lab_solicitudes.html', solicitudes=solicitudes, current_month=current_month)


@lab_bp.route('/solicitudes/csv-mensual')
@login_required
@lab_technician_required()
def solicitudes_csv_mensual():
    """Descarga CSV mensual de todos los RMA registrados en el mes indicado."""
    month_str = (request.args.get('month') or '').strip()
    try:
        if month_str:
            period_start = datetime.strptime(month_str, '%Y-%m')
        else:
            now = datetime.now()
            period_start = datetime(now.year, now.month, 1)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de mes inválido. Use YYYY-MM'}), 400

    if period_start.month == 12:
        period_end = datetime(period_start.year + 1, 1, 1)
    else:
        period_end = datetime(period_start.year, period_start.month + 1, 1)

    solicitudes_mes = SolicitudTraslado.query.filter(
        SolicitudTraslado.motivo.ilike('RMA:%'),
        SolicitudTraslado.fecha_solicitud >= period_start,
        SolicitudTraslado.fecha_solicitud < period_end
    ).order_by(SolicitudTraslado.fecha_solicitud.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'fecha_solicitud', 'estado', 'origen', 'destino', 'sector', 'motivo',
        'sn_fisica', 'sn_digital', 'modelo', 'falla_reportada', 'ip', 'mac',
        'ths', 'psu_model', 'psu_sn', 'cb_sn', 'hb1_sn', 'hb2_sn', 'hb3_sn'
    ])

    for s in solicitudes_mes:
        m = s.miner
        writer.writerow([
            s.fecha_solicitud.strftime('%Y-%m-%d %H:%M:%S') if s.fecha_solicitud else '',
            s.estado or '',
            s.origen_str or '',
            s.destino or '',
            s.sector or '',
            s.motivo or '',
            m.sn_fisica if m else '',
            m.sn_digital if m else '',
            m.modelo if m else '',
            m.diagnostico_detalle if m else '',
            m.ip_address if m else '',
            m.mac_address if m else '',
            m.ths if m else '',
            m.psu_model if m else '',
            m.psu_sn if m else '',
            m.cb_sn if m else '',
            m.hb1_sn if m else '',
            m.hb2_sn if m else '',
            m.hb3_sn if m else ''
        ])

    csv_data = output.getvalue()
    output.close()

    filename = f"lab_rma_mensual_{period_start.strftime('%Y_%m')}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


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
    
    
    print(f"DEBUG: iniciar_reparacion called. Miner ID: {miner_id}")
    
    if not miner_id:
        miner_id = request.args.get('id')
    
    print(f"DEBUG: Processing Miner ID: {miner_id}")
    
    # Check miner status before attempting
    minero = Miner.query.get(miner_id)
    if minero:
        print(f"DEBUG: Miner Found: {minero.sn_fisica}, State: {minero.proceso_estado}")
    else:
        print("DEBUG: Miner NOT found")

    success = repair_service.start_repair(miner_id)
    print(f"DEBUG: start_repair result: {success}")
    
    if success:
        minero = Miner.query.get(miner_id)
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="INICIO REPARACIÓN",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos="Equipo en mesa de trabajo."
        ))
        db.session.commit()
        if request.headers.get('HX-Request'):
            return '', 200
        flash('Equipo recibido y pasado a Mesa de Trabajo', 'success')
        return redirect(request.referrer or url_for('main.lab_solicitudes'))
    
    if request.headers.get('HX-Request'):
        return jsonify({'status': 'error'}), 404
    flash('No se pudo iniciar la reparación', 'danger')
    return redirect(request.referrer or url_for('main.lab_solicitudes'))


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
        if request.headers.get('HX-Request'):
            return '', 200
        flash('Equipo movido a Stock Lab', 'success')
        return redirect(request.referrer or url_for('lab.reparacion'))
    
    if request.headers.get('HX-Request'):
        return jsonify({'status': 'error'}), 404
    flash('No se pudo finalizar la reparación', 'danger')
    return redirect(request.referrer or url_for('lab.reparacion'))


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
        if request.headers.get('HX-Request'):
            return jsonify({'status': 'ok'})
        flash('Equipo dado de baja', 'warning')
        return redirect(request.referrer or url_for('lab.reparacion'))
    
    if request.headers.get('HX-Request'):
        return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404
    flash('No se pudo dar de baja el equipo', 'danger')
    return redirect(request.referrer or url_for('lab.reparacion'))


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
        if request.headers.get('HX-Request'):
            return jsonify({'status': 'ok', 'message': 'Equipo reinstalado exitosamente'})
        flash('Equipo reinstalado correctamente', 'success')
        return redirect(request.referrer or url_for('lab.stock'))
    
    error_msg = result.get('error', 'Error al reinstalar')
    if request.headers.get('HX-Request'):
        return jsonify({'status': 'error', 'message': error_msg}), 400
    flash(error_msg, 'danger')
    return redirect(request.referrer or url_for('lab.stock'))


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
        if request.headers.get('HX-Request'):
            return jsonify({'status': 'ok', 'message': f'Equipo reinstalado en posición original'})
        flash('Equipo reinstalado en su posición original', 'success')
        return redirect(request.referrer or url_for('lab.stock', sector='Hydro'))
    
    error_msg = result.get('error', 'Error al reinstalar')
    if request.headers.get('HX-Request'):
        return jsonify({'status': 'error', 'message': error_msg}), 400
    flash(error_msg, 'danger')
    return redirect(request.referrer or url_for('lab.stock', sector='Hydro'))
