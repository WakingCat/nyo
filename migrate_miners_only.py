#!/usr/bin/env python3
"""
Script para crear tabla miners y migrar los datos
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

print("\n🔨 Conectando y creando tabla miners...")

source_engine = create_engine(LOCAL_DB_URI)
dest_engine = create_engine(dest_url)

# Crear tabla Miner específicamente
app = create_app()
with app.app_context():
    # Forzar creación solo de la tabla miners
    Miner.__table__.create(bind=dest_engine, checkfirst=True)
    print("✅ Tabla miners lista.")

# Sesiones
SourceSession = sessionmaker(bind=source_engine)
DestSession = sessionmaker(bind=dest_engine)

source_session = SourceSession()
dest_session = DestSession()

print("📦 Migrando mineros...")
try:
    miners = source_session.query(Miner).all()
    total = len(miners)
    print(f"   📊 Total a migrar: {total}")
    
    count = 0
    for miner in miners:
        dest_session.merge(miner)
        count += 1
        
        # Mostrar progreso cada 1000
        if count % 1000 == 0:
            print(f"   ⏳ Progreso: {count}/{total}...")
    
    print(f"   💾 Confirmando cambios...")
    dest_session.commit()
    print(f"   ✅ {count} mineros migrados exitosamente!")
    
except Exception as e:
    dest_session.rollback()
    print(f"   ❌ Error: {e}")
    sys.exit(1)

print("\n✨ Migración de mineros completada.")
