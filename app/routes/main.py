from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, flash, current_app, abort
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
from app.services.sheets_queue import enqueue_sheet_export
from app.services.miner_service import miner_service
from app.services.movement_service import movement_service
from app.services.repair_service import repair_service
from app.services.transfer_service import transfer_service
from app.services.drive_service import GoogleDriveService
from app.models.miner import Miner, MinerModel
from app.models.user import User, Movimiento
from app.models.solicitud import SolicitudTraslado
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from app import db
from datetime import datetime, timedelta
from pathlib import Path
import threading
from app.utils.helpers import format_ubicacion

main_bp = Blueprint('main', __name__)

# ==========================================
# 1. FUNCIONES EN SEGUNDO PLANO (THREADING)
# ==========================================
HYDRO_WH_ID = 100  # ID de warehouse para Hydro
ASSET_WHITELIST = {
    'htmx.min.js': Path('js/htmx.min.js'),
    'rma_actions.js': Path('js/rma_actions.js'),
}


def _read_ram_usage():
    """Lee /proc/meminfo para calcular uso de RAM sin dependencias externas."""
    meminfo = {}
    with open('/proc/meminfo') as fh:
        for line in fh:
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            try:
                meminfo[key.strip()] = float(value.strip().split()[0])  # kB
            except (ValueError, IndexError):
                continue

    total_kb = meminfo.get('MemTotal', 0)
    avail_kb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
    free_kb = meminfo.get('MemFree', 0)
    used_kb = max(total_kb - avail_kb, 0)

    def kb_to_mb(kb):
        return round(kb / 1024, 2)

    return {
        'total_mb': kb_to_mb(total_kb),
        'used_mb': kb_to_mb(used_kb),
        'available_mb': kb_to_mb(avail_kb),
        'free_mb': kb_to_mb(free_kb),
        'used_percent': round((used_kb / total_kb) * 100, 2) if total_kb else 0,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }


@main_bp.route('/assets/<path:asset_name>')
def serve_asset(asset_name: str):
    """Entrega assets críticos incluso si /static está bloqueado."""
    allowed_path = ASSET_WHITELIST.get(asset_name)
    if not allowed_path:
        abort(404)

    static_dir = Path(current_app.root_path) / 'static'
    file_path = static_dir / allowed_path
    if not file_path.is_file():
        abort(404)

    response = current_app.response_class(
        file_path.read_text(encoding='utf-8'),
        mimetype='application/javascript'
    )
    response.headers.setdefault('Cache-Control', 'public, max-age=3600')
    return response

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

def tarea_background_rma(app_obj, datos):
    """Encola RMA para exportar a Sheets a las 18:00."""
    try:
        with app_obj.app_context():
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
    fecha_query = request.args.get('fecha', '').strip()
    sector = (request.args.get('sector', 'all') or 'all').lower()
    query = Movimiento.query
    subtitle = "Últimos 50 movimientos registrados en el sistema"
    limit = 50
    fecha_filtrada = None

    hydro_filter = db.or_(
        Movimiento.referencia_miner.ilike('%HYDRO%'),
        Movimiento.referencia_miner.ilike('%WH100%'),
        Movimiento.referencia_miner.ilike('%WH 100%'),
        Movimiento.datos_nuevos.ilike('%HYDRO%'),
        Movimiento.datos_nuevos.ilike('%WH100%'),
        Movimiento.datos_nuevos.ilike('%WH 100%')
    )
    
    if sn_filter:
        query = query.filter(
            db.or_(
                Movimiento.referencia_miner.ilike(f'%{sn_filter}%'),
                Movimiento.datos_nuevos.ilike(f'%{sn_filter}%')
            )
        )
        subtitle = f"Resultados filtrados por '{sn_filter}'"
        limit = 200
    
    if fecha_query:
        try:
            fecha_filtrada = datetime.strptime(fecha_query, '%Y-%m-%d')
            inicio = datetime.combine(fecha_filtrada.date(), datetime.min.time())
            fin = inicio + timedelta(days=1)
            query = query.filter(
                Movimiento.fecha_hora >= inicio,
                Movimiento.fecha_hora < fin
            )
            subtitle = f"Movimientos del {fecha_filtrada.strftime('%d/%m/%Y')}"
            limit = None
        except ValueError:
            flash('Formato de fecha inválido. Usa AAAA-MM-DD.', 'warning')

    if sector == 'hydro':
        query = query.filter(hydro_filter)
        subtitle = "Movimientos Hydro"
    elif sector == 'wh':
        query = query.filter(~hydro_filter)
        subtitle = "Movimientos WH"
    
    query = query.order_by(Movimiento.fecha_hora.desc())
    historial = query.all() if limit is None else query.limit(limit).all()
    
    if fecha_filtrada and sn_filter:
        subtitle = f"Movimientos del {fecha_filtrada.strftime('%d/%m/%Y')} filtrados por '{sn_filter}'"
    elif fecha_filtrada:
        subtitle = f"Movimientos del {fecha_filtrada.strftime('%d/%m/%Y')}" if sector == 'all' else subtitle + f" del {fecha_filtrada.strftime('%d/%m/%Y')}"
    elif sn_filter:
        subtitle = subtitle if sector != 'all' else subtitle
    
    return render_template('admin/monitor.html', historial=historial, monitor_subtitle=subtitle, sector=sector)


@main_bp.route('/it/salud')
@login_required
@supervisor_or_admin_required()
def it_health():
    """Vista de salud IT: métricas básicas del servidor."""
    return render_template('it_health.html')


@main_bp.route('/api/system/ram')
@login_required
@supervisor_or_admin_required()
def api_system_ram():
    """API JSON con consumo de RAM del host."""
    try:
        data = _read_ram_usage()
        return jsonify({'status': 'ok', 'data': data})
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@main_bp.route('/monitor/export', methods=['POST'])
@login_required
@supervisor_or_admin_required()
def export_monitor():
    """Exporta el monitor del mes seleccionado (o actual) a Google Sheets."""
    sn_filter = request.form.get('sn', '').strip()
    fecha_query = request.form.get('fecha', '').strip()
    sector = (request.form.get('sector', 'all') or 'all').lower()
    redirect_params = {}
    if sn_filter:
        redirect_params['sn'] = sn_filter
    if fecha_query:
        redirect_params['fecha'] = fecha_query
    if sector:
        redirect_params['sector'] = sector
    redirect_url = url_for('main.monitor', **redirect_params)

    try:
        if fecha_query:
            target_date = datetime.strptime(fecha_query, '%Y-%m-%d')
        else:
            target_date = datetime.now()
    except ValueError:
        flash('Formato de fecha inválido para exportación.', 'danger')
        return redirect(redirect_url)

    period_start = target_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)

    query = Movimiento.query.filter(
        Movimiento.fecha_hora >= period_start,
        Movimiento.fecha_hora < period_end
    )

    if sn_filter:
        query = query.filter(
            db.or_(
                Movimiento.referencia_miner.ilike(f'%{sn_filter}%'),
                Movimiento.datos_nuevos.ilike(f'%{sn_filter}%')
            )
        )

    movimientos = query.order_by(Movimiento.fecha_hora.asc()) \
        .options(joinedload(Movimiento.usuario).joinedload('role')) \
        .all()

    filas = []
    for mov in movimientos:
        fecha = mov.fecha_hora.strftime('%Y-%m-%d') if mov.fecha_hora else ''
        hora = mov.fecha_hora.strftime('%H:%M:%S') if mov.fecha_hora else ''
        usuario = mov.usuario.username if mov.usuario else 'N/A'
        rol = mov.usuario.role.nombre_puesto if mov.usuario and mov.usuario.role else ''
        filas.append([
            mov.id,
            fecha,
            hora,
            usuario,
            rol,
            mov.accion or '',
            mov.referencia_miner or '',
            mov.datos_nuevos or ''
        ])

    periodo_label = period_start.strftime('%Y-%m')
    sheets = GoogleSheetsService()
    if not filas:
        flash('No hay movimientos para exportar en ese período.', 'warning')
        return redirect(redirect_url)

    sheet_title = f"Historial {periodo_label}"
    if sheets.exportar_monitor_historial(filas, sheet_title=sheet_title):
        flash(f'Se exportaron {len(filas)} movimientos a la hoja "{sheet_title}".', 'success')
    else:
        flash('No se pudo exportar el monitor a Google Sheets.', 'danger')

    return redirect(redirect_url)


@main_bp.route('/mi-historial')
@login_required
def mi_historial():
    """Historial personal y de mi grupo (mismos WH/Contenedores)"""
    user = User.query.get(session['user_id'])
    my_whs = [wh for wh in user.get_assigned_warehouses() if wh != HYDRO_WH_ID]
    my_containers = user.get_assigned_containers() or []
    my_hydro_racks = []
    for c in my_containers:
        try:
            c_int = int(c)
            my_hydro_racks.extend([c_int * 2 - 1, c_int * 2])
        except (TypeError, ValueError):
            continue
    
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
        
    def pertenece_a_mis_wh(mov: Movimiento) -> bool:
        ref = (mov.referencia_miner or '').upper()
        data = (mov.datos_nuevos or '').upper()

        def contains_token(token: str) -> bool:
            return token in ref or token in data

        # Manejo Hydro: solo si tiene contenedores asignados y coincide
        hydro_mentions = any(contains_token(t) for t in ['HYDRO', 'WH100', 'WH 100'])
        if hydro_mentions:
            if not my_hydro_racks and not my_containers:
                return False
            # Coincidir por rack o contenedor
            for rack in my_hydro_racks:
                rack_token = f"R{rack}".upper()
                if contains_token(rack_token):
                    return True
            for c in my_containers:
                cont_token = f"C{c}".upper()
                if contains_token(cont_token):
                    return True
            return False

        # Aire: requiere match con WH asignados
        if not my_whs:
            return True

        for wh in my_whs:
            tag = f"WH{wh}".upper()
            tag_spaced = f"WH {wh}".upper()
            if contains_token(tag) or contains_token(tag_spaced):
                return True
        return False

    historial_raw = query.limit(300).all()
    historial = [m for m in historial_raw if pertenece_a_mis_wh(m)][:100]
    
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
    datos = miner_service.get_resumen_aire_hydro()
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
        ubicacion_str = format_ubicacion(wh, rack, f, c)
        db.session.add(Movimiento(usuario_id=session['user_id'], accion=accion, referencia_miner=ubicacion_str, datos_nuevos=f"SN:{minero.sn_fisica}"))
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
    
    # Siempre devolver JSON si la petición espera JSON
    wants_json = 'application/json' in request.headers.get('Accept', '')
    
    # Validar datos obligatorios
    if not all([wh, rack, f, c]):
        if wants_json:
            return jsonify({'status': 'error', 'message': 'Datos de ubicación incompletos'}), 400
        flash('Datos de ubicación incompletos', 'danger')
        return redirect(url_for('main.index'))
    
    problem_type = request.form.get('diagnostico_detalle', '')
    log_text = request.form.get('log_detalle', '')
    
    # Validar que el problema esté especificado
    if not problem_type or problem_type.strip() == '':
        if wants_json:
            return jsonify({'status': 'error', 'message': 'Debe especificar el tipo de problema'}), 400
        flash('Debe especificar el tipo de problema antes de enviar al laboratorio', 'warning')
        return redirect_to_rack(wh, rack)
    
    # Capturar IP del puerto actual (requerido para RMA)
    ip_rma = request.form.get('ip_rma', '').strip()
    log_file = request.files.get('log_file')
    no_enciende = str(request.form.get('no_enciende', '')).strip().lower() in ['1', 'true', 'on', 'si', 'yes']
    
    if not ip_rma:
        if wants_json:
            return jsonify({'status': 'error', 'message': 'Debe ingresar la IP del puerto actual'}), 400
        flash('Debe ingresar la IP del puerto actual', 'warning')
        return redirect_to_rack(wh, rack)

    if not no_enciende and not log_file:
        msg = 'Debe adjuntar archivo .txt del log para RMA'
        if wants_json:
            return jsonify({'status': 'error', 'message': msg}), 400
        flash(msg, 'warning')
        return redirect_to_rack(wh, rack)

    # Validaciones de backend (no depender del frontend)
    sn_digital = (request.form.get('sn_digital') or '').strip()
    mac = (request.form.get('mac') or '').strip()
    ths_raw = (request.form.get('ths') or '').strip()

    if not sn_digital or not mac or not ths_raw or (not no_enciende and not log_text.strip()):
        msg = 'Debe completar SN Digital, MAC, TH/s y Log para enviar RMA'
        if wants_json:
            return jsonify({'status': 'error', 'message': msg}), 400
        flash(msg, 'warning')
        return redirect_to_rack(wh, rack)

    if no_enciende and not log_text.strip():
        log_text = 'NO ENCIENDE'

    try:
        ths_val = float(ths_raw)
        if ths_val <= 0:
            raise ValueError('TH/s inválido')
    except Exception:
        msg = 'TH/s inválido. Debe ser un número mayor a 0'
        if wants_json:
            return jsonify({'status': 'error', 'message': msg}), 400
        flash(msg, 'warning')
        return redirect_to_rack(wh, rack)

    tipo = problem_type.strip().upper()
    if tipo == 'PSU':
        psu_model = (request.form.get('psu_model') or '').strip()
        psu_sn = (request.form.get('psu_sn') or '').strip()
        if not psu_model or not psu_sn:
            msg = 'Para falla PSU debe completar Modelo y SN de la fuente'
            if wants_json:
                return jsonify({'status': 'error', 'message': msg}), 400
            flash(msg, 'warning')
            return redirect_to_rack(wh, rack)
    elif tipo == 'CONTROL BOARD':
        cb_sn = (request.form.get('cb_sn') or '').strip()
        if not cb_sn:
            msg = 'Para falla CONTROL BOARD debe completar SN de control board'
            if wants_json:
                return jsonify({'status': 'error', 'message': msg}), 400
            flash(msg, 'warning')
            return redirect_to_rack(wh, rack)
    elif tipo == 'HASHBOARD':
        hb1 = (request.form.get('hb1_sn') or '').strip()
        hb2 = (request.form.get('hb2_sn') or '').strip()
        hb3 = (request.form.get('hb3_sn') or '').strip()
        if not any([hb1, hb2, hb3]):
            msg = 'Para falla HASHBOARD debe ingresar al menos un SN de placa (HB)'
            if wants_json:
                return jsonify({'status': 'error', 'message': msg}), 400
            flash(msg, 'warning')
            return redirect_to_rack(wh, rack)
    
    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    
    if not minero:
        if wants_json:
            return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404
        flash('Minero no encontrado en la posición especificada', 'danger')
        return redirect_to_rack(wh, rack)

    if not minero.sn_fisica:
        msg = 'El equipo no tiene SN físico registrado. Complete los datos antes de enviar RMA'
        if wants_json:
            return jsonify({'status': 'error', 'message': msg}), 400
        flash(msg, 'warning')
        return redirect_to_rack(wh, rack)

    # Subir log .txt a Google Drive con nombre de SN Digital
    upload_result = {'file_name': '', 'link': ''}
    if not no_enciende:
        drive = GoogleDriveService()
        upload_result = drive.upload_rma_log_txt(log_file, sn_digital)
        if not upload_result.get('ok'):
            msg = upload_result.get('message', 'No se pudo subir el log a Drive')
            if wants_json:
                return jsonify({'status': 'error', 'message': msg}), 400
            flash(msg, 'danger')
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
    minero.proceso_estado = 'en_rma'  # Marcar como RMA enviado
    
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
        'log_drive_file': upload_result.get('file_name', ''),
        'log_drive_link': upload_result.get('link', ''),
        'no_enciende': no_enciende,
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
    app_obj = current_app._get_current_object()
    hilo = threading.Thread(target=tarea_background_rma, args=(app_obj, datos_para_sheets,))
    hilo.start()
    
    # Registrar en historial
    ubicacion_str = format_ubicacion(wh, rack, f, c)
    db.session.add(Movimiento(
        usuario_id=session['user_id'], 
        accion="REGISTRO RMA", 
        referencia_miner=ubicacion_str, 
        datos_nuevos=(
            f"SN: {minero.sn_fisica} -> Falla: {problem_type}. "
            f"Log Drive: {upload_result.get('file_name', '')}"
        )
    ))
    db.session.commit()
    
    # Si es petición AJAX, retornar JSON
    if wants_json:
        return jsonify({
            'status': 'ok',
            'message': f'RMA registrado para {minero.sn_fisica}',
            'miner_id': minero.id,
            'log_drive_link': upload_result.get('link', '')
        })
    
    flash(f'RMA registrado para {minero.sn_fisica}. Para mover el equipo, cree una Solicitud de Traslado.', 'success')
    return redirect_to_rack(wh, rack)

@main_bp.route('/api/mover', methods=['POST'])
@login_required
def mover():
    data = request.json or {}
    wh, rack, f, c = data.get('wh'), data.get('rack'), data.get('f'), data.get('c')
    motivo = data.get('motivo', 'Sin motivo especificado')

    minero = Miner.query.filter_by(warehouse_id=wh, rack_id=rack, fila=f, columna=c).first()
    if not minero:
        return jsonify({'status': 'error', 'message': 'No encontrado'}), 404

    # Guardar datos que vienen del modal para no perderlos
    if 'sn_digital' in data: minero.sn_digital = data['sn_digital']
    if 'mac' in data: minero.mac_address = data['mac']
    db.session.commit()

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

        ubicacion_str = format_ubicacion(wh, rack, f, c)
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="SOLICITUD TRASLADO", 
            referencia_miner=ubicacion_str, 
            datos_nuevos=f"SN: {minero.sn_fisica} -> Solicitud {solicitud.id} enviada a aprobación. Motivo: {motivo}"
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

    return jsonify({'status': 'ok', 'message': 'Solicitud enviada a aprobación del laboratorio'})

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
        
        ubicacion_str = format_ubicacion(wh, rack, f, c)
        db.session.add(Movimiento(
            usuario_id=session['user_id'], 
            accion="RMA CANCELADO", 
            referencia_miner=ubicacion_str, 
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
    if not minero:
        return jsonify({'status': 'error', 'message': 'Minero no encontrado'}), 404

    # Actualizar datos rápidos del form
    if 'sn_digital' in data: minero.sn_digital = data['sn_digital']
    if 'mac' in data: minero.mac_address = data['mac']
    if 'psu_sn' in data: minero.psu_sn = data['psu_sn']
    if 'psu_model' in data: minero.psu_model = data['psu_model']
    if 'cb_sn' in data: minero.cb_sn = data['cb_sn']

    pieza = minero.diagnostico_detalle or 'GENERAL'
    comentario = (minero.log_detalle or '').strip()
    if cant_coolers:
        comentario = f"{comentario} | Coolers dañados: {cant_coolers}" if comentario else f"Coolers dañados: {cant_coolers}"

    try:
        HYDRO_WH_ID = 100
        modelo_lower = (minero.modelo or '').lower()
        es_hydro = any(x in modelo_lower for x in ['hyd', 'm33', 'm53']) or minero.warehouse_id == HYDRO_WH_ID

        if not es_hydro:
            # Conciliación in-situ WH
            from app.models.solicitud_pieza import SolicitudPieza
            solicitud = SolicitudPieza(
                miner_id=minero.id,
                tipo_pieza=pieza,
                ubicacion_reparacion='WH',
                tipo_conciliacion='WH',
                wh_origen=minero.warehouse_id,
                estado='pendiente_aprobacion_lab',
                comentario=comentario,
                solicitante_id=session['user_id']
            )
            db.session.add(solicitud)
            minero.proceso_estado = 'Conciliando'
            db.session.add(Movimiento(
                usuario_id=session['user_id'],
                accion="SOLICITUD CONCILIACIÓN WH",
                referencia_miner=f"{minero.sn_fisica} (WH{minero.warehouse_id}-R{minero.rack_id}-{minero.fila}:{minero.columna})",
                datos_nuevos=f"Pieza: {pieza}. Estado cambiado a Conciliando. {comentario}"
            ))
        else:
            # Conciliación en LAB (Hydro o WH que requiera prueba en lab)
            from app.models.solicitud import SolicitudTraslado
            from app.models.solicitud_pieza import SolicitudPieza

            # Reutilizar traslado pendiente si ya existe para este minero
            traslado = SolicitudTraslado.query.filter(
                SolicitudTraslado.miner_id == minero.id,
                SolicitudTraslado.estado == 'pendiente_lab'
            ).order_by(SolicitudTraslado.fecha_solicitud.desc()).first()

            if not traslado:
                traslado = SolicitudTraslado(
                    miner_id=minero.id,
                    origen_wh=minero.warehouse_id,
                    origen_rack=minero.rack_id,
                    origen_fila=minero.fila,
                    origen_columna=minero.columna,
                    destino='LAB',
                    sector='Hydro' if minero.warehouse_id == HYDRO_WH_ID else 'WH',
                    motivo=f"CONCILIACIÓN LAB: Prueba de pieza {pieza}. {comentario}",
                    solicitante_id=session['user_id'],
                    # Requiere aprobación del Lab y luego Coordinador
                    estado='pendiente_lab'
                )
                db.session.add(traslado)
                db.session.flush()

            solicitud = SolicitudPieza(
                miner_id=minero.id,
                tipo_pieza=pieza,
                ubicacion_reparacion='LAB',
                tipo_conciliacion='LAB',
                solicitud_traslado_id=traslado.id,
                wh_origen=minero.warehouse_id,
                estado='pendiente_aprobacion_lab',
                comentario=comentario,
                solicitante_id=session['user_id']
            )
            db.session.add(solicitud)

            db.session.add(Movimiento(
                usuario_id=session['user_id'],
                accion="SOLICITUD CONCILIACIÓN LAB",
                referencia_miner=f"{minero.sn_fisica}",
                datos_nuevos=f"Pieza: {pieza}. Requiere traslado a LAB para prueba."
            ))

            # Bloquear mientras se procesa el traslado
            minero.proceso_estado = 'pendiente_traslado'

        db.session.commit()
        return jsonify({'status': 'ok', 'message': 'Conciliación registrada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
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



# --- API: INICIAR REPARACIÓN (De Solicitud -> Mesa) ---






# --- API: REINSTALAR EQUIPO (Stock Lab → Warehouse) ---



# --- API PARTIAL: ESTADÍSTICAS EN TIEMPO REAL ---

