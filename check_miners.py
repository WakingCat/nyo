#!/usr/bin/env python3
"""Script para verificar cuántos mineros hay en PostgreSQL"""
import sys
from sqlalchemy import create_engine, text

dest_url = input("Ingresa la EXTERNAL DATABASE URL de Render (postgresql://...): ").strip()

if not dest_url:
    print("❌ Debes ingresar una URL válida.")
    sys.exit(1)

if dest_url.startswith("postgres://"):
    dest_url = dest_url.replace("postgres://", "postgresql://", 1)

print("\n🔍 Conectando a PostgreSQL...")
engine = create_engine(dest_url)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM miners;"))
        count = result.scalar()
        print(f"✅ Mineros en base de datos: {count}")
        
        # Ver algunos ejemplos
        if count > 0:
            result = conn.execute(text("SELECT id, sn, wh, columna, fila FROM miners LIMIT 5;"))
            print("\n📋 Primeros 5 mineros:")
            for row in result:
                print(f"   ID={row[0]}, SN={row[1]}, WH={row[2]}, Col={row[3]}, Fila={row[4]}")
except Exception as e:
    print(f"❌ Error: {e}")
