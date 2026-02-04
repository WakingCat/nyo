import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from app.models.miner import Miner
from app.services.warranty_service import warranty_service
from app.utils.auth_decorators import login_required
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

lab_routes = Blueprint('lab_routes', __name__)

@lab_routes.route('/dashboard/lab/garantias')
@login_required
def garantias():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '')
    estado = request.args.get('estado', 'all')
    
    query = Miner.query
    
    # Filtro de búsqueda
    if q:
        query = query.filter(Miner.sn_fisica.ilike(f'%{q}%'))
        
    # Filtro de estado
    today = datetime.now().date()
    warning_date = today + timedelta(days=30)
    
    if estado == 'vencida':
        query = query.filter(Miner.garantia_vence < today)
    elif estado == 'por_vencer':
        query = query.filter(Miner.garantia_vence >= today, Miner.garantia_vence <= warning_date)
    elif estado == 'activa':
        query = query.filter(Miner.garantia_vence > warning_date)
        
    # Importante: Solo mostrar miners que tienen fecha de garantia seteada si se filtra por estado
    # (Opcional, depende de requerimiento. Si 'all', mostramos todo)
    
    pagination = query.paginate(page=page, per_page=20)
    
    miners_processed = []
    for m in pagination.items:
        est = 'activa'
        if not m.garantia_vence:
            est = 'sin_dato'
        elif m.garantia_vence < today:
            est = 'vencida'
        elif m.garantia_vence <= warning_date:
            est = 'por_vencer'
            
        m.estado_garantia = est
        
        # Determinar ubicación legible
        loc_str = "Desconocida"
        if m.warehouse_id:
            loc_str = f"WH {m.warehouse_id}"
        elif m.proceso_estado in ['en_laboratorio', 'en_reparacion', 'stock_lab']:
            loc_str = "LABORATORIO"
            
        m.ubicacion_str = loc_str
        miners_processed.append(m)
        
    return render_template('lab_warranty_list.html', miners=miners_processed, pagination=pagination)

@lab_routes.route('/dashboard/lab/importar_garantias', methods=['POST'])
@login_required
def importar_garantias():
    if 'file' not in request.files:
        flash('No se subió archivo', 'danger')
        return redirect(url_for('lab_routes.garantias'))
        
    file = request.files['file']
    if file.filename == '':
        flash('Archivo no seleccionado', 'danger')
        return redirect(url_for('lab_routes.garantias'))
        
    if file and file.filename.endswith('.xlsx'):
        filename = secure_filename(file.filename)
        # Guardar temp
        filepath = os.path.join('/tmp', filename)
        file.save(filepath)
        
        result = warranty_service.import_warranties_from_excel(filepath)
        
        if result['status'] == 'ok':
            flash(f"Importación exitosa. {result['updated']} equipos actualizados.", 'success')
            if result['errors']:
                flash(f"Advertencias: {len(result['errors'])} filas omitidas (ver log).", 'warning')
        else:
            flash(f"Error: {result['message']}", 'danger')
            
        return redirect(url_for('lab_routes.garantias'))
    else:
        flash('Formato inválido. Solo .xlsx', 'danger')
        return redirect(url_for('lab_routes.garantias'))
