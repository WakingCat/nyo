#!/usr/bin/env python3
"""
Script para migrar piezas del depósito desde MySQL a PostgreSQL
"""
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import create_app, db
from app.models.pieza_deposito import PiezaDeposito

LOCAL_DB_URI = 'mysql+mysqlconnector://root:root@localhost:3306/hive_mining_db'

dest_url = input("Ingresa la EXTERNAL DATABASE URL de Render (postgresql://...): ").strip()

if not dest_url:
    print("❌ Debes ingresar una URL válida.")
    sys.exit(1)

if dest_url.startswith("postgres://"):
    dest_url = dest_url.replace("postgres://", "postgresql://", 1)

print("\n🔨 Conectando y creando tabla piezas_deposito...", flush=True)

source_engine = create_engine(LOCAL_DB_URI)
dest_engine = create_engine(dest_url)

# Crear tabla
app = create_app()
with app.app_context():
    PiezaDeposito.__table__.create(bind=dest_engine, checkfirst=True)
    print("✅ Tabla piezas_deposito lista.", flush=True)

# Sesiones
SourceSession = sessionmaker(bind=source_engine)
DestSession = sessionmaker(bind=dest_engine)

source_session = SourceSession()
dest_session = DestSession()

print("📦 Migrando piezas del depósito con BULK INSERT...", flush=True)
try:
    # Limpiar registros anteriores (en caso de re-run)
    print("   🧹 Limpiando registros anteriores...", flush=True)
    dest_session.query(PiezaDeposito).delete()
    dest_session.commit()
    
    print("   📥 Leyendo datos de MySQL...", flush=True)
    piezas = source_session.query(PiezaDeposito).all()
    total = len(piezas)
    print(f"   📊 Total a migrar: {total}", flush=True)
    
    if total == 0:
        print("   ⚠️ No hay piezas para migrar.", flush=True)
        sys.exit(0)
    
    print("   🔄 Preparando datos...", flush=True)
    pieza_dicts = []
    for pieza in piezas:
        pieza_dict = {
            'id': pieza.id,
            'sn': pieza.sn,
            'tipo': pieza.tipo,
            'modelo_equipo': pieza.modelo_equipo,
            'modelo_pieza': pieza.modelo_pieza,
            'ubicacion': pieza.ubicacion,
            'caja_numero': pieza.caja_numero,
            'pallet_numero': pieza.pallet_numero,
            'estante': pieza.estante,
            'es_reparado': pieza.es_reparado,
            'estado': pieza.estado,
            'notas': pieza.notas,
            'fecha_ingreso': pieza.fecha_ingreso,
            'fecha_salida': pieza.fecha_salida,
            'registrado_por': pieza.registrado_por,
            'ultima_modificacion': pieza.ultima_modificacion,
            'modificado_por': pieza.modificado_por,
            'solicitud_id': None  # Ignoramos la referencia para evitar FK error
        }
        pieza_dicts.append(pieza_dict)
    
    BATCH_SIZE = 500
    print(f"   💾 Insertando en batches de {BATCH_SIZE}...", flush=True)
    
    for i in range(0, total, BATCH_SIZE):
        batch = pieza_dicts[i:i+BATCH_SIZE]
        dest_session.bulk_insert_mappings(PiezaDeposito, batch)
        dest_session.commit()
        print(f"   ⚡ Progreso: {min(i+BATCH_SIZE, total)}/{total}...", flush=True)
    
    print(f"   ✅ {total} piezas del depósito migradas exitosamente!", flush=True)
    
except Exception as e:
    dest_session.rollback()
    print(f"   ❌ Error: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    source_session.close()
    dest_session.close()

print("\n✨ Migración de depósito completada!", flush=True)
