from flask import Blueprint, request, jsonify, session
from app.models.solicitud_pieza import SolicitudPieza
from app.models.solicitud import SolicitudTraslado
from app.models.user import Movimiento
from app.models.miner import Miner
from app.utils.auth_decorators import login_required
from app import db
import datetime

conciliacion_bp = Blueprint('conciliacion', __name__, url_prefix='/api/conciliacion')

@conciliacion_bp.route('/crear', methods=['POST'])
@login_required
def crear_conciliacion():
    """
    Endpoint para conciliación de piezas por TÉCNICOS/SUPERVISORES DE WH.
    
    IMPORTANTE:
    - Los técnicos/supervisores de WH son los que CONCILIAN (no el lab)
    - El Lab solo REPARA equipos completos (flujo RMA)
    
    DOS OPCIONES DE CONCILIACIÓN:
    
    1. WH (In-Situ):
       - Equipo se queda en warehouse
       - Lab aprueba solicitud de pieza
       - Depósito envía pieza al WH
       - Técnico WH concilia en el rack
       
    2. LAB (Prueba en Laboratorio):
       - Técnico WH lleva FÍSICAMENTE el equipo al lab
       - Requiere SOLICITUD DE TRASLADO (sale del WH)
       - Técnico WH prueba/concilia en instalaciones del lab
       - Si funciona → Vuelve al WH
       - Si NO funciona → Se queda para reparación completa del Lab
    """
    try:
        data = request.json
        tipo = data.get('tipo', '').upper()  # WH o LAB
        miner_id = data.get('miner_id')
        pieza = data.get('pieza', 'GENERAL')
        comentario = data.get('comentario', '')
        
        if not miner_id or tipo not in ['WH', 'LAB']:
            return jsonify({'status': 'error', 'message': 'Datos inválidos (falta ID o tipo)'}), 400
            
        miner = Miner.query.get(miner_id)
        if not miner:
             return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404

        # Verificar que el minero está en un warehouse
        if not miner.warehouse_id:
            return jsonify({
                'status': 'error', 
                'message': 'El minero no está en un warehouse. La conciliación es solo para equipos en WH.'
            }), 400

        if tipo == 'WH':
            # ===================================================
            # CONCILIACIÓN IN-SITU (WAREHOUSE)
            # Solo para WH normal, NO para Hydro
            # ===================================================
            
            # Detectar si es Hydro - NO PERMITIDO
            HYDRO_WH_ID = 100
            modelo_lower = (miner.modelo or '').lower()
            es_hydro = any(x in modelo_lower for x in ['hyd', 'm33', 'm53']) or miner.warehouse_id == HYDRO_WH_ID
            
            if es_hydro:
                # Hydro NO permite in-situ, pero el frontend ya debería manejar esto.
                # Si llega aquí es un error de UI o intento manual
                return jsonify({
                    'status': 'error',
                    'message': 'Hydro no permite conciliación in-situ. Use la opción de Traslado a LAB.'
                }), 400
            
            # Continúa solo si es WH normal
            
            # 1. El equipo SE QUEDA EN SU POSICIÓN
            
            # 2. Crear solicitud de pieza para que Lab apruebe
            solicitud = SolicitudPieza(
                miner_id=miner_id,
                tipo_pieza=pieza,
                ubicacion_reparacion='WH',
                estado='pendiente_aprobacion_lab',
                comentario=comentario,
                solicitante_id=session['user_id']
            )
            db.session.add(solicitud)
            
            # 3. Log movimiento
            ubicacion = f"WH{miner.warehouse_id}-R{miner.rack_id}-{miner.fila}:{miner.columna}"
            
            # ACTUALIZACION DE ESTADO: Pasa a 'Conciliando'
            miner.proceso_estado = 'Conciliando'
            # Mantenemos diagnostico_detalle si existe, para saber por qué falló antes, 
            # o podríamos actualizarlo para decir "En Conciliación".
            # miner.diagnostico_detalle = "En Proceso de Conciliación" 
                
            db.session.add(Movimiento(
                usuario_id=session['user_id'],
                accion="SOLICITUD CONCILIACIÓN WH",
                referencia_miner=f"{miner.sn_fisica} ({ubicacion})",
                datos_nuevos=f"Pieza: {pieza}. Estado cambiado a Conciliando. {comentario}"
            ))
            
            db.session.commit()
            return jsonify({'status': 'ok', 'message': 'Solicitud de pieza creada. Minero en estado Conciliando.'})

        elif tipo == 'LAB':
            # ===================================================
            # CONCILIACIÓN EN LABORATORIO (PRUEBA)
            # Para WH (opcional) y Hydro (obligatorio)
            # ===================================================
            
            # 1. Crear solicitud de traslado
            traslado = SolicitudTraslado(
                miner_id=miner_id,
                origen_wh=miner.warehouse_id,
                origen_rack=miner.rack_id,
                origen_fila=miner.fila,
                origen_columna=miner.columna,
                destino='LAB',
                sector='Hydro' if miner.warehouse_id == 100 else 'WH',
                motivo=f"CONCILIACIÓN LAB: Prueba de pieza {pieza}. {comentario}",
                solicitante_id=session['user_id'],
                estado='pendiente_lab' # Lab aprueba tanto la pieza como el traslado
            )
            db.session.add(traslado)
            db.session.flush() # Para obtener ID
            
            # 2. Crear solicitud de pieza vinculada
            solicitud_pieza = SolicitudPieza(
                miner_id=miner_id,
                tipo_pieza=pieza,
                ubicacion_reparacion='LAB',
                tipo_conciliacion='LAB',
                solicitud_traslado_id=traslado.id,
                wh_origen=miner.warehouse_id,
                estado='pendiente_aprobacion_lab',
                comentario=comentario,
                solicitante_id=session['user_id']
            )
            db.session.add(solicitud_pieza)
            
            # 3. Log
            db.session.add(Movimiento(
                usuario_id=session['user_id'],
                accion="SOLICITUD CONCILIACIÓN LAB",
                referencia_miner=f"{miner.sn_fisica}",
                datos_nuevos=f"Pieza: {pieza}. Requiere traslado a LAB para prueba."
            ))
            
            db.session.commit()
            return jsonify({'status': 'ok', 'message': 'Solicitud de conciliación en Lab creada. Pendiente aprobación.'})
            

            
    except Exception as e:
        db.session.rollback()
        print(f"Error en conciliacion: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

