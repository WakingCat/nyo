
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import create_app, db
from app.models.user import User, Movimiento
from app.models.miner import Miner
from app.models.solicitud import SolicitudTraslado
from app.models.solicitud_pieza import SolicitudPieza
from app.models.diagnostico import Diagnostico
from app.models.inventario_pieza import InventarioPieza, MovimientoPieza as MovimientoPiezaInv
from app.models.pieza_deposito import PiezaDeposito, MovimientoPiezaDeposito

# Configuración
LOCAL_DB_URI = 'mysql+mysqlconnector://root:root@localhost:3306/hive_mining_db'

print("="*60)
print("SCRIPT DE MIGRACIÓN: MySQL Local -> PostgreSQL Render")
print("="*60)

dest_url = input("Ingresa la EXTERNAL DATABASE URL de Render (postgresql://...): ").strip()

if not dest_url:
    print("❌ Debes ingresar una URL válida.")
    sys.exit(1)

# Fix para Render
if dest_url.startswith("postgres://"):
    dest_url = dest_url.replace("postgres://", "postgresql://", 1)

print(f"\n📡 Conectando a DB Destino...")

# Motores (MySQL Local -> Postgres Render)
source_engine = create_engine(LOCAL_DB_URI)
dest_engine = create_engine(dest_url)

# Crear tablas en destino
print("🔨 Creando tablas en destino (si no existen)...")
app = create_app()
app = create_app()
with app.app_context():
    # Usar el bind explícito para crear tablas en la base de datos destino
    try:
        # print("🧹 Limpiando tablas antiguas en destino...")
        # db.metadata.drop_all(bind=dest_engine)
        
        print("🔨 Creando tablas en destino...")
        db.metadata.create_all(bind=dest_engine)
        print("✅ Tablas listas.")
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")
        # Intentamos continuar por si ya existen

# Sesiones
SourceSession = sessionmaker(bind=source_engine)
DestSession = sessionmaker(bind=dest_engine)

source_session = SourceSession()
dest_session = DestSession()

# Función de migración genérica
def migrate_table(Model, name):
    print(f"📦 Migrando {name}...")
    try:
        # dest_session.query(Model).delete() # Opcional: limpiar destino primero
        records = source_session.query(Model).all()
        count = 0
        for r in records:
            dest_session.merge(r)
            count += 1
        
        dest_session.commit()
        print(f"   ✅ {count} registros migrados.")
    except Exception as e:
        dest_session.rollback()
        print(f"   ❌ Error migrando {name}: {e}")

# ORDEN DE MIGRACIÓN
migrate_table(User, "Usuarios")
migrate_table(InventarioPieza, "Inventario de Piezas")
migrate_table(Miner, "Mineros")
migrate_table(PiezaDeposito, "Piezas Depósito")
migrate_table(SolicitudTraslado, "Solicitudes Traslado")
migrate_table(SolicitudPieza, "Solicitudes Pieza")
migrate_table(Diagnostico, "Diagnósticos")
migrate_table(Movimiento, "Movimientos (Logs)")
migrate_table(MovimientoPiezaInv, "Historial Movimiento Piezas Inv")
migrate_table(MovimientoPiezaDeposito, "Historial Movimiento Piezas Dep")

print("\n✨ Migración completada.")
