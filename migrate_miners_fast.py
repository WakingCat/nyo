#!/usr/bin/env python3
"""
Script OPTIMIZADO para migrar mineros con batch processing
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

print("📦 Migrando mineros con batch processing...", flush=True)
try:
    miners = source_session.query(Miner).all()
    total = len(miners)
    print(f"   📊 Total a migrar: {total}", flush=True)
    
    BATCH_SIZE = 500
    count = 0
    
    for i in range(0, total, BATCH_SIZE):
        batch = miners[i:i+BATCH_SIZE]
        for miner in batch:
            dest_session.merge(miner)
        
        dest_session.flush()  # Flush cada batch
        count += len(batch)
        print(f"   ⏳ Progreso: {count}/{total}...", flush=True)
    
    print(f"   💾 Confirmando cambios...", flush=True)
    dest_session.commit()
    print(f"   ✅ {count} mineros migrados exitosamente!", flush=True)
    
except Exception as e:
    dest_session.rollback()
    print(f"   ❌ Error: {e}", flush=True)
    sys.exit(1)

print("\n✨ Migración completada.", flush=True)
