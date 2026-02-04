"""
Rutas del Dashboard de Depósito
Gestión de inventario de piezas por Serial Number
"""
from flask import Blueprint, render_template, request, jsonify, session
from app.models.pieza_deposito import PiezaDeposito, MovimientoPiezaDeposito, TIPOS_PIEZA, MODELOS_EQUIPO
from app.models.solicitud_pieza import SolicitudPieza
from app.models.user import User, Movimiento
from app.utils.auth_decorators import login_required
from app import db
from functools import wraps
from datetime import datetime
from sqlalchemy import func

deposito_bp = Blueprint('deposito', __name__, url_prefix='/deposito')

# ============================================
# DECORADOR DE PERMISOS
# ============================================

def deposito_access_required():
    """Solo Site, Coordinadores, y Depósito"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role', '')
            user_dept = session.get('depto', '')
            
            roles_permitidos = ['site', 'coordinador', 'admin']
            departamentos_permitidos = ['deposito', 'site', 'global', 'coordinacion']
            
            role_lower = user_role.lower() if user_role else ''
            dept_lower = user_dept.lower() if user_dept else ''
            
            tiene_acceso = (
                any(r in role_lower for r in roles_permitidos) or
                any(d in dept_lower for d in departamentos_permitidos)
            )
            
            if not tiene_acceso:
                return jsonify({'error': 'Acceso denegado. Solo Site, Coordinadores y Depósito.'}), 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================
# DASHBOARD PRINCIPAL
# ============================================

@deposito_bp.route('/')
@login_required
@deposito_access_required()
def dashboard():
    """Dashboard principal de depósito con tracking por SN"""
    
    # Obtener piezas (últimas 100)
    piezas = PiezaDeposito.query.order_by(PiezaDeposito.fecha_ingreso.desc()).limit(100).all()
    
    # Solicitudes pendientes
    solicitudes = SolicitudPieza.query.filter_by(
        estado='pendiente_deposito'
    ).order_by(SolicitudPieza.fecha_solicitud.asc()).all()
    
    # Estadísticas
    total_piezas = PiezaDeposito.query.count()
    disponibles = PiezaDeposito.query.filter_by(estado='DISPONIBLE', ubicacion='STOCK').count()
    en_lab = PiezaDeposito.query.filter_by(ubicacion='LAB').count()
    reparadas = PiezaDeposito.query.filter_by(es_reparado=True).count()
    total_cajas = db.session.query(func.count(func.distinct(PiezaDeposito.caja_numero))).scalar() or 0
    
    stats = {
        'total_piezas': total_piezas,
        'disponibles': disponibles,
        'en_lab': en_lab,
        'reparadas': reparadas,
        'solicitudes_pendientes': len(solicitudes),
        'total_cajas': total_cajas
    }
    
    # Resumen por tipo
    resumen_tipos = {}
    for tipo in TIPOS_PIEZA:
        count = PiezaDeposito.query.filter_by(tipo=tipo).count()
        if count > 0:
            resumen_tipos[tipo] = count
    
    return render_template('deposito_dashboard.html', 
                          piezas=piezas,
                          solicitudes=solicitudes,
                          stats=stats,
                          resumen_tipos=resumen_tipos)


# ============================================
# API: PIEZAS (CRUD)
# ============================================

@deposito_bp.route('/api/piezas')
@login_required
@deposito_access_required()
def get_piezas():
    """Obtiene piezas con filtros"""
    sn = request.args.get('sn', '')
    tipo = request.args.get('tipo', '')
    modelo = request.args.get('modelo', '')
    ubicacion = request.args.get('ubicacion', '')
    estado = request.args.get('estado', '')
    
    query = PiezaDeposito.query
    
    if sn:
        query = query.filter(PiezaDeposito.sn.ilike(f'%{sn}%'))
    if tipo:
        query = query.filter_by(tipo=tipo)
    if modelo:
        query = query.filter_by(modelo_equipo=modelo)
    if ubicacion:
        query = query.filter_by(ubicacion=ubicacion)
    if estado:
        query = query.filter_by(estado=estado)
    
    limite = 500 if sn else 200
    piezas = query.order_by(PiezaDeposito.fecha_ingreso.desc()).limit(limite).all()
    
    return jsonify({
        'status': 'ok',
        'data': [p.info_completa for p in piezas]
    })


@deposito_bp.route('/api/piezas/crear', methods=['POST'])
@login_required
@deposito_access_required()
def crear_pieza():
    """Crea una nueva pieza"""
    data = request.json
    
    sn = data.get('sn', '').strip()
    tipo = data.get('tipo', '').upper()
    modelo_equipo = data.get('modelo_equipo', '')
    
    if not sn or not tipo or not modelo_equipo:
        return jsonify({'status': 'error', 'message': 'Faltan campos obligatorios (SN, tipo, modelo)'}), 400
    
    # Verificar SN único
    existente = PiezaDeposito.query.filter_by(sn=sn).first()
    if existente:
        return jsonify({'status': 'error', 'message': f'Ya existe una pieza con SN {sn}'}), 400
    
    # Crear pieza
    nueva = PiezaDeposito(
        sn=sn,
        tipo=tipo,
        modelo_equipo=modelo_equipo,
        modelo_pieza=data.get('modelo_pieza', ''),
        caja_numero=int(data.get('caja_numero')) if data.get('caja_numero') else None,
        pallet_numero=int(data.get('pallet_numero')) if data.get('pallet_numero') else None,
        estante=data.get('estante', ''),
        es_reparado=data.get('es_reparado', False),
        ubicacion='STOCK',
        estado='DISPONIBLE',
        registrado_por=session['user_id']
    )
    db.session.add(nueva)
    
    # Registrar movimiento
    db.session.add(MovimientoPiezaDeposito(
        pieza_id=nueva.id,
        tipo_movimiento='INGRESO',
        ubicacion_anterior=None,
        ubicacion_nueva='STOCK',
        motivo='Registro inicial',
        usuario_id=session['user_id']
    ))
    
    # Log general
    db.session.add(Movimiento(
        usuario_id=session['user_id'],
        accion="PIEZA REGISTRADA DEPOSITO",
        referencia_miner=sn,
        datos_nuevos=f"{tipo} {modelo_equipo}. Caja: {data.get('caja_numero', 'N/A')}"
    ))
    
    db.session.commit()
    
    return jsonify({
        'status': 'ok',
        'message': f'Pieza {sn} registrada correctamente',
        'id': nueva.id
    })


@deposito_bp.route('/api/piezas/<int:pieza_id>')
@login_required
@deposito_access_required()
def get_pieza(pieza_id):
    """Obtiene detalle de una pieza"""
    pieza = PiezaDeposito.query.get(pieza_id)
    if not pieza:
        return jsonify({'status': 'error', 'message': 'Pieza no encontrada'}), 404
    
    return jsonify({
        'status': 'ok',
        'data': pieza.info_completa
    })


@deposito_bp.route('/api/piezas/<int:pieza_id>/actualizar', methods=['POST'])
@login_required
@deposito_access_required()
def actualizar_pieza(pieza_id):
    """Actualiza una pieza"""
    pieza = PiezaDeposito.query.get(pieza_id)
    if not pieza:
        return jsonify({'status': 'error', 'message': 'Pieza no encontrada'}), 404
    
    data = request.json
    
    # Actualizar campos permitidos
    if 'ubicacion' in data:
        ubicacion_anterior = pieza.ubicacion
        pieza.ubicacion = data['ubicacion']
        
        db.session.add(MovimientoPiezaDeposito(
            pieza_id=pieza_id,
            tipo_movimiento='TRANSFERENCIA',
            ubicacion_anterior=ubicacion_anterior,
            ubicacion_nueva=data['ubicacion'],
            motivo=data.get('motivo', ''),
            usuario_id=session['user_id']
        ))
    
    if 'estado' in data:
        pieza.estado = data['estado']
    if 'caja_numero' in data:
        pieza.caja_numero = data['caja_numero']
    if 'notas' in data:
        pieza.notas = data['notas']
    
    pieza.modificado_por = session['user_id']
    
    db.session.commit()
    
    return jsonify({'status': 'ok', 'message': 'Pieza actualizada'})


# ============================================
# API: DESPACHO DE PIEZAS
# ============================================

@deposito_bp.route('/api/piezas/despachar', methods=['POST'])
@login_required
@deposito_access_required()
def despachar_pieza():
    """Despacha una pieza específica para una solicitud"""
    data = request.json
    
    solicitud_id = data.get('solicitud_id')
    pieza_id = data.get('pieza_id')
    notas = data.get('notas', '')
    
    if not solicitud_id or not pieza_id:
        return jsonify({'status': 'error', 'message': 'Faltan datos'}), 400
    
    # Validar solicitud
    solicitud = SolicitudPieza.query.get(solicitud_id)
    if not solicitud or solicitud.estado != 'pendiente_deposito':
        return jsonify({'status': 'error', 'message': 'Solicitud no válida'}), 404
    
    # Validar pieza
    pieza = PiezaDeposito.query.get(pieza_id)
    if not pieza:
        return jsonify({'status': 'error', 'message': 'Pieza no encontrada'}), 404
    if pieza.estado != 'DISPONIBLE':
        return jsonify({'status': 'error', 'message': 'Pieza no disponible'}), 400
    
    # Actualizar pieza
    ubicacion_anterior = pieza.ubicacion
    pieza.ubicacion = 'WH' if solicitud.ubicacion_reparacion == 'WH' else 'LAB'
    pieza.estado = 'EN_USO'
    pieza.solicitud_id = solicitud_id
    pieza.fecha_salida = datetime.now()
    pieza.modificado_por = session['user_id']
    
    # Actualizar solicitud
    solicitud.producto_sn = pieza.sn
    solicitud.producto_modelo = f"{pieza.modelo_equipo} {pieza.modelo_pieza or pieza.tipo}"
    solicitud.despachador_id = session['user_id']
    solicitud.fecha_despacho = datetime.now()
    solicitud.notas_deposito = notas
    solicitud.estado = 'en_camino'
    
    # Registrar movimiento de pieza
    destino_wh = solicitud.wh_origen or (solicitud.miner.warehouse_id if solicitud.miner else None)
    db.session.add(MovimientoPiezaDeposito(
        pieza_id=pieza_id,
        tipo_movimiento='SALIDA',
        ubicacion_anterior=ubicacion_anterior,
        ubicacion_nueva=pieza.ubicacion,
        solicitud_pieza_id=solicitud_id,
        destino_wh=destino_wh,
        motivo=f"Despacho solicitud #{solicitud_id}. {notas}",
        usuario_id=session['user_id']
    ))
    
    # Log general
    db.session.add(Movimiento(
        usuario_id=session['user_id'],
        accion="DESPACHO PIEZA",
        referencia_miner=pieza.sn,
        datos_nuevos=f"Para solicitud #{solicitud_id}. Destino: WH{destino_wh or '?'}"
    ))
    
    db.session.commit()
    
    return jsonify({
        'status': 'ok',
        'message': f'Pieza {pieza.sn} despachada correctamente',
        'data': {
            'pieza_sn': pieza.sn,
            'destino': f"WH{destino_wh}" if destino_wh else solicitud.ubicacion_reparacion
        }
    })


# ============================================
# API: SOLICITUDES
# ============================================

@deposito_bp.route('/api/solicitudes')
@login_required
@deposito_access_required()
def get_solicitudes():
    """Obtiene solicitudes pendientes"""
    solicitudes = SolicitudPieza.query.filter_by(
        estado='pendiente_deposito'
    ).order_by(SolicitudPieza.fecha_solicitud.asc()).all()
    
    return jsonify({
        'status': 'ok',
        'data': [{
            'id': s.id,
            'tipo_pieza': s.tipo_pieza,
            'miner_sn': s.miner.sn_fisica if s.miner else 'N/A',
            'miner_modelo': s.miner.modelo if s.miner else 'N/A',
            'wh_origen': s.wh_origen or (s.miner.warehouse_id if s.miner else None),
            'ubicacion': s.ubicacion_reparacion,
            'solicitante': s.solicitante.username if s.solicitante else 'N/A',
            'solicitante_rol': s.solicitante.role.nombre_puesto if s.solicitante and s.solicitante.role else '',
            'fecha': s.fecha_solicitud.strftime('%d/%m/%Y %H:%M') if s.fecha_solicitud else ''
        } for s in solicitudes]
    })


# ============================================
# API: HISTORIAL
# ============================================

@deposito_bp.route('/api/historial')
@login_required
@deposito_access_required()
def get_historial():
    """Historial de movimientos"""
    limite = request.args.get('limite', 50, type=int)
    
    movimientos = MovimientoPiezaDeposito.query.order_by(
        MovimientoPiezaDeposito.fecha.desc()
    ).limit(limite).all()
    
    return jsonify({
        'status': 'ok',
        'data': [{
            'id': m.id,
            'pieza_sn': m.pieza.sn if m.pieza else 'N/A',
            'tipo': m.tipo_movimiento,
            'ubicacion_anterior': m.ubicacion_anterior,
            'ubicacion_nueva': m.ubicacion_nueva,
            'destino_wh': m.destino_wh,
            'motivo': m.motivo,
            'usuario': m.usuario.username if m.usuario else 'N/A',
            'fecha': m.fecha.strftime('%d/%m/%Y %H:%M') if m.fecha else ''
        } for m in movimientos]
    })


# ============================================
# STATS EN TIEMPO REAL
# ============================================

@deposito_bp.route('/stats-partial')
@login_required  
@deposito_access_required()
def stats_partial():
    """Stats para polling"""
    total = PiezaDeposito.query.count()
    disponibles = PiezaDeposito.query.filter_by(estado='DISPONIBLE', ubicacion='STOCK').count()
    pendientes = SolicitudPieza.query.filter_by(estado='pendiente_deposito').count()
    
    return jsonify({
        'total_piezas': total,
        'disponibles': disponibles,
        'solicitudes_pendientes': pendientes
    })


# ============================================
# IMPORTAR DESDE SHEETS (TODO)
# ============================================

@deposito_bp.route('/api/importar-sheets', methods=['POST'])
@login_required
@deposito_access_required()
def importar_sheets():
    """Importa datos desde Google Sheets por ID de planilla"""
    from app.services.sheets_service import GoogleSheetsService
    from app.models.pieza_deposito import PiezaDeposito, MovimientoPiezaDeposito
    
    data = request.json
    spreadsheet_id = data.get('spreadsheet_id')
    
    if not spreadsheet_id:
        return jsonify({'status': 'error', 'message': 'Falta ID de planilla'}), 400
    
    # Inicializar servicio de Sheets
    sheets_service = GoogleSheetsService()
    
    # Importar datos
    resultado = sheets_service.importar_inventario_deposito(spreadsheet_id)
    
    if resultado['status'] != 'ok':
        return jsonify(resultado), 500
    
    # Procesar piezas
    piezas_importadas = resultado['piezas']
    creadas = 0
    duplicadas = 0
    errores_db = []
    
    for pieza_data in piezas_importadas:
        try:
            # Verificar si ya existe
            existente = PiezaDeposito.query.filter_by(sn=pieza_data['sn']).first()
            if existente:
                duplicadas += 1
                continue
            
            # Crear nueva pieza
            nueva = PiezaDeposito(
                sn=pieza_data['sn'],
                tipo=pieza_data['tipo'],
                modelo_equipo=pieza_data['modelo_equipo'],
                caja_numero=pieza_data.get('caja_numero'),
                es_reparado=pieza_data.get('es_reparado', False),
                ubicacion=pieza_data.get('ubicacion', 'STOCK'),
                estado='DISPONIBLE',
                registrado_por=session['user_id']
            )
            db.session.add(nueva)
            
            # Flush para obtener el ID antes de crear el movimiento
            db.session.flush()
            
            # Registrar movimiento
            db.session.add(MovimientoPiezaDeposito(
                pieza_id=nueva.id,
                tipo_movimiento='INGRESO',
                ubicacion_anterior=None,
                ubicacion_nueva=nueva.ubicacion,
                motivo=f'Importado desde Sheets - {pieza_data.get("hoja_origen", "N/A")}',
                usuario_id=session['user_id']
            ))
            
            creadas += 1
            
        except Exception as e:
            db.session.rollback()
            errores_db.append(f"{pieza_data.get('sn', 'N/A')}: {str(e)}")
            continue
    
    # Commit todo junto
    try:
        db.session.commit()
        
        # Log general
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="IMPORTACION MASIVA DEPOSITO",
            referencia_miner=spreadsheet_id[:20],
            datos_nuevos=f"Importadas: {creadas}. Duplicadas: {duplicadas}. Hojas: {len(resultado['hojas_procesadas'])}"
        ))
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error al guardar en BD: {str(e)}'
        }), 500
    
    return jsonify({
        'status': 'ok',
        'creadas': creadas,
        'duplicadas': duplicadas,
        'total_procesadas': len(piezas_importadas),
        'hojas_procesadas': resultado['hojas_procesadas'],
        'errores_sheets': resultado.get('errores', []),
        'errores_db': errores_db
    })


