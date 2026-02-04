import gspread
from app import create_app, db
from app.models.miner import Miner
from datetime import datetime
import sys

def migrar_desde_google():
    app = create_app()
    with app.app_context():
        print("🔌 Conectando con Google Sheets...")
        try:
            gc = gspread.service_account(filename='credentials.json')
            sh = gc.open_by_key('1U7oMiVMWaBqBcxIzhdJdzKO4-LoME_gyAiMsw6nJDE0')
            worksheet = sh.worksheet("DATA")
        except Exception as e:
            print(f"❌ Error al conectar: {e}")
            return

        print("📥 Descargando datos...")
        try:
            registros = worksheet.get_all_records()
        except Exception as e:
            print(f"❌ Error al leer registros: {e}")
            return

        total_registros = len(registros)
        print(f"✅ Detectadas {total_registros} filas. Procesando...")
        
        count = 0
        updated_sn = 0
        created = 0
        moved = 0
        
        for i, row in enumerate(registros):
            try:
                # 1. Parsing de Ubicación
                raw_wh = row.get('WH')
                raw_cont = row.get('Contenedor')
                raw_rack = row.get('Rack') # Puede ser 'A', 'B', '1', ...
                raw_fila = row.get('Fila')
                
                wh_id = None
                rack_id = 0
                fila = 0
                columna = int(row.get('Columna', 0)) if row.get('Columna') else 0

                # A. Lógica HYDRO (Si hay Contenedor)
                # Validar que raw_cont no sea solo espacios
                if raw_cont and str(raw_cont).strip(): 
                    wh_id = 100 
                    try:
                        container_num = int(raw_cont)
                        
                        raw_rack_str = str(raw_rack).strip().upper() if raw_rack else ''
                        
                        # Si Fila es " " o vacia, ser cero
                        fila_val_str = str(raw_fila).strip() if raw_fila else '0'
                        if not fila_val_str.replace('-','').isdigit(): fila_val_str = '0'
                        
                        if raw_rack_str == 'A' or (raw_rack_str != 'X' and raw_rack_str != 'B' and int(fila_val_str) <= 7):
                            rack_id = (container_num - 1) * 2 + 1
                            fila = int(fila_val_str)
                        else:
                            rack_id = (container_num - 1) * 2 + 2
                            val_fila = int(fila_val_str)
                            if val_fila > 7:
                                fila = val_fila - 7
                            else:
                                fila = val_fila 
                    except ValueError:
                         # Si falla conversion (ej Contenedor='A'), saltar
                         print(f"Error parsing Hydro location row {i}")
                         continue 

                # B. Lógica WAREHOUSE NORMAL / DEPOSITO
                elif raw_wh and str(raw_wh).strip():
                    wh_str = str(raw_wh).strip()
                    # Manejo de DEPOSITO ('Dep')
                    if wh_str.lower().startswith('dep'):
                        wh_id = None
                        # Marcaremos como 'en_deposito' más adelante
                    else:
                        try:
                            wh_id = int(wh_str)
                        except ValueError:
                            # Si falla conversión (ej: '2o'), saltar esta fila o loguear
                            print(f"Advertencia: WH inválido '{raw_wh}' en fila {i+2}")
                            continue

                    try:
                        rack_id = int(str(raw_rack).strip()) if raw_rack and str(raw_rack).strip().isdigit() else 0
                    except: rack_id = 0
                    
                    try:
                        fila = int(str(raw_fila).strip()) if raw_fila and str(raw_fila).strip().isdigit() else 0
                    except: fila = 0

                # Si wh_id es None pero NO es Deposito (ej: fila vacía), saltar
                if wh_id is None and not (raw_wh and str(raw_wh).strip().lower().startswith('dep')):
                    continue

                # 2. Parsing de Datos
                sn_val = str(row.get('SN', '')).strip()
                # Filtrar valores no válidos de SN para tratarlos como vacíos
                if sn_val.upper() in ['X', '', 'None', 'N/A']:
                    sn_val = None
                    es_bloqueado = (str(row.get('SN', '')).strip().upper() == 'X')
                else:
                    es_bloqueado = False

                # 3. Lógica de UPSERT
                
                # A) Si hay un SN válido -> El Rey es el SN
                if sn_val:
                    # Buscar por SN (Donde esté)
                    target_miner = Miner.query.filter_by(sn_fisica=sn_val).first()
                    
                    # Buscar ocupante actual del sitio
                    occupant = Miner.query.filter_by(
                        warehouse_id=wh_id, rack_id=rack_id, fila=fila, columna=columna
                    ).first()

                    # Si hay alguien en el sitio Y no soy yo -> DESALOJAR (Evict)
                    if occupant and (not target_miner or occupant.id != target_miner.id):
                        # Desalojamos al ocupante anterior a "Sin Ubicación"
                        # para evitar colisión de ubicación
                        occupant.warehouse_id = None
                        occupant.rack_id = None
                        occupant.fila = None
                        occupant.columna = None
                        # No borramos, solo desalojamos
                        db.session.add(occupant)
                        # FLUSH para liberar la posición INMEDIATAMENTE y evitar error de unicidad
                        db.session.flush()
                    
                    if target_miner:
                        # EXISTE: Actualizar ubicación y datos
                        updated_sn += 1
                        target_miner.warehouse_id = wh_id
                        target_miner.rack_id = rack_id
                        target_miner.fila = fila
                        target_miner.columna = columna
                    else:
                        # NO EXISTE: Crear nuevo
                        created += 1
                        target_miner = Miner(
                            sn_fisica=sn_val,
                            warehouse_id=wh_id,
                            rack_id=rack_id,
                            fila=fila,
                            columna=columna
                        )
                    
                    # Actualizar resto de campos
                    target_miner.modelo = str(row.get('Modelo', '')).strip()
                    target_miner.ip_address = str(row.get('IP', '')).strip() or None
                    target_miner.mac_address = str(row.get('MAC', '')).strip() or None
                    
                    # Estado: Si vino de Deposito
                    if raw_wh and str(raw_wh).strip().lower().startswith('dep'):
                        target_miner.proceso_estado = 'en_deposito'
                    else:
                        target_miner.proceso_estado = 'operativo'

                    try:
                        # La columna exacta tiene un espacio al final: 'Hash Teorico '
                        hash_val = row.get('Hash Teorico ') or row.get('Hash Teorico') or 0
                        hash_str = str(hash_val).strip().upper()
                        # Si es 'X' o vacío, asignar 0.0
                        if hash_str == 'X' or hash_str == '':
                            target_miner.ths = 0.0
                        else:
                            # Manejar formato "358 TH/s" extrayendo solo el número
                            if 'TH' in hash_str:
                                # Extraer la parte numérica antes de TH
                                hash_num_str = hash_str.split('TH')[0].strip()
                                target_miner.ths = float(hash_num_str)
                            else:
                                target_miner.ths = float(hash_val)
                    except:
                        target_miner.ths = 0.0

                    # Garantía
                    garantia_str = str(row.get('Warranty', '')).strip()
                    if garantia_str:
                        try:
                            target_miner.garantia_vence = datetime.strptime(garantia_str, '%d/%m/%Y').date()
                        except ValueError:
                            try:
                                target_miner.garantia_vence = datetime.strptime(garantia_str, '%Y-%m-%d').date()
                            except: pass

                    db.session.add(target_miner)

                # B) Si NO hay SN (Vacio o Bloqueado)
                else:
                    # Buscar ocupante
                    occupant = Miner.query.filter_by(
                         warehouse_id=wh_id, rack_id=rack_id, fila=fila, columna=columna
                    ).first()
                    
                    if occupant:
                        if occupant.sn_fisica:
                            # Era un minero real -> DESALOJAR
                            occupant.warehouse_id = None
                            occupant.rack_id = None
                            occupant.fila = None
                            occupant.columna = None
                            db.session.add(occupant)
                            db.session.flush() # Liberar posición
                            # NO crear placeholder - dejar vacío
                        else:
                            # Era un placeholder (vacio/bloqueado)
                            # Si posición vacía -> ELIMINAR placeholder
                            if not es_bloqueado:
                                db.session.delete(occupant)
                            # Si es bloqueado -> Mantener/actualizar placeholder
                            # (Ya no creamos bloqueados, solo mantenemos existentes)
                    # Si no hay ocupante y posición vacía -> No hacer nada (dejar vacío)

                count += 1
                if count % 500 == 0:
                    db.session.commit()
                    sys.stdout.write(f"\rProcesados: {count}/{total_registros} (Upd: {updated_sn}, New: {created})")
                    sys.stdout.flush()

            except Exception as e_row:
                db.session.rollback()
                print(f"Error en fila {i}: {e_row}")
                continue

        db.session.commit()
        print(f"\n✅ Finalizado. Procesados: {count}")
        print(f"   - Actualizados (SN Existente): {updated_sn}")
        print(f"   - Creados (SN Nuevo): {created}")

if __name__ == "__main__":
    migrar_desde_google()