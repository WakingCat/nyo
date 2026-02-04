from app import create_app, db
from app.models.miner import Miner
from app.models.solicitud import SolicitudTraslado
from app.services.repair_service import repair_service

app = create_app()

with app.app_context():
    miner_id = 62082
    wh = 100
    miner = Miner.query.get(miner_id)
    print(f"Miner State Before: {miner.proceso_estado}, WH: {miner.warehouse_id}")

    # Logic from main.py
    rack = None
    
    last_transfer = SolicitudTraslado.query.filter_by(
        miner_id=miner_id,
        destino='LAB'
    ).order_by(SolicitudTraslado.fecha_solicitud.desc()).first()
    
    if last_transfer:
        print(f"Transfer Found: ID={last_transfer.id}, Origin WH={last_transfer.origen_wh}")
        if last_transfer.origen_wh == 100:
            rack = last_transfer.origen_rack
            fila = last_transfer.origen_fila
            columna = last_transfer.origen_columna
            print(f"Recovered Location: Rack={rack}, Fila={fila}, Col={columna}")
    else:
        print("Transfer NOT found")
        
    if rack:
        # Simulate repair service call
        # Uncomment to actually execute
        # result = repair_service.return_to_warehouse(miner_id, wh, rack, fila, columna)
        print(f"Calling repair_service with: WH={wh}, R={rack}, F={fila}, C={columna}")
        
        # Check occupancy manually first
        ocupante = Miner.query.filter(
            Miner.warehouse_id == wh,
            Miner.rack_id == rack,
            Miner.fila == fila,
            Miner.columna == columna,
            Miner.id != miner_id
        ).first()
        
        if ocupante:
             print(f"OCCUPIED BY: {ocupante.sn_fisica}")
        else:
             print("POSITION FREE")
             
    else:
        print("FAILED to recover location")
