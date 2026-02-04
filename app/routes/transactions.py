"""
Transaction Routes
APIs transaccionales: guardar, mover, RMA, conciliación
"""
from flask import Blueprint, request, session, redirect, url_for, jsonify, flash
from app.utils.auth_decorators import login_required
from app.services.sheets_service import GoogleSheetsService
from app.models.miner import Miner
from app.models.user import Movimiento
from app import db
from datetime import datetime
import threading

transactions_bp = Blueprint('transactions', __name__, url_prefix='/api')


# ==========================================
# FUNCIONES EN SEGUNDO PLANO (THREADING)
# ==========================================
HYDRO_WH_ID = 100  # ID de warehouse para Hydro

def tarea_background_rma(datos):
    """Exporta RMA a Google Sheets, detectando si es Hydro o WH"""
    try:
        sheets = GoogleSheetsService()
        # Detectar si es Hydro (wh == 100)
        wh = datos.get('wh')
        print(f"🔍 [Debug RMA] wh original: '{wh}' (type: {type(wh).__name__})")
        try:
            wh = int(wh)
        except:
            wh = 0
        print(f"🔍 [Debug RMA] wh convertido: {wh}, HYDRO_WH_ID: {HYDRO_WH_ID}, es_hydro: {wh == HYDRO_WH_ID}")
        
        if wh == HYDRO_WH_ID:
            sheets.exportar_rma_hydro(datos)
            print(f"✅ [Background] RMA Hydro exportado: {datos.get('sn_fisico', 'N/A')}")
        else:
            sheets.exportar_rma_aire(datos)
            print(f"✅ [Background] RMA WH exportado: {datos.get('sn_fisico', 'N/A')}")
    except Exception as e:
        print(f"❌ [Background] Error RMA: {e}")

def tarea_background_movimiento(datos):
    """Exporta movimiento a Google Sheets, detectando si es Hydro o WH"""
    try:
        sheets = GoogleSheetsService()
        es_hydro = datos.get('es_hydro', False)
        
        if es_hydro:
            sheets.exportar_movimiento_hydro(datos)
            print(f"✅ [Background] Movimiento Hydro exportado: {datos.get('sn_fisico', 'N/A')}")
        else:
            sheets.exportar_movimiento_wh(datos)
            print(f"✅ [Background] Movimiento WH exportado: {datos.get('sn_fisico', 'N/A')}")
    except Exception as e:
        print(f"❌ [Background] Error Movimiento: {e}")

def tarea_background_cambio_piezas(datos):
    try:
        GoogleSheetsService().exportar_cambio_piezas(datos)
        print(f"✅ [Background] Piezas exportadas: {datos['sn_maquina']}")
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
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion=accion, 
            referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
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
        flash('Datos de ubicación incompletos', 'danger')
        return redirect(url_for('dashboard.index'))
    
    problem_type = request.form.get('diagnostico_detalle', '')
    log_text = request.form.get('log_detalle', '')
    
    if not problem_type or problem_type.strip() == '':
        flash('Debe especificar el tipo de problema antes de enviar al laboratorio', 'warning')
        return redirect(url_for('dashboard.warehouse', wh=wh, rack=rack))
    
    ip_rma = request.form.get('ip_rma', '').strip()
    
    if not ip_rma:
        flash('Debe ingresar la IP del puerto actual', 'warning')
        return redirect(url_for('dashboard.warehouse', wh=wh, rack=rack))
    
    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if not minero:
        flash('Minero no encontrado en la posición especificada', 'danger')
        return redirect(url_for('dashboard.warehouse', wh=wh, rack=rack))
    
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
    
    db.session.commit()

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
        # Datos adicionales para Hydro
        'fila': f,
        'columna': c
    }
    
    # Calcular container desde rack_id para Hydro
    try:
        wh_int = int(wh)
        rack_int = int(rack)
        if wh_int == HYDRO_WH_ID:
            container_num = (rack_int + 1) // 2  # Calcular número de contenedor
            datos_para_sheets['container'] = container_num
    except:
        pass
    
    hilo = threading.Thread(target=tarea_background_rma, args=(datos_para_sheets,))
    hilo.start()
    
    db.session.add(Movimiento(
        usuario_id=session['user_id'], 
        accion="REGISTRO RMA", 
        referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
        datos_nuevos=f"SN: {minero.sn_fisica} -> Falla: {problem_type}"
    ))
    db.session.commit()
    
    flash(f'RMA registrado para {minero.sn_fisica}. Para mover el equipo, cree una Solicitud de Traslado.', 'success')
    return redirect(url_for('dashboard.warehouse', wh=wh, rack=rack))


@transactions_bp.route('/mover', methods=['POST'])
@login_required
def mover():
    data = request.json
    wh, rack, f, c = data['wh'], data['rack'], data['f'], data['c']
    motivo = data.get('motivo', 'Sin motivo especificado')

    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if minero:
        if 'sn_digital' in data: minero.sn_digital = data['sn_digital']
        if 'mac' in data: minero.mac_address = data['mac']
        db.session.commit()

        sn_temp = minero.sn_fisica
        
        # Detectar si es Hydro
        try:
            wh_int = int(wh)
            rack_int = int(rack)
            es_hydro = wh_int == HYDRO_WH_ID
            if es_hydro:
                container_num = (rack_int + 1) // 2
                origen = f"C{container_num}"
            else:
                origen = f"WH{wh} - R{rack}"
        except:
            es_hydro = False
            origen = f"WH{wh} - R{rack}"
        
        datos_movimiento = {
            'fecha': datetime.now().strftime("%d/%m/%Y"),
            'sn_fisico': minero.sn_fisica,
            'origen': origen,
            'destino': "LAB",
            'responsable': session.get('username', 'Usuario'),
            'motivo': motivo,
            'ip': minero.ip_address,
            'mac': minero.mac_address,
            'es_hydro': es_hydro,
            # Legacy fields (para compatibilidad)
            'observacion': f"Retirado del Rack {rack} - Pos {f}-{c}",
            'estado': minero.proceso_estado or 'OPERATIVO'
        }
        hilo = threading.Thread(target=tarea_background_movimiento, args=(datos_movimiento,))
        hilo.start()

        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="TRASLADO (SALIDA)", 
            referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
            datos_nuevos=f"SN: {sn_temp} retirado a LAB. Motivo: {motivo}"
        ))

        minero.warehouse_id = None
        minero.rack_id = None
        minero.fila = None
        minero.columna = None
        minero.proceso_estado = 'en_laboratorio'
        
        db.session.commit()
        return jsonify({'status': 'ok'})
    
    return jsonify({'status': 'error', 'message': 'No encontrado'}), 404


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
            referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
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
            referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
            datos_nuevos=f"Solicitud OK. Falla: {minero.diagnostico_detalle}"
        ))
        db.session.commit()
        
        return jsonify({'status': 'ok'})

    return jsonify({'status': 'error'}), 404
