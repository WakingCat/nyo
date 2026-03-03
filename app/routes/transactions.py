"""
Transaction Routes
APIs transaccionales: guardar, mover, RMA, conciliación
"""
from flask import Blueprint, request, session, redirect, url_for, jsonify, flash, current_app
from app.utils.auth_decorators import login_required
from app.services.sheets_service import GoogleSheetsService
from app.services.sheets_queue import enqueue_sheet_export
from app.models.miner import Miner
from app.models.user import Movimiento
from app.models.solicitud import SolicitudTraslado
from app.services.transfer_service import transfer_service
from app import db
from datetime import datetime
import threading
from app.utils.helpers import format_ubicacion
from app.services.notification_service import send_notification
from app.models.user import User, Role
from app.services.drive_service import GoogleDriveService

transactions_bp = Blueprint('transactions', __name__, url_prefix='/api')


# ==========================================
# FUNCIONES EN SEGUNDO PLANO (THREADING)
# ==========================================
HYDRO_WH_ID = 100  # ID de warehouse para Hydro

def tarea_background_rma(app_obj, datos):
    """Encola RMA para exportar a Sheets a las 18:00."""
    try:
        with app_obj.app_context():
            # Detectar si es Hydro (wh == 100)
            wh = datos.get('wh')
            print(f"🔍 [Debug RMA] wh original: '{wh}' (type: {type(wh).__name__})")
            try:
                wh = int(wh)
            except:
                wh = 0
            print(f"🔍 [Debug RMA] wh convertido: {wh}, HYDRO_WH_ID: {HYDRO_WH_ID}, es_hydro: {wh == HYDRO_WH_ID}")
            
            if wh == HYDRO_WH_ID:
                enqueue_sheet_export('rma_hydro', datos)
                print(f"✅ [Background] RMA Hydro encolado: {datos.get('sn_fisico', 'N/A')}")
            else:
                enqueue_sheet_export('rma_aire', datos)
                print(f"✅ [Background] RMA WH encolado: {datos.get('sn_fisico', 'N/A')}")
                
            # ENVIAR NOTIFICACIONES
            # 1. Buscar usuarios de Lab y Coordinadores
            with db.session.no_autoflush:
                destinatarios = User.query.join(Role).filter(
                    (Role.departamento == 'Lab') | 
                    (Role.nombre_puesto.in_(['Coordinador', 'Site Manager', 'Manager']))
                ).all()
                
                mensaje = f"Nuevo RMA creado: {datos.get('sn_fisico')} (WH{wh})"
                for dest in destinatarios:
                    send_notification(
                        message=mensaje,
                        recipient_user_id=dest.id,
                        link='rma',
                        type='info'
                    )
                
    except Exception as e:
        print(f"❌ [Background] Error RMA: {e}")

def tarea_background_movimiento(datos):
    """Encola movimiento para exportar a Sheets a las 18:00."""
    try:
        es_hydro = datos.get('es_hydro', False)
        
        if es_hydro:
            enqueue_sheet_export('movimiento_hydro', datos)
            print(f"✅ [Background] Movimiento Hydro encolado: {datos.get('sn_fisico', 'N/A')}")
        else:
            enqueue_sheet_export('movimiento_wh', datos)
            print(f"✅ [Background] Movimiento WH encolado: {datos.get('sn_fisico', 'N/A')}")
    except Exception as e:
        print(f"❌ [Background] Error Movimiento: {e}")

def tarea_background_cambio_piezas(datos):
    try:
        enqueue_sheet_export('cambio_piezas', datos)
        print(f"✅ [Background] Piezas encoladas: {datos['sn_maquina']}")
    except Exception as e:
        print(f"❌ [Background] Error Piezas: {e}")


# ==========================================
# APIs TRANSACCIONALES
# ==========================================

@transactions_bp.route('/guardar', methods=['POST'])
@login_required
def guardar():
    wh = request.form.get('wh')
    rack = request.form.get('rack')
    f = request.form.get('fila')
    c = request.form.get('columna')
    
    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    nuevo = False
    if not minero:
        minero = Miner(warehouse_id=wh, rack_id=rack, fila=f, columna=c)
        nuevo = True
    
    minero.modelo = request.form.get('modelo')
    minero.sn_fisica = request.form.get('sn_fisica')
    minero.sn_digital = request.form.get('sn_digital')
    minero.mac_address = request.form.get('mac')
    minero.psu_model = request.form.get('psu_model')
    minero.psu_sn = request.form.get('psu_sn')
    minero.cb_sn = request.form.get('cb_sn')
    minero.hb1_sn = request.form.get('hb1_sn')
    minero.hb2_sn = request.form.get('hb2_sn')
    minero.hb3_sn = request.form.get('hb3_sn')
    
    try: minero.ths = float(request.form.get('ths'))
    except: minero.ths = 0

    try:
        db.session.add(minero)
        accion = "REGISTRO" if nuevo else "EDICIÓN"
        db.session.add(minero)
        accion = "REGISTRO" if nuevo else "EDICIÓN"
        ubicacion_str = format_ubicacion(wh, rack, f, c)
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion=accion, 
            referencia_miner=ubicacion_str, 
            datos_nuevos=f"SN:{minero.sn_fisica}"
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error al guardar: {e}")

    return redirect(url_for('dashboard.warehouse', wh=wh, rack=rack))


@transactions_bp.route('/rma/enviar_y_exportar', methods=['POST'])
@login_required
def enviar_y_exportar():
    wh = request.form.get('wh')
    rack = request.form.get('rack')
    f = request.form.get('fila')
    c = request.form.get('columna')
    
    if not all([wh, rack, f, c]):
        return jsonify({'status': 'error', 'message': 'Datos de ubicación incompletos'}), 400
    
    problem_type = request.form.get('diagnostico_detalle', '')
    log_text = request.form.get('log_detalle', '')
    
    if not problem_type or problem_type.strip() == '':
        return jsonify({'status': 'error', 'message': 'Debe especificar el tipo de problema'}), 400
    
    ip_rma = request.form.get('ip_rma', '').strip()
    log_file = request.files.get('log_file')
    no_enciende = str(request.form.get('no_enciende', '')).strip().lower() in ['1', 'true', 'on', 'si', 'yes']
    
    if not ip_rma:
        return jsonify({'status': 'error', 'message': 'Debe ingresar IP'}), 400

    if not no_enciende and not log_file:
        return jsonify({'status': 'error', 'message': 'Debe adjuntar archivo .txt del log para RMA'}), 400

    # Validaciones de backend (no depender solo del frontend)
    sn_digital = (request.form.get('sn_digital') or '').strip()
    mac = (request.form.get('mac') or '').strip()
    ths_raw = (request.form.get('ths') or '').strip()

    if not sn_digital or not mac or not ths_raw or (not no_enciende and not log_text.strip()):
        return jsonify({'status': 'error', 'message': 'Debe completar SN Digital, MAC, TH/s y Log para enviar RMA'}), 400

    if no_enciende and not log_text.strip():
        log_text = 'NO ENCIENDE'

    try:
        ths_val = float(ths_raw)
        if ths_val <= 0:
            raise ValueError('TH/s inválido')
    except Exception:
        return jsonify({'status': 'error', 'message': 'TH/s inválido. Debe ser un número mayor a 0'}), 400

    tipo = problem_type.strip().upper()
    if tipo == 'PSU':
        psu_model = (request.form.get('psu_model') or '').strip()
        psu_sn = (request.form.get('psu_sn') or '').strip()
        if not psu_model or not psu_sn:
            return jsonify({'status': 'error', 'message': 'Para falla PSU debe completar Modelo y SN de la fuente'}), 400
    elif tipo == 'CONTROL BOARD':
        cb_sn = (request.form.get('cb_sn') or '').strip()
        if not cb_sn:
            return jsonify({'status': 'error', 'message': 'Para falla CONTROL BOARD debe completar SN de control board'}), 400
    elif tipo == 'HASHBOARD':
        hb1 = (request.form.get('hb1_sn') or '').strip()
        hb2 = (request.form.get('hb2_sn') or '').strip()
        hb3 = (request.form.get('hb3_sn') or '').strip()
        if not any([hb1, hb2, hb3]):
            return jsonify({'status': 'error', 'message': 'Para falla HASHBOARD debe ingresar al menos un SN de placa (HB)'}), 400
    
    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if not minero:
        if request.headers.get('Option') != 'no-redirect':
            # Si no es JSON y es navegador, devolver redirect
            flash('Minero no encontrado', 'danger')
            return redirect(url_for('dashboard.warehouse', wh=wh, rack=rack))
        else:
            return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404

    if not minero.sn_fisica:
        return jsonify({'status': 'error', 'message': 'El equipo no tiene SN físico registrado. Complete los datos antes de enviar RMA'}), 400

    # Subir log .txt a Google Drive con nombre de SN Digital
    upload_result = {'file_name': '', 'link': ''}
    if not no_enciende:
        drive = GoogleDriveService()
        upload_result = drive.upload_rma_log_txt(log_file, sn_digital)
        if not upload_result.get('ok'):
            return jsonify({'status': 'error', 'message': upload_result.get('message', 'No se pudo subir el log a Drive')}), 400
    
    minero.sn_digital = request.form.get('sn_digital')
    minero.mac_address = request.form.get('mac')
    minero.psu_model = request.form.get('psu_model')
    minero.psu_sn = request.form.get('psu_sn')
    minero.cb_sn = request.form.get('cb_sn')
    minero.hb1_sn = request.form.get('hb1_sn')
    minero.hb2_sn = request.form.get('hb2_sn')
    minero.hb3_sn = request.form.get('hb3_sn')
    
    minero.fecha_diagnostico = datetime.now()
    minero.diagnostico_detalle = problem_type
    minero.log_detalle = log_text
    
    # --- NUEVO FLUJO: SOLICITUD DE TRASLADO ---
    # En lugar de moverlo directamente, creamos una solicitud de traslado
    from app.services.transfer_service import transfer_service
    
    # Definir ubicación para el historial
    ubicacion_historial = format_ubicacion(wh, rack, f, c)

    try:
        # 1. Crear solicitud de traslado (Esto pone al minero en 'pendiente_traslado')
        # El destino es 'LAB' por defecto para RMAs
        solicitud = transfer_service.create_request(
            miner_id=minero.id,
            destino='LAB',
            motivo=f"RMA: {problem_type}",
            solicitante_id=session['user_id']
        )
        
        # 2. Guardar ubicación original en el modelo (Backup adicional)
        if int(wh) == 100:
            minero.orig_warehouse_id = int(wh)
            minero.orig_rack_id = int(rack) if rack else None
            minero.orig_fila = int(f) if f else None
            minero.orig_columna = int(c) if c else None
        
        db.session.commit()
        
        # 3. Exportar a Sheets (Registro del RMA)
        # Preparamos datos 
        datos_para_sheets = {
            'fecha': datetime.now().strftime("%d/%m/%Y"),
            'responsable': session.get('username', 'Usuario'),
            'wh': wh, 'rack': rack, 'problem': problem_type,
            'ip': ip_rma,
            'sn_digital': minero.sn_digital,
            'sn_fisico': minero.sn_fisica,
            'mac': minero.mac_address,
            'th': minero.ths,
            'modelo': minero.modelo,
            'garantia_vence': minero.garantia_vence,
            'psu_model': minero.psu_model,
            'psu_sn': minero.psu_sn,
            'hb1': minero.hb1_sn,
            'hb2': minero.hb2_sn,
            'hb3': minero.hb3_sn,
            'cb_sn': minero.cb_sn,
            'log': log_text,
            'log_drive_file': upload_result.get('file_name', ''),
            'log_drive_link': upload_result.get('link', ''),
            'no_enciende': no_enciende,
            'fila': f,
            'columna': c
        }
        
        # Calcular container hydro
        try:
            if int(wh) == HYDRO_WH_ID:
                datos_para_sheets['container'] = (int(rack) + 1) // 2
        except:
            pass

        # Lanza hilo para sheets
        app_obj = current_app._get_current_object()
        hilo = threading.Thread(target=tarea_background_rma, args=(app_obj, datos_para_sheets,))
        hilo.start()
        
        # 4. Historial
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="SOLICITUD RMA", 
            referencia_miner=ubicacion_historial, 
            datos_nuevos=(
                f"SN: {minero.sn_fisica} -> Solicitud traslado a LAB creada. "
                f"Falla: {problem_type}. Log Drive: {upload_result.get('file_name', '')}"
            )
        ))
        db.session.commit()
        
        return jsonify({
            'status': 'ok',
            'message': 'RMA registrado, log cargado en Drive y solicitud de traslado creada.',
            'log_drive_link': upload_result.get('link', '')
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error en enviar_y_exportar: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@transactions_bp.route('/mover', methods=['POST'])
@login_required
def mover():
    data = request.json or {}
    wh, rack, f, c = data.get('wh'), data.get('rack'), data.get('f'), data.get('c')
    motivo = data.get('motivo', 'Sin motivo especificado')

    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    if not minero:
        return jsonify({'status': 'error', 'message': 'No encontrado'}), 404

    # Guardar datos básicos que llegan desde la UI (no mover todavía)
    if 'sn_digital' in data: minero.sn_digital = data['sn_digital']
    if 'mac' in data: minero.mac_address = data['mac']
    db.session.commit()

    # Evitar duplicar solicitudes
    pending_states = ['pendiente_lab', 'pendiente_coordinador', 'pendiente_coordinador_hydro', 'pendiente']
    solicitud_existente = SolicitudTraslado.query.filter(
        SolicitudTraslado.miner_id == minero.id,
        SolicitudTraslado.estado.in_(pending_states)
    ).first()
    if solicitud_existente:
        return jsonify({'status': 'error', 'message': 'Ya existe una solicitud de traslado pendiente para este equipo'}), 400

    try:
        solicitud = transfer_service.create_request(
            miner_id=minero.id,
            destino='LAB',
            motivo=motivo,
            solicitante_id=session['user_id']
        )

        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="SOLICITUD TRASLADO",
            referencia_miner=format_ubicacion(wh, rack, f, c),
            datos_nuevos=f"SN: {minero.sn_fisica} -> Solicitud {solicitud.id} enviada a aprobación. Motivo: {motivo}"
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

    return jsonify({'status': 'ok', 'message': 'Solicitud enviada a aprobación del laboratorio'})


@transactions_bp.route('/rma/cancelar', methods=['POST'])
@login_required
def cancelar_rma():
    data = request.json
    wh, rack, f, c = data['wh'], data['rack'], data['f'], data['c']
    
    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if minero:
        minero.proceso_estado = 'operativo'
        minero.diagnostico_detalle = None
        minero.log_detalle = None
        minero.fecha_diagnostico = None
        
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="RMA CANCELADO", 
            referencia_miner=format_ubicacion(wh, rack, f, c), 
            datos_nuevos=f"SN: {minero.sn_fisica} restaurado a operativo"
        ))
        db.session.commit()
        return jsonify({'status': 'ok'})
    
    return jsonify({'status': 'error'}), 404


@transactions_bp.route('/conciliar', methods=['POST'])
@login_required
def conciliar():
    data = request.json
    wh, rack, f, c = data['wh'], data['rack'], data['f'], data['c']
    cant_coolers = data.get('cant_coolers', '') 

    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()

    if minero:
        if 'sn_digital' in data: minero.sn_digital = data['sn_digital']
        if 'mac' in data: minero.mac_address = data['mac']
        if 'psu_sn' in data: minero.psu_sn = data['psu_sn']
        if 'psu_model' in data: minero.psu_model = data['psu_model']
        if 'cb_sn' in data: minero.cb_sn = data['cb_sn']
        
        db.session.commit() 

        psu_sn_viejo = ""
        cb_sn_viejo = ""
        
        if minero.diagnostico_detalle == 'PSU':
            psu_sn_viejo = minero.psu_sn
        elif minero.diagnostico_detalle == 'CONTROL BOARD':
            cb_sn_viejo = minero.cb_sn

        psu_mod = getattr(minero, 'psu_model', '') or 'Genérico'
        mod_especifico = f"{psu_mod} {minero.ths}T"

        datos_para_sheets = {
            'fecha': datetime.now().strftime("%d/%m/%Y"),
            'problema': minero.diagnostico_detalle or 'N/A',
            'sn_maquina': minero.sn_fisica,
            'mac_digital': minero.mac_address,
            'ubicacion': f"WH{wh} - R{rack}",
            'modelo': minero.modelo,
            'modelo_especifico': mod_especifico,
            'cant_coolers': cant_coolers,
            'psu_sn_viejo': psu_sn_viejo,
            'cb_sn_viejo': cb_sn_viejo,
            'detalles': minero.log_detalle or '',
            'tecnico': session.get('username', 'Usuario'),
            'ip': minero.ip_address,
            'estado': minero.proceso_estado
        }

        hilo = threading.Thread(target=tarea_background_cambio_piezas, args=(datos_para_sheets,))
        hilo.start()

        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="CONCILIACIÓN (PIEZAS)", 
            referencia_miner=format_ubicacion(wh, rack, f, c), 
            datos_nuevos=f"Solicitud OK. Falla: {minero.diagnostico_detalle}"
        ))
        db.session.commit()
        
        return jsonify({'status': 'ok'})

    return jsonify({'status': 'error'}), 404
