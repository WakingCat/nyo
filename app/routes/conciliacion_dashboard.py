from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app.models.solicitud_pieza import SolicitudPieza
from app.models.solicitud import SolicitudTraslado
from app.models.user import User, Movimiento
from app.models.miner import Miner
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
        
        # Actualizar solicitud
        solicitud.estado = 'finalizado'
        
        # RESTAURAR ESTADO DEL MINERO
        miner = solicitud.miner
        if miner:
            miner.proceso_estado = 'operativo'
            miner.diagnostico_detalle = None
            miner.diagnostico_fecha = None
            
            # Si es conciliación LAB, el minero debe volver al WH de origen
            if solicitud.tipo_conciliacion == 'LAB':
                # Obtener datos del traslado original para saber a dónde volver
                traslado = SolicitudTraslado.query.get(solicitud.solicitud_traslado_id) if solicitud.solicitud_traslado_id else None
                
                if traslado and traslado.origen_wh:
                    # Restaurar al WH de origen como pendiente de colocación
                    miner.warehouse_id = traslado.origen_wh
                    miner.rack_id = None  # Se colocará manualmente
                    miner.fila = None
                    miner.columna = None
                    miner.proceso_estado = 'pendiente_colocacion'
                    
                    db.session.add(Movimiento(
                        usuario_id=session['user_id'],
                        accion="RETORNO A WH (CONCILIACIÓN EXITOSA)",
                        referencia_miner=f"{miner.sn_fisica}",
                        datos_nuevos=f"Retorna a WH{traslado.origen_wh} como pendiente de colocación."
                    ))
                elif solicitud.wh_origen:
                    # Fallback: usar wh_origen de la solicitud de pieza
                    miner.warehouse_id = solicitud.wh_origen
                    miner.rack_id = None
                    miner.fila = None
                    miner.columna = None
                    miner.proceso_estado = 'pendiente_colocacion'
                    
                    db.session.add(Movimiento(
                        usuario_id=session['user_id'],
                        accion="RETORNO A WH (CONCILIACIÓN EXITOSA)",
                        referencia_miner=f"{miner.sn_fisica}",
                        datos_nuevos=f"Retorna a WH{solicitud.wh_origen} como pendiente de colocación."
                    ))
            
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="CONCILIACIÓN EXITOSA",
            referencia_miner=f"{solicitud.miner.sn_fisica}",
            datos_nuevos=f"Pieza {solicitud.tipo_pieza} funcionó. {comentario}"
        ))
        
        db.session.commit()
        
        if solicitud.tipo_conciliacion == 'LAB':
            flash('Conciliación finalizada con éxito. El equipo está pendiente de colocación en el WH.', 'success')
        else:
            flash('Conciliación finalizada con éxito. El equipo ha vuelto a estado OPERATIVO.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        
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
        
        # 1. Marcar solicitud de pieza como cedida (no finalizada normal)
        solicitud.estado = 'cedido_lab'
        
        # 2. Si es In-Situ (WH), crear traslado a Lab ahora
        if solicitud.tipo_conciliacion == 'WH':
            traslado = SolicitudTraslado(
                miner_id=miner.id,
                origen_wh=miner.warehouse_id,
                origen_rack=miner.rack_id,
                origen_fila=miner.fila,
                origen_columna=miner.columna,
                destino='LAB',
                sector='WH', # In-Situ solo aplica a WH
                motivo=f"FALLO CONCILIACIÓN IN-SITU: {comentario}. Se deriva a Lab.",
                solicitante_id=session['user_id'],
                estado='pendiente_lab'
            )
            db.session.add(traslado)
            
            db.session.add(Movimiento(
                usuario_id=session['user_id'],
                accion="CEDIDO AL LAB",
                referencia_miner=f"{miner.sn_fisica}",
                datos_nuevos=f"Fallo prueba pieza {solicitud.tipo_pieza}. Se genera traslado a Lab."
            ))
            
        elif solicitud.tipo_conciliacion == 'LAB':
            # Ya está en Lab o en proceso de ir.
            # Solo actualizamos el log, el minero ya debería tener solicitud de traslado vinculada.
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
        
    return redirect(url_for('conciliacion_dash.dashboard'))
