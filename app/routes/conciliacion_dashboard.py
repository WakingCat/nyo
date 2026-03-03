from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app.models.solicitud_pieza import SolicitudPieza
from app.models.solicitud import SolicitudTraslado
from app.models.user import User, Movimiento
from app.models.miner import Miner
from app.models.pieza_deposito import PiezaDeposito, MovimientoPiezaDeposito
from app.utils.auth_decorators import login_required
from app import db
from datetime import datetime

conciliacion_dash_bp = Blueprint('conciliacion_dash', __name__, url_prefix='/conciliacion')

@conciliacion_dash_bp.route('/')
@login_required
def dashboard():
    """
    Dashboard de Conciliación para Técnicos y Supervisores.
    Muestra piezas solicitadas, estado de traslados a Lab y permite acciones finales.
    """
    user_id = session['user_id']
    
    # 1. Mis Conciliaciones (Solicitadas por mí)
    mis_solicitudes = SolicitudPieza.query.filter_by(
        solicitante_id=user_id
    ).filter(
        SolicitudPieza.estado.notin_(['finalizado', 'cedido_lab', 'rechazado'])
    ).order_by(SolicitudPieza.fecha_solicitud.desc()).all()
    
    # 2. Pendientes de Acción (Si soy Supervisor, veo las de mi equipo también? Por ahora solo propias)
    # TODO: Agregar lógica para supervisores si se requiere ver actividad del equipo
    
    return render_template('conciliaciones/dashboard.html', 
                         solicitudes=mis_solicitudes)

@conciliacion_dash_bp.route('/tabla-partial')
@login_required
def tabla_partial():
    """
    Partial HTMX para actualización automática de la tabla de conciliaciones.
    """
    user_id = session['user_id']
    
    solicitudes = SolicitudPieza.query.filter_by(
        solicitante_id=user_id
    ).filter(
        SolicitudPieza.estado.notin_(['finalizado', 'cedido_lab', 'rechazado'])
    ).order_by(SolicitudPieza.fecha_solicitud.desc()).all()
    
    return render_template('partials/conciliaciones_table_body.html', 
                         solicitudes=solicitudes)

@conciliacion_dash_bp.route('/confirmar-recepcion/<id>', methods=['POST'])
@login_required
def confirmar_recepcion(id):
    """
    Técnico confirma que recibió la pieza del depósito.
    """
    try:
        solicitud = SolicitudPieza.query.get(id)
        if not solicitud or solicitud.solicitante_id != session['user_id']:
            flash('Solicitud no encontrada o sin permiso', 'danger')
            return redirect(url_for('conciliacion_dash.dashboard'))
            
        if solicitud.estado != 'en_camino':
            flash('Solo se puede confirmar recepción de piezas en camino', 'warning')
            return redirect(url_for('conciliacion_dash.dashboard'))
            
        solicitud.estado = 'recibido'
        solicitud.fecha_recepcion = datetime.now()
        
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="CONFIRMACIÓN RECEPCIÓN PIEZA",
            referencia_miner=f"{solicitud.miner.sn_fisica}",
            datos_nuevos=f"Pieza {solicitud.tipo_pieza} recibida. Lista para prueba."
        ))
        
        db.session.commit()
        flash('Recepción confirmada. Procede a realizar la prueba.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    # Si es petición HTMX, redirigir con HX-Redirect
    if request.headers.get('HX-Request'):
        response = redirect(url_for('conciliacion_dash.dashboard'))
        response.headers['HX-Redirect'] = url_for('conciliacion_dash.dashboard')
        return response
        
    return redirect(url_for('conciliacion_dash.dashboard'))

@conciliacion_dash_bp.route('/finalizar-exito/<id>', methods=['POST'])
@login_required
def finalizar_exito(id):
    """
    Prueba EXITOSA. El minero queda operativo con la pieza nueva.
    Si es conciliación LAB, el minero vuelve al WH de origen.
    """
    try:
        solicitud = SolicitudPieza.query.get(id)
        if not solicitud:
            flash('Error', 'danger')
            return redirect(url_for('conciliacion_dash.dashboard'))
            
        comentario = request.form.get('comentario', 'Prueba exitosa')
        tipo_conciliacion = (solicitud.tipo_conciliacion or 'WH').upper()
        es_hydro_auto = False
        retorno_automatico = False
        
        # Actualizar solicitud
        solicitud.estado = 'finalizado'
        
        # RESTAURAR ESTADO DEL MINERO
        miner = solicitud.miner
        if miner:
            # =========================================================
            # ACTUALIZACIÓN AUTOMÁTICA DE SN (FEATURE REQUEST)
            # Cuando el técnico confirma éxito, el SN de la pieza nueva
            # debe quedar registrado en el minero.
            # =========================================================
            tipo_pieza = (solicitud.tipo_pieza or '').upper()
            nuevo_sn = (solicitud.producto_sn or '').strip()
            nuevo_modelo = (solicitud.producto_modelo or '').strip()
            
            log_cambios = []
            
            if nuevo_sn:
                # 1. PSU / FUENTE
                if 'PSU' in tipo_pieza or 'FUENTE' in tipo_pieza:
                    old_sn = miner.psu_sn
                    miner.psu_sn = nuevo_sn
                    if nuevo_modelo: miner.psu_model = nuevo_modelo
                    log_cambios.append(f"Cambio PSU: {old_sn} -> {nuevo_sn}")
                    
                # 2. CONTROL BOARD
                elif 'CONTROL' in tipo_pieza or 'CB' in tipo_pieza or 'BOARD' in tipo_pieza:
                    old_sn = miner.cb_sn
                    miner.cb_sn = nuevo_sn
                    log_cambios.append(f"Cambio CB: {old_sn} -> {nuevo_sn}")
                    
                # 3. HASHBOARDS (Intentar detectar cuál es)
                elif 'HASHBOARD' in tipo_pieza or 'HB' in tipo_pieza:
                    # Si el tipo especifica cuál (ej: HB1, HB2)
                    idx = None
                    if '1' in tipo_pieza or 'CH0' in tipo_pieza: idx = 1
                    elif '2' in tipo_pieza or 'CH1' in tipo_pieza: idx = 2
                    elif '3' in tipo_pieza or 'CH2' in tipo_pieza: idx = 3
                    
                    if idx:
                        campo = f"hb{idx}_sn"
                        old_sn = getattr(miner, campo, '')
                        setattr(miner, campo, nuevo_sn)
                        log_cambios.append(f"Cambio HB{idx}: {old_sn} -> {nuevo_sn}")
                    else:
                        # Si es genérico, solo loguear pero no reemplazar a ciegas
                        log_cambios.append(f"Pieza Hashboard {nuevo_sn} instalada (posición no especificada)")
                
                # 4. OTROS Componentes (FAN, etc) - Solo loguear
                else:
                    log_cambios.append(f"Pieza {tipo_pieza}: {nuevo_sn} instalada")

            # Restaurar estado operativo
            miner.proceso_estado = 'operativo'
            miner.diagnostico_detalle = None
            miner.diagnostico_fecha = None
            
            # Si es conciliación LAB, el minero debe volver al WH de origen
            if tipo_conciliacion == 'LAB':
                # Obtener datos del traslado original para saber a dónde volver
                traslado = solicitud.traslado or (SolicitudTraslado.query.get(solicitud.solicitud_traslado_id) if solicitud.solicitud_traslado_id else None)
                wh_destino = None
                if traslado and traslado.origen_wh:
                    wh_destino = traslado.origen_wh
                elif solicitud.wh_origen:
                    wh_destino = solicitud.wh_origen

                es_hydro = False
                if traslado:
                    es_hydro = traslado.sector == 'Hydro' or (traslado.origen_wh == 100)
                elif wh_destino == 100:
                    es_hydro = True

                if traslado and traslado.origen_wh:
                    # Retorno automático al punto de origen (WH/Hydro)
                    miner.warehouse_id = traslado.origen_wh
                    miner.rack_id = traslado.origen_rack
                    miner.fila = traslado.origen_fila
                    miner.columna = traslado.origen_columna
                    miner.proceso_estado = 'operativo'
                    es_hydro_auto = traslado.sector == 'Hydro' or (traslado.origen_wh == 100)
                    retorno_automatico = True

                    db.session.add(Movimiento(
                        usuario_id=session['user_id'],
                        accion="RETORNO AUTOMÁTICO ORIGEN",
                        referencia_miner=f"{miner.sn_fisica}",
                        datos_nuevos=f"Retorna automáticamente a WH{miner.warehouse_id}-R{miner.rack_id} ({miner.fila}-{miner.columna})."
                    ))
                elif wh_destino:
                    # Fallback si no hay rack/fila/columna de origen
                    miner.warehouse_id = wh_destino
                    miner.rack_id = None
                    miner.fila = None
                    miner.columna = None
                    miner.proceso_estado = 'pendiente_colocacion'

                    db.session.add(Movimiento(
                        usuario_id=session['user_id'],
                        accion="RETORNO A WH (PENDIENTE COLOCACIÓN)",
                        referencia_miner=f"{miner.sn_fisica}",
                        datos_nuevos=f"Sin ubicación exacta de origen. Retorna a WH{wh_destino} pendiente de colocación."
                    ))
            
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="CONCILIACIÓN EXITOSA",
            referencia_miner=f"{solicitud.miner.sn_fisica}",
            datos_nuevos=f"Pieza {solicitud.tipo_pieza} funcionó. {comentario}. {' | '.join(log_cambios) if log_cambios else ''}"
        ))
        
        db.session.commit()
        
        if tipo_conciliacion == 'LAB':
            if retorno_automatico and es_hydro_auto:
                flash('Conciliación finalizada con éxito. El Hydro volvió automáticamente a su contenedor.', 'success')
            elif retorno_automatico:
                flash('Conciliación finalizada con éxito. El equipo volvió automáticamente a su ubicación de origen.', 'success')
            else:
                flash('Conciliación finalizada con éxito. El equipo está pendiente de colocación en el WH.', 'success')
        else:
            flash('Conciliación finalizada con éxito. El equipo ha vuelto a estado OPERATIVO.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    # Si es petición HTMX, redirigir con HX-Redirect
    if request.headers.get('HX-Request'):
        response = redirect(url_for('conciliacion_dash.dashboard'))
        response.headers['HX-Redirect'] = url_for('conciliacion_dash.dashboard')
        return response
        
    return redirect(url_for('conciliacion_dash.dashboard'))


@conciliacion_dash_bp.route('/reintentar-pieza/<id>', methods=['POST'])
@login_required
def reintentar_pieza(id):
    """
    Prueba FALLIDA pero SIN ceder a reparación completa:
    crea una nueva solicitud de pieza para volver a intentar conciliación.
    """
    try:
        solicitud = SolicitudPieza.query.get(id)
        if not solicitud:
            flash('Solicitud no encontrada', 'danger')
            return redirect(url_for('conciliacion_dash.dashboard'))

        comentario = (request.form.get('comentario') or '').strip()
        comentario_base = solicitud.comentario or ''
        comentario_final = f"Reintento solicitado. {comentario}".strip()
        if comentario_base:
            comentario_final = f"{comentario_base} | {comentario_final}"

        # Cerrar solicitud actual como completada (sin éxito)
        solicitud.estado = 'finalizado'

        # Crear nueva solicitud con mismos datos base
        nueva = SolicitudPieza(
            miner_id=solicitud.miner_id,
            tipo_pieza=solicitud.tipo_pieza,
            ubicacion_reparacion=solicitud.ubicacion_reparacion,
            tipo_conciliacion=solicitud.tipo_conciliacion,
            solicitud_traslado_id=solicitud.solicitud_traslado_id,
            wh_origen=solicitud.wh_origen,
            estado='pendiente_aprobacion_lab',
            comentario=comentario_final,
            solicitante_id=session['user_id']
        )
        db.session.add(nueva)

        miner = solicitud.miner
        if miner:
            if (solicitud.tipo_conciliacion or 'WH').upper() == 'LAB':
                miner.proceso_estado = 'en_laboratorio'
            else:
                miner.proceso_estado = 'Conciliando'

        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="REINTENTO CONCILIACIÓN",
            referencia_miner=f"{solicitud.miner.sn_fisica if solicitud.miner else 'N/A'}",
            datos_nuevos=f"Solicitud #{solicitud.id} cerrada sin éxito. Nueva solicitud de pieza #{nueva.id} creada."
        ))

        db.session.commit()
        flash('Se creó una nueva solicitud para probar otra pieza.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    if request.headers.get('HX-Request'):
        response = redirect(url_for('conciliacion_dash.dashboard'))
        response.headers['HX-Redirect'] = url_for('conciliacion_dash.dashboard')
        return response

    return redirect(url_for('conciliacion_dash.dashboard'))

@conciliacion_dash_bp.route('/ceder-lab/<id>', methods=['POST'])
@login_required
def ceder_lab(id):
    """
    Prueba FALLIDA. Se cede el equipo al Laboratorio para reparación completa.
    """
    try:
        solicitud = SolicitudPieza.query.get(id)
        if not solicitud:
            flash('Error', 'danger')
            return redirect(url_for('conciliacion_dash.dashboard'))
            
        comentario = request.form.get('comentario', 'Fallo en prueba de pieza')
        miner = solicitud.miner
        
        # 1) Marcar solicitud como cedida a Lab
        solicitud.estado = 'cedido_lab'
        
        # 2) Flujo WH: generar traslado a Lab y enlazarlo a la solicitud
        if solicitud.tipo_conciliacion == 'WH':
            # Detectar sector real (Hydro vs WH) para que aparezca en el panel correcto
            modelo_lower = (miner.modelo or '').lower()
            es_hydro = miner.warehouse_id == 100 or any(x in modelo_lower for x in ['hyd', 'm33', 'm53'])
            sector = 'Hydro' if es_hydro else 'WH'

            # Evitar duplicar solicitudes: si ya existe traslado pendiente para este minero, reutilizarlo
            estados_pendientes = ['pendiente_lab', 'pendiente_coordinador', 'pendiente_coordinador_hydro', 'pendiente']
            traslado = SolicitudTraslado.query.filter(
                SolicitudTraslado.miner_id == miner.id,
                SolicitudTraslado.estado.in_(estados_pendientes)
            ).order_by(SolicitudTraslado.fecha_solicitud.desc()).first()

            if not traslado:
                traslado = SolicitudTraslado(
                    miner_id=miner.id,
                    origen_wh=miner.warehouse_id,
                    origen_rack=miner.rack_id,
                    origen_fila=miner.fila,
                    origen_columna=miner.columna,
                    destino='LAB',
                    sector=sector,
                    motivo=f"FALLO CONCILIACIÓN IN-SITU: {comentario}. Se deriva a Lab.",
                    solicitante_id=session['user_id'],
                    estado='pendiente_lab'
                )
                db.session.add(traslado)
                db.session.flush()  # Necesario para obtener traslado.id

            # Enlazar y bloquear minero mientras se tramita el traslado
            solicitud.solicitud_traslado_id = traslado.id
            miner.proceso_estado = 'pendiente_traslado'

            db.session.add(Movimiento(
                usuario_id=session['user_id'],
                accion="CEDIDO AL LAB",
                referencia_miner=f"{miner.sn_fisica}",
                datos_nuevos=f"Fallo prueba pieza {solicitud.tipo_pieza}. Traslado #{traslado.id} (sector {sector})."
            ))
            
        elif solicitud.tipo_conciliacion == 'LAB':
            # Ya está en flujo LAB. Aseguramos que quede visible para reparación.
            miner.proceso_estado = 'en_laboratorio'
            db.session.add(Movimiento(
                usuario_id=session['user_id'],
                accion="CEDIDO AL LAB (YA EN LAB)",
                referencia_miner=f"{miner.sn_fisica}",
                datos_nuevos=f"Fallo prueba pieza {solicitud.tipo_pieza}. El equipo se queda en Lab para reparación profunda."
            ))
            
        db.session.commit()
        flash('Equipo cedido al Laboratorio exitosamente.', 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    # Si es petición HTMX, redirigir con HX-Redirect
    if request.headers.get('HX-Request'):
        response = redirect(url_for('conciliacion_dash.dashboard'))
        response.headers['HX-Redirect'] = url_for('conciliacion_dash.dashboard')
        return response
        
    return redirect(url_for('conciliacion_dash.dashboard'))
