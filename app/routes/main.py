from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, flash
from app.utils.auth_decorators import login_required, admin_required
from app.utils.permission_decorators import (
    department_required,
    role_required,
    warehouse_permission_required,
    supervisor_or_admin_required,
    lab_technician_required,
    api_permission_check,
    coordinator_or_higher_required
)
from app.services.sheets_service import GoogleSheetsService
from app.services.miner_service import miner_service
from app.services.movement_service import movement_service
from app.services.repair_service import repair_service
from app.models.miner import Miner, MinerModel
from app.models.user import User, Movimiento
from sqlalchemy import or_
from app import db
from datetime import datetime
import threading

main_bp = Blueprint('main', __name__)

# ==========================================
# 1. FUNCIONES EN SEGUNDO PLANO (THREADING)
# ==========================================
HYDRO_WH_ID = 100  # ID de warehouse para Hydro

def redirect_to_rack(wh, rack):
    """
    Genera la redirección correcta según sea Hydro o WH normal.
    Para Hydro (wh=100): redirige a /dashboard/hydro/container/X?rack=Y
    Para WH normal: redirige a /dashboard/wh/rack
    """
    try:
        wh_int = int(wh)
        rack_int = int(rack)
        if wh_int == HYDRO_WH_ID:
            container_num = (rack_int + 1) // 2
            return redirect(url_for('main.dashboard_container', container=container_num, rack=rack_int))
    except:
        pass
    return redirect(url_for('main.dashboard', wh=wh, rack=rack))

def tarea_background_rma(datos):
    """Exporta RMA a Google Sheets, detectando si es Hydro o WH"""
    try:
        sheets = GoogleSheetsService()
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
# 2. VISTAS PRINCIPALES (DASHBOARDS)
# ==========================================
@main_bp.route('/')
@login_required
def index():
    """Redirige al dashboard apropiado según el rol del usuario"""
    user_role = session.get('role', '')
    user_dept = session.get('depto', '')
    
    # Site Manager -> Dashboard Site Manager
    if 'Site Manager' in user_role:
        return redirect(url_for('main.dashboard_coordinador'))  # Por ahora usa mismo que coordinador
    
    # Coordinadores -> Dashboard Coordinador
    elif 'Coordinador' in user_role:
        return redirect(url_for('main.dashboard_coordinador'))
    
    # Personal de Lab -> Lab Hub
        return redirect(url_for('lab.dashboard'))
    
    # Personal de Depósito -> Dashboard Depósito
    elif user_dept == 'Deposito' or 'Deposito' in user_role:
        return redirect(url_for('deposito.dashboard'))
    
    # Personal de Hydro -> Dashboard Hydro
    elif user_dept == 'Hydro' or 'Hydro' in user_role:
        return redirect(url_for('main.dashboard_hydro'))
    
    # Técnicos y Supervisores WH -> Dashboard Técnico
    else:
        return redirect(url_for('main.dashboard_tecnico'))



@main_bp.route('/lab/solicitudes')
@login_required
@lab_technician_required()  # Solo personal de laboratorio
def lab_solicitudes():
    """Vista de solicitudes pendientes usando RepairService"""
    solicitudes = repair_service.get_pending_requests()
    return render_template('lab_solicitudes.html', solicitudes=solicitudes)

@main_bp.route('/lab/solicitudes-partial')
@login_required
@lab_technician_required()
def lab_solicitudes_partial():
    """Partial HTMX para actualización automática de solicitudes"""
    solicitudes = repair_service.get_pending_requests()
    return render_template('partials/lab_solicitudes_body.html', solicitudes=solicitudes)

@main_bp.route('/lab/stock')
@login_required
@lab_technician_required()  # Solo personal de laboratorio
def lab_stock():
    """Stock de laboratorio con filtros por sector"""
    sector = request.args.get('sector')  # 'WH', 'Hydro' o None
    stock = repair_service.get_stock_lab(sector)
    return render_template('lab_stock.html', stock=stock, sector=sector)

@main_bp.route('/lab/stock-partial')
@login_required
@lab_technician_required()
def lab_stock_partial():
    """Partial HTMX para actualización automática del stock"""
    sector = request.args.get('sector')
    stock = repair_service.get_stock_lab(sector)
    return render_template('partials/stock_grid.html', stock=stock, sector=sector)

@main_bp.route('/lab/cementerio')
@login_required
@lab_technician_required()  # Solo personal de laboratorio
def lab_cementerio():
    """Cementerio - equipos dados de baja"""
    scrap_list = repair_service.get_cemetery()
    return render_template('lab_scrap.html', lista=scrap_list)

@main_bp.route('/monitor')
@login_required
@supervisor_or_admin_required()  # Solo supervisores y admins
def monitor():
    """Monitor de historial - Solo para supervisores+"""
    sn_filter = request.args.get('sn', '').strip()
    
    query = Movimiento.query.order_by(Movimiento.fecha_hora.desc())
    
    if sn_filter:
        # Filtrar movimientos que contengan el SN en referencia_miner o datos_nuevos
        query = query.filter(
            db.or_(
                Movimiento.referencia_miner.ilike(f'%{sn_filter}%'),
                Movimiento.datos_nuevos.ilike(f'%{sn_filter}%')
            )
        )
    
    historial = query.limit(100).all()
    return render_template('admin/monitor.html', historial=historial)


@main_bp.route('/mi-historial')
@login_required
def mi_historial():
    """Historial personal y de mi grupo (mismos WH/Contenedores)"""
    user = User.query.get(session['user_id'])
    my_whs = user.get_assigned_warehouses()
    
    if not my_whs:
        # Si no tiene WH, solo mostrar sus propios movimientos
        share_users = [user.id]
    else:
        # Buscar usuarios que compartan al menos un WH o Contenedor
        all_users = User.query.all()
        share_users = []
        
        for u in all_users:
            u_whs = u.get_assigned_warehouses()
            # Intersección de listas: si comparten algún WH
            if set(my_whs) & set(u_whs):
                share_users.append(u.id)
                
        # Asegurar incluirse a sí mismo
        if user.id not in share_users:
            share_users.append(user.id)
    
    # Query movimientos de estos usuarios
    sn_filter = request.args.get('sn', '').strip()
    query = Movimiento.query.filter(Movimiento.usuario_id.in_(share_users)).order_by(Movimiento.fecha_hora.desc())
    
    if sn_filter:
         query = query.filter(
            db.or_(
                Movimiento.referencia_miner.ilike(f'%{sn_filter}%'),
                Movimiento.datos_nuevos.ilike(f'%{sn_filter}%')
            )
        )
        
    historial = query.limit(100).all()
    
    return render_template('mi_historial.html', 
                          historial=historial, 
                          title="MI HISTORIAL DE GRUPO",
                          subtitle=f"Movimientos en mis zonas ({', '.join(map(str, my_whs))})")

@main_bp.route('/dashboard/<int:wh>/<int:rack>')
@login_required
@warehouse_permission_required()  # Verificar acceso al warehouse
def dashboard(wh, rack):
    """Dashboard de warehouse - Solo usuarios con acceso a ese WH"""
    
    # REDIRECCIÓN AUTOMÁTICA: Si es Hydro (wh=100), redirigir al contenedor correcto
    if wh == HYDRO_WH_ID:
        container_num = (rack + 1) // 2
        return redirect(url_for('main.dashboard_container', container=container_num, rack=rack))
    
    # Obtener mineros del rack actual
    mineros_db = Miner.query.filter_by(warehouse_id=wh, rack_id=rack).all()
    datos_matriz = {(m.fila, m.columna): m for m in mineros_db}
    
    # Obtener mineros pendientes de colocación en este WH
    pendientes = Miner.query.filter_by(
        warehouse_id=wh, 
        proceso_estado='pendiente_colocacion'
    ).all()
    
    return render_template('wh_dashboard.html', 
                          wh_actual=wh, 
                          rack_actual=rack, 
                          datos=datos_matriz,
                          pendientes=pendientes)

# --- VISTA: RESUMEN GENERAL (PIVOT) ---
@main_bp.route('/resumen')
@login_required
@supervisor_or_admin_required()  # Solo supervisores y admins pueden ver resumen completo
def resumen():
    """Resumen general pivot (Aire vs Hydro)"""
    mineros = Miner.query.all()
    datos = {
        'aire': {'wh': 0, 'lab': 0, 'total': 0},
        'hydro': {'planta': 0, 'lab': 0, 'total': 0},
        'total_general': 0
    }
    
    for m in mineros:
        modelo_str = (m.modelo or "").lower()
        es_hydro = 'hyd' in modelo_str or 'm33' in modelo_str or 'm53' in modelo_str
        en_lab = m.proceso_estado in ['en_laboratorio', 'en_reparacion', 'stock_lab']
        
        if es_hydro:
            if en_lab: datos['hydro']['lab'] += 1
            else: datos['hydro']['planta'] += 1
            datos['hydro']['total'] += 1
        else:
            if en_lab: datos['aire']['lab'] += 1
            else: datos['aire']['wh'] += 1
            datos['aire']['total'] += 1
        datos['total_general'] += 1

    return render_template('resumen.html', datos=datos)

# --- VISTAS: DASHBOARDS PERSONALIZADOS POR ROL ---
@main_bp.route('/dashboard/coordinador')
@login_required
@supervisor_or_admin_required()
def dashboard_coordinador():
    """Dashboard personalizado para Coordinadores y Site Managers"""
    from app.services.transfer_service import transfer_service
    from app.services.user_service import user_service
    from app.models.user import Movimiento
    
    # Obtener contadores de solicitudes pendientes
    contadores = transfer_service.get_pending_count_by_sector()
    
    # Stats de laboratorio
    stats_lab = repair_service.get_dashboard_stats()
    
    # Actividad reciente (últimos 10 movimientos)
    movimientos_recientes = Movimiento.query.order_by(
        Movimiento.fecha_hora.desc()
    ).limit(10).all()
    
    # Obtener listado de personal para gestión
    user_role = session.get('role', '')
    user_dept = session.get('depto', '')
    personal_lista = user_service.get_all_personnel(user_role, user_dept)
    
    return render_template('dashboard_coordinador.html',
                          pendientes_total=contadores['total'],
                          pendientes_wh=contadores['WH'],
                          pendientes_hydro=contadores['Hydro'],
                          stats_lab=stats_lab,
                          movimientos_recientes=movimientos_recientes,
                          personal_lista=personal_lista,
                          can_manage_wh=('Coordinador' in user_role and user_dept == 'WH') or 'Site Manager' in user_role,
                          can_manage_hydro=('Coordinador' in user_role and user_dept == 'Hydro') or 'Site Manager' in user_role)

@main_bp.route('/dashboard/tecnico')
@login_required
def dashboard_tecnico():
    """Dashboard personalizado para Técnicos de WH"""
    from app.models.solicitud import SolicitudTraslado
    
    # Warehouses asignados al usuario
    mis_wh = session.get('mis_wh', [])
    
    # Mis solicitudes recientes (últimas 5)
    mis_solicitudes = SolicitudTraslado.query.filter_by(
        solicitante_id=session.get('user_id')
    ).order_by(SolicitudTraslado.fecha_solicitud.desc()).limit(5).all()
    
    return render_template('dashboard_tecnico.html',
                          mis_warehouses=mis_wh,
                          mis_solicitudes=mis_solicitudes)

@main_bp.route('/dashboard/hydro')
@login_required
@department_required('Hydro')  # Solo personal de Hydro
def dashboard_hydro():
    """Dashboard personalizado para Técnicos de Hydro"""
    from app.models.solicitud import SolicitudTraslado
    
    # Hydro siempre usa warehouse_id = 100
    HYDRO_WH_ID = 100
    
    # Mis solicitudes recientes (últimas 5)
    mis_solicitudes = SolicitudTraslado.query.filter_by(
        solicitante_id=session.get('user_id')
    ).order_by(SolicitudTraslado.fecha_solicitud.desc()).limit(5).all()
    
    # Estadísticas de Hydro
    total_positions = Miner.query.filter_by(warehouse_id=HYDRO_WH_ID).count()
    operational = Miner.query.filter_by(
        warehouse_id=HYDRO_WH_ID, 
        proceso_estado='operativo'
    ).count()
    empty = Miner.query.filter_by(
        warehouse_id=HYDRO_WH_ID,
        proceso_estado='vacio'
    ).count()
    
    if request.headers.get('HX-Request'):
        return render_template('partials/dashboard_hydro_content.html',
                           warehouse_id=HYDRO_WH_ID,
                           total_containers=110,
                           total_positions=total_positions,
                           operational=operational,
                           empty=empty,
                           mis_solicitudes=mis_solicitudes)

    return render_template('dashboard_hydro.html',
                           warehouse_id=HYDRO_WH_ID,
                           total_containers=110,
                           total_positions=total_positions,
                           operational=operational,
                           empty=empty,
                           mis_solicitudes=mis_solicitudes)

@main_bp.route('/dashboard/hydro/container/<int:container>')
@login_required
@department_required('Hydro')
def dashboard_container(container):
    """Vista de un contenedor específico de Hydro"""
    HYDRO_WH_ID = 100
    
    # Validar rango de contenedor
    if container < 1 or container > 110:
        flash('Contenedor no válido', 'danger')
        return redirect(url_for('main.dashboard_hydro'))
    
    # Calcular rack_ids para este contenedor
    # Container N tiene racks: (N*2-1) y (N*2)
    rack_a_id = (container - 1) * 2 + 1
    rack_b_id = (container - 1) * 2 + 2
    
    # Por defecto mostrar Rack A
    rack_actual = request.args.get('rack', rack_a_id, type=int)
    
    # Validar que el rack pertenece a este contenedor
    if rack_actual not in [rack_a_id, rack_b_id]:
        rack_actual = rack_a_id
    
    # Obtener mineros del rack actual
    mineros_db = Miner.query.filter_by(
        warehouse_id=HYDRO_WH_ID, 
        rack_id=rack_actual
    ).all()
    
    datos_matriz = {(m.fila, m.columna): m for m in mineros_db}
    
    # Obtener mineros pendientes de colocación en Hydro
    pendientes = Miner.query.filter_by(
        warehouse_id=HYDRO_WH_ID, 
        proceso_estado='pendiente_colocacion'
    ).all()
    
    if request.headers.get('HX-Request'):
        return render_template('partials/hydro_container_content.html',
                           container=container,
                           rack_a_id=rack_a_id,
                           rack_b_id=rack_b_id,
                           rack_actual=rack_actual,
                           datos=datos_matriz,
                           warehouse_id=HYDRO_WH_ID,
                           pendientes=pendientes)

    return render_template('hydro_container.html',
                           container=container,
                           rack_a_id=rack_a_id,
                           rack_b_id=rack_b_id,
                           rack_actual=rack_actual,
                           datos=datos_matriz,
                           warehouse_id=HYDRO_WH_ID,
                           pendientes=pendientes)



# ==========================================
# 3. APIS (BUSCADOR Y DATOS)
# ==========================================
@main_bp.route('/api/buscar')
@login_required
def buscar_minero():
    """API de búsqueda de mineros usando MinerService"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'found': False})
    
    # Usar servicio para búsqueda
    resultados = miner_service.search_miners(query)
    
    if resultados:
        return jsonify({
            'found': True,
            'total': len(resultados),
            'resultados': resultados
        })
    
    return jsonify({'found': False})

@main_bp.route('/api/get_miner/<int:wh>/<int:rack>/<int:f>/<int:c>')
@login_required
def get_miner_data(wh, rack, f, c):
    """API para obtener datos de un minero específico usando MinerService"""
    m = miner_service.get_miner_by_position(wh, rack, f, c)
    
    if m:
        return jsonify({
            'id': m.id,  # Para crear solicitudes de traslado
            'modelo': m.modelo,
            'ths': m.ths,
            'ip_address': m.ip_address,
            'mac_address': m.mac_address,
            'sn_fisica': m.sn_fisica,
            'sn_digital': m.sn_digital or '',
            'psu_model': m.psu_model or '',
            'psu_sn': m.psu_sn,
            'cb_sn': m.cb_sn,
            'hb1_sn': m.hb1_sn or '',
            'hb2_sn': m.hb2_sn or '',
            'hb3_sn': m.hb3_sn or '',
            'estado': m.proceso_estado,
            'proceso_estado': m.proceso_estado,  # Alias para JS actualizado
            'diagnostico': m.diagnostico_detalle,
            'diagnostico_detalle': m.diagnostico_detalle,  # Alias para JS actualizado
            'log': m.log_detalle
        })
    
    return jsonify({})

@main_bp.route('/api/check-miner/<int:wh>/<int:rack>/<int:f>/<int:c>')
@login_required
def check_miner(wh, rack, f, c):
    """Verifica si un miner existe en la posición - para auto-removal en tiempo real"""
    # Obtener parámetros de evento del request
    event_wh = request.args.get('event_wh', type=int)
    event_rack = request.args.get('event_rack', type=int)
    event_fila = request.args.get('event_fila', type=int)
    event_columna = request.args.get('event_columna', type=int)
    
    # Solo actualizar si el evento corresponde a este miner específico
    if event_wh == wh and event_rack == rack and event_fila == f and event_columna == c:
        # Verificar si el miner aún existe en esta posición
        m = miner_service.get_miner_by_position(wh, rack, f, c)
        if not m:
            # Miner fue removido, retornar card vacío
            return render_template('partials/miner_card.html',
                                 m=None, wh_actual=wh, rack_actual=rack, f=f, c=c)
    
    # Si no coincide o aún existe, retornar el card actual sin cambios
    m = miner_service.get_miner_by_position(wh, rack, f, c)
    return render_template('partials/miner_card.html',
                         m=m, wh_actual=wh, rack_actual=rack, f=f, c=c)

# ==========================================
# 4. APIS TRANSACCIONALES (GUARDAR, MOVER, RMA)
# ==========================================
@main_bp.route('/api/guardar', methods=['POST'])
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
    # NOTA: ip_address ya no se captura en el formulario normal - solo en RMA
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
        db.session.add(Movimiento(usuario_id=session['user_id'], accion=accion, referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", datos_nuevos=f"SN:{minero.sn_fisica}"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Manejo de error de duplicados si ocurre
        print(f"Error al guardar: {e}")

    return redirect_to_rack(wh, rack)

@main_bp.route('/api/rma/enviar_y_exportar', methods=['POST'])
@login_required
def enviar_y_exportar():
    wh = request.form.get('wh')
    rack = request.form.get('rack')
    f = request.form.get('fila')
    c = request.form.get('columna')
    
    # Validar datos obligatorios
    if not all([wh, rack, f, c]):
        flash('Datos de ubicación incompletos', 'danger')
        return redirect(url_for('main.index'))
    
    problem_type = request.form.get('diagnostico_detalle', '')
    log_text = request.form.get('log_detalle', '')
    
    # Validar que el problema esté especificado
    if not problem_type or problem_type.strip() == '':
        flash('Debe especificar el tipo de problema antes de enviar al laboratorio', 'warning')
        return redirect_to_rack(wh, rack)
    
    # Capturar IP del puerto actual (requerido para RMA)
    ip_rma = request.form.get('ip_rma', '').strip()
    
    if not ip_rma:
        flash('Debe ingresar la IP del puerto actual', 'warning')
        return redirect_to_rack(wh, rack)
    
    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if not minero:
        flash('Minero no encontrado en la posición especificada', 'danger')
        return redirect_to_rack(wh, rack)
    
    # Actualización de datos frescos antes de exportar
    minero.sn_digital = request.form.get('sn_digital')
    minero.mac_address = request.form.get('mac')
    # NOTA: Ya no actualizamos ip_address - se captura solo en el momento del RMA
    minero.psu_model = request.form.get('psu_model')
    minero.psu_sn = request.form.get('psu_sn')
    minero.cb_sn = request.form.get('cb_sn')
    minero.hb1_sn = request.form.get('hb1_sn')
    minero.hb2_sn = request.form.get('hb2_sn')
    minero.hb3_sn = request.form.get('hb3_sn')
    
    # IMPORTANTE: RMA solo registra el problema, NO mueve el equipo
    # El equipo permanece en el warehouse hasta que se apruebe una Solicitud de Traslado
    minero.fecha_diagnostico = datetime.now()
    minero.diagnostico_detalle = problem_type
    minero.log_detalle = log_text
    
    db.session.commit()

    datos_para_sheets = {
        'fecha': datetime.now().strftime("%d/%m/%Y"),
        'responsable': session.get('username', 'Usuario'),
        'wh': wh, 'rack': rack, 'problem': problem_type,
        'ip': ip_rma,  # IP del puerto actual, no del registro del minero
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
            container_num = (rack_int + 1) // 2
            datos_para_sheets['container'] = container_num
    except:
        pass
    
    # Exportar a Google Sheets en background
    hilo = threading.Thread(target=tarea_background_rma, args=(datos_para_sheets,))
    hilo.start()
    
    # Registrar en historial
    db.session.add(Movimiento(
        usuario_id=session['user_id'], 
        accion="REGISTRO RMA", 
        referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
        datos_nuevos=f"SN: {minero.sn_fisica} -> Falla: {problem_type}"
    ))
    db.session.commit()
    
    flash(f'RMA registrado para {minero.sn_fisica}. Para mover el equipo, cree una Solicitud de Traslado.', 'success')
    return redirect_to_rack(wh, rack)

@main_bp.route('/api/mover', methods=['POST'])
@login_required
def mover():
    data = request.json
    wh, rack, f, c = data['wh'], data['rack'], data['f'], data['c']
    motivo = data.get('motivo', 'Sin motivo especificado')

    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if minero:
        # 1. AUTO-GUARDADO
        if 'sn_digital' in data: minero.sn_digital = data['sn_digital']
        if 'mac' in data: minero.mac_address = data['mac']
        db.session.commit()

        # 2. Hilo a Sheets
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

        # 3. Log
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="TRASLADO (SALIDA)", 
            referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
            datos_nuevos=f"SN: {sn_temp} retirado a LAB. Motivo: {motivo}"
        ))

        # 4. ACTUALIZACIÓN CRÍTICA (NO BORRAR)
        # Limpiamos ubicación para liberar rack, pero mantenemos el registro
        minero.warehouse_id = None
        minero.rack_id = None
        minero.fila = None
        minero.columna = None
        minero.proceso_estado = 'en_laboratorio'
        
        db.session.commit()
        return jsonify({'status': 'ok'})
    
    return jsonify({'status': 'error', 'message': 'No encontrado'}), 404

@main_bp.route('/api/rma/cancelar', methods=['POST'])
@login_required
def cancelar_rma():
    data = request.json
    wh, rack, f, c = data['wh'], data['rack'], data['f'], data['c']
    
    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if minero:
        # Limpiar estado de RMA completamente
        minero.proceso_estado = 'operativo'
        minero.diagnostico_detalle = None  # Limpiar diagnóstico
        minero.log_detalle = None  # Limpiar log
        minero.fecha_diagnostico = None  # Limpiar fecha
        
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="RMA CANCELADO", 
            referencia_miner=f"WH{wh}-R{rack}-{f}:{c}", 
            datos_nuevos=f"SN: {minero.sn_fisica} restaurado a operativo"
        ))
        db.session.commit()
        return jsonify({'status': 'ok'})
    
    return jsonify({'status': 'error'}), 404

@main_bp.route('/api/conciliar', methods=['POST'])
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

@main_bp.route('/api/lab/scrap', methods=['POST']) 
@login_required
@lab_technician_required()
def scrap_equipo():
    """Da de baja un equipo"""
    # HTMX puede enviar form data o json
    data = request.get_json(silent=True) or request.form
    
    miner_id = data.get('id')
    tipo = data.get('tipo')  # 'piezas' o 'basura'
    motivo = data.get('motivo', 'Sin motivo irreparable')
    
    # Mapear tipo del cliente a tipo de BD
    if tipo == 'basura':
        tipo_bd = 'baja_definitiva'
        accion_log = "BAJA (DESECHO)"
        msg_extra = "Equipo desechado/reciclado."
    else:
        tipo_bd = 'donante_piezas'
        accion_log = "BAJA (DESGUACE)"
        msg_extra = "Equipo almacenado como donante de repuestos."
    
    # Usar servicio
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

# --- VISTA: MESA DE TRABAJO (EN REPARACIÓN) ---
@main_bp.route('/lab/reparacion')
@login_required
def lab_reparacion():
    """Vista de mesa de trabajo usando RepairService"""
    en_mesa = repair_service.get_in_repair()
    return render_template('lab_reparacion.html', equipos=en_mesa)

@main_bp.route('/lab/reparacion-partial')
@login_required
@lab_technician_required()
def lab_reparacion_partial():
    """Partial HTMX para actualización automática de mesa de trabajo"""
    equipos = repair_service.get_in_repair()
    return render_template('partials/lab_reparacion_grid.html', equipos=equipos)


# --- API: INICIAR REPARACIÓN (De Solicitud -> Mesa) ---
@main_bp.route('/api/lab/iniciar', methods=['POST'])
@login_required
@lab_technician_required()
def iniciar_reparacion():
    """Mueve equipo de Solicitudes a Mesa de Trabajo"""
    # HTMX puede enviar form data o json
    data = request.get_json(silent=True) or request.form
    miner_id = data.get('id')
    
    # Validar
    if not miner_id:
        # Intentar obtener de args si es GET (aunque es POST)
        miner_id = request.args.get('id')
    
    # Usar servicio
    success = repair_service.start_repair(miner_id)
    
    if success:
        # Log del movimiento
        minero = Miner.query.get(miner_id)
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="INICIO REPARACIÓN",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos="Equipo en mesa de trabajo."
        ))
        db.session.commit()
        
        # Retornar HTML vacío para HTMX (elimina el elemento)
        return '', 200
    
    return jsonify({'status': 'error'}), 404


# --- API: REPARACIÓN EXITOSA (De Mesa -> Stock Lab) ---
@main_bp.route('/api/lab/terminar', methods=['POST'])
@login_required
@lab_technician_required()
def terminar_reparacion():
    """Finaliza reparación moviendo a Stock Lab"""
    # HTMX puede enviar form data o json
    data = request.get_json(silent=True) or request.form
    miner_id = data.get('id')
    solucion = data.get('solucion', 'Reparación estándar')
    
    # Usar servicio
    success = repair_service.finish_repair(miner_id, solucion)
    
    if success:
        # Log del movimiento
        minero = Miner.query.get(miner_id)
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="REPARACIÓN FINALIZADA",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos=f"Equipo pasa a STOCK LAB. Solución: {solucion}"
        ))
        db.session.commit()
        
        # Retornar HTML vacío para HTMX (elimina el elemento)
        return '', 200
    
    return jsonify({'status': 'error'}), 404


# --- API: REINSTALAR EQUIPO (Stock Lab → Warehouse) ---
@main_bp.route('/api/lab/reinstalar', methods=['POST'])
@login_required
@lab_technician_required()
def reinstalar_equipo():
    """Reinstala un equipo del stock lab a un warehouse"""
    # HTMX puede enviar form data o json
    data = request.get_json(silent=True) or request.form
    
    miner_id = data.get('id')
    wh = data.get('wh')
    
    # Coordenadas opcionales
    rack = data.get('rack')
    fila = data.get('fila')
    columna = data.get('columna')
    
    # Validar datos mínimos
    if not miner_id or not wh:
        return jsonify({'status': 'error', 'message': 'Datos incompletos'}), 400
    
    # Convertir a int si existen
    def to_int_or_none(val):
        return int(val) if val and val != '' else None
        
    rack = to_int_or_none(rack)
    fila = to_int_or_none(fila)
    # LÓGICA ESPECIAL HYDRO: Recuperar CONTENEDOR original (Rack)
    # El usuario quiere que vuelva a su container, pero que el técnico ubique la fila/columna exacta.
    HYDRO_WH_ID = 100
    if int(wh) == HYDRO_WH_ID and not rack:
        from app.models.solicitud import SolicitudTraslado
        # Buscar último traslado hacia LAB
        last_transfer = SolicitudTraslado.query.filter_by(
            miner_id=miner_id,
            destino='LAB'
        ).order_by(SolicitudTraslado.fecha_solicitud.desc()).first()
        
        if last_transfer and last_transfer.origen_wh == HYDRO_WH_ID:
            rack = last_transfer.origen_rack
            # NO recuperamos fila/columna por petición del usuario (técnico ubicará)
            fila = None
            columna = None
    
    # Usar servicio (ahora retorna dict)
    result = repair_service.return_to_warehouse(
        int(miner_id),
        int(wh),
        rack,
        fila,
        columna
    )
    
    if result.get('success'):
        # Log del movimiento
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

        
        response = jsonify({'status': 'ok', 'message': 'Equipo reinstalado exitosamente'})
        response.headers['HX-Trigger'] = 'reloadStock'
        return response
    
    # Si hubo error, retornar el mensaje específico
    error_msg = result.get('error', 'Error al reinstalar')
    return jsonify({'status': 'error', 'message': error_msg}), 400


# --- API PARTIAL: ESTADÍSTICAS EN TIEMPO REAL ---
@main_bp.route('/lab/stats-partial')
@login_required
def lab_stats_partial():
    """Partial para actualización HTMX de estadísticas usando RepairService"""
    stats = repair_service.get_lab_stats()
    
    return render_template('partials/lab_stats.html', 
                           c_pendientes=stats['c_pendientes'],
                           c_reparacion=stats['c_reparacion'],
                           c_stock=stats['c_stock'],
                           c_scrap=stats['c_scrap'])