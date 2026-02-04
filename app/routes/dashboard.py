"""
Dashboard Routes
Vistas de dashboards para diferentes roles y departamentos
"""
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app import db
from app.utils.auth_decorators import login_required
from app.utils.permission_decorators import (
    department_required,
    warehouse_permission_required,
    supervisor_or_admin_required,
)
from app.services.miner_service import miner_service
from app.services.repair_service import repair_service
from app.models.miner import Miner
from app.models.user import Movimiento

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Redirige al dashboard apropiado según el rol del usuario"""
    user_role = session.get('role', '')
    user_dept = session.get('depto', '')
    
    # Site Manager -> Dashboard Site Manager
    if 'Site Manager' in user_role:
        return redirect(url_for('dashboard.coordinador'))
    
    # Coordinadores -> Dashboard Coordinador
    elif 'Coordinador' in user_role:
        return redirect(url_for('dashboard.coordinador'))
    
    # Personal de Lab -> Lab Hub
    elif user_dept == 'Lab' or 'Lab' in user_role:
        return redirect(url_for('lab.dashboard'))
    
    # Personal de Depósito -> Dashboard Depósito
    elif user_dept == 'Deposito' or 'Deposito' in user_role:
        return redirect(url_for('deposito.dashboard'))
    
    # Personal de Hydro -> Dashboard Hydro
    elif user_dept == 'Hydro' or 'Hydro' in user_role:
        return redirect(url_for('dashboard.hydro'))
    
    # Técnicos y Supervisores WH -> Dashboard Técnico
    else:
        return redirect(url_for('dashboard.tecnico'))


@dashboard_bp.route('/wh/<int:wh>/<int:rack>')
@login_required
@warehouse_permission_required()
def warehouse(wh, rack):
    """Dashboard de warehouse - Solo usuarios con acceso a ese WH"""
    HYDRO_WH_ID = 100
    
    # REDIRECCIÓN AUTOMÁTICA: Si es Hydro (wh=100), redirigir al contenedor correcto
    if wh == HYDRO_WH_ID:
        container_num = (rack + 1) // 2
        return redirect(url_for('dashboard.hydro_container', container=container_num, rack=rack))
    
    mineros_db = Miner.query.filter_by(warehouse_id=wh, rack_id=rack).all()
    datos_matriz = {(m.fila, m.columna): m for m in mineros_db}
    
    pendientes = Miner.query.filter_by(
        warehouse_id=wh, 
        proceso_estado='pendiente_colocacion'
    ).all()
    
    return render_template('wh_dashboard.html', 
                          wh_actual=wh, 
                          rack_actual=rack, 
                          datos=datos_matriz,
                          pendientes=pendientes)

@dashboard_bp.route('/wh/<int:wh>/pendientes-partial')
@login_required
@warehouse_permission_required()
def pendientes_partial(wh):
    """Partial HTMX para actualización automática de pendientes de colocación"""
    pendientes = Miner.query.filter_by(
        warehouse_id=wh, 
        proceso_estado='pendiente_colocacion'
    ).all()
    
    return render_template('partials/pendientes_colocacion.html', 
                          pendientes=pendientes,
                          wh_actual=wh)


@dashboard_bp.route('/resumen')
@login_required
@supervisor_or_admin_required()
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


@dashboard_bp.route('/coordinador')
@login_required
@supervisor_or_admin_required()
def coordinador():
    """Dashboard personalizado para Coordinadores y Site Managers"""
    from app.services.transfer_service import transfer_service
    from app.services.user_service import user_service
    
    contadores = transfer_service.get_pending_count_by_sector()
    stats_lab = repair_service.get_dashboard_stats()
    
    movimientos_recientes = Movimiento.query.order_by(
        Movimiento.fecha_hora.desc()
    ).limit(10).all()
    
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


@dashboard_bp.route('/tecnico')
@login_required
def tecnico():
    """Dashboard personalizado para Técnicos de WH"""
    from app.models.solicitud import SolicitudTraslado
    
    mis_wh = session.get('mis_wh', [])
    
    mis_solicitudes = SolicitudTraslado.query.filter_by(
        solicitante_id=session.get('user_id')
    ).order_by(SolicitudTraslado.fecha_solicitud.desc()).limit(5).all()
    
    return render_template('dashboard_tecnico.html',
                          mis_warehouses=mis_wh,
                          mis_solicitudes=mis_solicitudes)


@dashboard_bp.route('/hydro')
@login_required
@department_required('Hydro')
def hydro():
    """Dashboard personalizado para Técnicos de Hydro"""
    from app.models.solicitud import SolicitudTraslado
    
    HYDRO_WH_ID = 100
    
    mis_solicitudes = SolicitudTraslado.query.filter_by(
        solicitante_id=session.get('user_id')
    ).order_by(SolicitudTraslado.fecha_solicitud.desc()).limit(5).all()
    
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


@dashboard_bp.route('/hydro/container/<int:container>')
@login_required
@department_required('Hydro')
def hydro_container(container):
    """Vista de un contenedor específico de Hydro"""
    HYDRO_WH_ID = 100
    
    if container < 1 or container > 110:
        flash('Contenedor no válido', 'danger')
        return redirect(url_for('dashboard.hydro'))
    
    rack_a_id = (container - 1) * 2 + 1
    rack_b_id = (container - 1) * 2 + 2
    
    rack_actual = request.args.get('rack', rack_a_id, type=int)
    
    if rack_actual not in [rack_a_id, rack_b_id]:
        rack_actual = rack_a_id
    
    mineros_db = Miner.query.filter_by(
        warehouse_id=HYDRO_WH_ID, 
        rack_id=rack_actual
    ).all()
    
    datos_matriz = {(m.fila, m.columna): m for m in mineros_db}
    
    pendientes = Miner.query.filter(
        Miner.warehouse_id == HYDRO_WH_ID, 
        Miner.proceso_estado == 'pendiente_colocacion',
        Miner.rack_id.in_([rack_a_id, rack_b_id])
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


@dashboard_bp.route('/api/hydro/colocar', methods=['POST'])
@login_required
@department_required('Hydro')
def hydro_colocar():
    """API para colocar un minero pendiente en una posición específica de Hydro"""
    try:
        miner_id = request.form.get('id')
        wh = request.form.get('wh')
        rack = request.form.get('rack')
        fila = request.form.get('fila')
        columna = request.form.get('columna')
        
        if not all([miner_id, wh, rack, fila, columna]):
            flash('Faltan datos para la colocación', 'danger')
            container = (int(request.form.get('rack', 1)) + 1) // 2
            return redirect(url_for('dashboard.hydro_container', container=container))

        # Verificar ocupante
        ocupante = Miner.query.filter_by(
            warehouse_id=wh,
            rack_id=rack,
            fila=fila,
            columna=columna
        ).first()
        
        if ocupante and str(ocupante.id) != str(miner_id):
            flash(f'Posición ocupada por {ocupante.sn_fisica}', 'warning')
            container = (int(rack) + 1) // 2
            return redirect(url_for('dashboard.hydro_container', container=container))
            
        # Actualizar minero
        minero = Miner.query.get(int(miner_id))
        
        if minero:
            minero.warehouse_id = int(wh)
            minero.rack_id = int(rack)
            minero.fila = int(fila)
            minero.columna = int(columna)
            minero.proceso_estado = 'operativo'
            
            try:
                mov = Movimiento(
                    usuario_id=session['user_id'],
                    accion="COLOCACION_HYDRO",
                    referencia_miner=f"SN: {minero.sn_fisica}",
                    datos_nuevos=f"Colocado en C{(int(rack)+1)//2} R{rack} F{fila} C{columna}"
                )
                db.session.add(mov)
                db.session.commit()
            except Exception as em:
                # Si falla el historial, intentar guardar al menos el minero
                try:
                    db.session.commit()
                except:
                    pass

            flash('Minero colocado exitosamente', 'success')
            
        container = (int(rack) + 1) // 2
        return redirect(url_for('dashboard.hydro_container', container=container, rack=rack))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al colocar: {str(e)}', 'danger')
        return redirect(url_for('dashboard.hydro'))


@dashboard_bp.route('/monitor')
@login_required
@supervisor_or_admin_required()
def monitor():
    """Monitor de historial - Solo para supervisores+"""
    historial = Movimiento.query.order_by(Movimiento.fecha_hora.desc()).limit(50).all()
    return render_template('admin/monitor.html', historial=historial)
