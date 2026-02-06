from flask import Blueprint, request, jsonify, render_template, session
from app.models.diagnostico import Diagnostico
from app.models.miner import Miner
from app.models.user import User
from app.utils.auth_decorators import login_required, admin_required
from app.services.sheets_service import GoogleSheetsService
from app import db
from datetime import datetime

diagnostico_bp = Blueprint('diagnostico', __name__)

@diagnostico_bp.route('/api/diagnostico/guardar', methods=['POST'])
@login_required
def guardar_diagnostico():
    data = request.json
    wh = data.get('wh')
    rack = data.get('rack')
    fila = data.get('fila')
    columna = data.get('columna')
    
    miner_id = data.get('miner_id')
    ip = data.get('ip')
    sn_digital = data.get('sn_digital')
    falla = data.get('falla')
    observacion = data.get('observacion')
    solucion = data.get('solucion')
    
    if not all([wh, rack, fila, columna, miner_id, falla, solucion]):
        return jsonify({'status': 'error', 'message': 'Faltan datos obligatorios'}), 400
        
    try:
        current_time = datetime.now()
        
        # 1. Guardar Diagnóstico
        nuevo_diag = Diagnostico(
            usuario_id=session['user_id'],
            miner_id=miner_id,
            warehouse_id=wh,
            rack_id=rack,
            fila=fila,
            columna=columna,
            ip_address=ip,
            sn_fisica=data.get('sn_fisica', 'N/A'),
            sn_digital=sn_digital,
            falla=falla,
            observacion=observacion,
            solucion=solucion,
            fecha=current_time
        )
        db.session.add(nuevo_diag)
        
        # 2. Actualizar Minero
        minero = Miner.query.get(miner_id)
        if minero:
            # Actualizar datos básicos
            if ip and minero.ip_address != ip:
                minero.ip_address = ip
            if sn_digital and minero.sn_digital != sn_digital:
                minero.sn_digital = sn_digital
            
            # Lógica de Estado Diagnosticado
            marcar_solucionado = data.get('marcar_solucionado', False)
            
            if marcar_solucionado:
                # Si se solucionó, limpiamos cualquier rastro de problema anterior
                minero.diagnostico_detalle = None
                # Aseguramos que quede como operativo si estaba en otro estado (excepto si estaba en proceso critico)
                if minero.proceso_estado == 'operativo':
                    pass # Ya está bien
                elif minero.proceso_estado not in ['baja_definitiva', 'donante_piezas']:
                    minero.proceso_estado = 'operativo'
            else:
                # Si no se solucionó (es solo diagnóstico o va para RMA), marcamos la etiqueta
                # Esto hará que aparezca el badge "DIAGNOSTICADO"
                minero.diagnostico_detalle = f"DIAGNOSTICADO: {falla}"
                
        db.session.commit()
        
        # 3. Exportar a Sheets
        try:
            sheets = GoogleSheetsService()
            datos_export = {
                'fecha': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'wh': wh,
                'rack': rack, 'fila': fila, 'columna': columna,
                'sn_fisica': data.get('sn_fisica', 'N/A'),
                'sn_digital': sn_digital,
                'ip': ip,
                'falla': falla,
                'solucion': solucion,
                'observacion': observacion,
                'tecnico': session.get('username', 'Desconocido')
            }
            sheets.exportar_diagnostico(datos_export)
        except Exception as e:
            print(f"⚠️ Error no bloqueante al exportar a Sheets: {e}")

        return jsonify({'status': 'ok', 'message': 'Diagnóstico guardado correctamente'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@diagnostico_bp.route('/diagnosticos/historial')
@login_required
@admin_required
def historial_diagnosticos():
    # Filtros
    wh_filter = request.args.get('wh')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    query = Diagnostico.query
    
    if wh_filter and wh_filter.isdigit():
        query = query.filter_by(warehouse_id=int(wh_filter))
    elif wh_filter == 'Hydro':
        query = query.filter_by(warehouse_id=100) # ID 100 es Hydro
        
    pagination = query.order_by(Diagnostico.fecha.desc()).paginate(page=page, per_page=per_page)
    
    return render_template('historial_diagnosticos.html', 
                          pagination=pagination, 
                          current_wh=wh_filter)
