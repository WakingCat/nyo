#!/usr/bin/env python3
"""
Script ULTRA-RÁPIDO para migrar mineros con bulk insert
Usa bulk_insert_mappings() que es 10-20x más rápido que merge()
"""
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import create_app, db
from app.models.miner import Miner

LOCAL_DB_URI = 'mysql+mysqlconnector://root:root@localhost:3306/hive_mining_db'

dest_url = input("Ingresa la EXTERNAL DATABASE URL de Render (postgresql://...): ").strip()

if not dest_url:
    print("❌ Debes ingresar una URL válida.")
    sys.exit(1)

if dest_url.startswith("postgres://"):
    dest_url = dest_url.replace("postgres://", "postgresql://", 1)

print("\n🔨 Conectando y creando tabla miners...", flush=True)

source_engine = create_engine(LOCAL_DB_URI)
dest_engine = create_engine(dest_url)

# Crear tabla
app = create_app()
with app.app_context():
    Miner.__table__.create(bind=dest_engine, checkfirst=True)
    print("✅ Tabla miners lista.", flush=True)

# Sesiones
SourceSession = sessionmaker(bind=source_engine)
DestSession = sessionmaker(bind=dest_engine)

source_session = SourceSession()
dest_session = DestSession()

print("📦 Migrando mineros con BULK INSERT (ultra-rápido)...", flush=True)
try:
    # Leer todos los mineros de MySQL
    print("   📥 Leyendo datos de MySQL...", flush=True)
    miners = source_session.query(Miner).all()
    total = len(miners)
    print(f"   📊 Total a migrar: {total}", flush=True)
    
    # Convertir a diccionarios (más eficiente que objetos ORM)
    print("   🔄 Preparando datos...", flush=True)
    miner_dicts = []
    for miner in miners:
        miner_dict = {
            'id': miner.id,
            'warehouse_id': miner.warehouse_id,
            'rack_id': miner.rack_id,
            'fila': miner.fila,
            'columna': miner.columna,
            'modelo': miner.modelo,
            'ths': miner.ths,
            'ip_address': miner.ip_address,
            'mac_address': miner.mac_address,
            'sn_fisica': miner.sn_fisica,
            'sn_digital': miner.sn_digital,
            'sn_antiguo': miner.sn_antiguo,
            'garantia_vence': miner.garantia_vence,
            'psu_model': miner.psu_model,
            'psu_sn': miner.psu_sn,
            'cb_sn': miner.cb_sn,
            'hb1_sn': miner.hb1_sn,
            'hb2_sn': miner.hb2_sn,
            'hb3_sn': miner.hb3_sn,
            'proceso_estado': miner.proceso_estado,
            'responsable': miner.responsable,
            'fecha_diagnostico': miner.fecha_diagnostico,
            'diagnostico_detalle': miner.diagnostico_detalle,
            'log_detalle': miner.log_detalle,
            'observaciones': miner.observaciones,
            'fecha_registro': miner.fecha_registro
        }
        miner_dicts.append(miner_dict)
    
    # Bulk insert en batches (para no saturar memoria)
    BATCH_SIZE = 1000
    print(f"   💾 Insertando en batches de {BATCH_SIZE}...", flush=True)
    
    for i in range(0, total, BATCH_SIZE):
        batch = miner_dicts[i:i+BATCH_SIZE]
        dest_session.bulk_insert_mappings(Miner, batch)
        dest_session.commit()  # Commit cada batch
        print(f"   ⚡ Progreso: {min(i+BATCH_SIZE, total)}/{total}...", flush=True)
    
    print(f"   ✅ {total} mineros migrados exitosamente!", flush=True)
    
except Exception as e:
    dest_session.rollback()
    print(f"   ❌ Error: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    source_session.close()
    dest_session.close()

print("\n✨ Migración completada en tiempo récord!", flush=True)
