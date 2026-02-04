# --- API: REINSTALAR EQUIPO (Stock Lab → Warehouse) ---
@main_bp.route('/api/lab/reinstalar', methods=['POST'])
@login_required
@lab_technician_required()
def reinstalar_equipo():
    """Reinstala un equipo del stock lab a un warehouse"""
    data = request.json
    
    miner_id = data.get('id')
    wh = data.get('wh')
    rack = data.get('rack')
    fila = data.get('fila')
    columna = data.get('columna')
    
    # Validar datos
    if not all([miner_id, wh, rack, fila, columna]):
        return jsonify({'status': 'error', 'message': 'Datos incompletos'}), 400
    
    # Usar servicio
    success = repair_service.return_to_warehouse(
        int(miner_id),
        int(wh),
        int(rack),
        int(fila),
        int(columna)
    )
    
    if success:
        # Log del movimiento
        minero = Miner.query.get(miner_id)
        db.session.add(Movimiento(
            usuario_id=session['user_id'],
            accion="REINSTALACIÓN",
            referencia_miner=f"SN: {minero.sn_fisica}",
            datos_nuevos=f"Reinstalado en WH{wh}-R{rack}-F{fila}-C{columna}"
        ))
        db.session.commit()
        
        return jsonify({'status': 'ok', 'message': 'Equipo reinstalado exitosamente'})
    
    return jsonify({'status': 'error', 'message': 'Error al reinstalar'}), 400
