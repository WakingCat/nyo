#!/usr/bin/env python3
"""
Script para arreglar el tamaño de la columna password_hash en PostgreSQL
"""
import sys
from sqlalchemy import create_engine, text

dest_url = input("Ingresa la EXTERNAL DATABASE URL de Render (postgresql://...): ").strip()

if not dest_url:
    print("❌ Debes ingresar una URL válida.")
    sys.exit(1)

# Fix para Render
if dest_url.startswith("postgres://"):
    dest_url = dest_url.replace("postgres://", "postgresql://", 1)

print("\n🔧 Conectando a PostgreSQL...")
engine = create_engine(dest_url)

print("🔧 Alterando columna password_hash a VARCHAR(256)...")
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(256);"))
        conn.commit()
    print("✅ Columna actualizada correctamente.")
except Exception as e:
    print(f"⚠️  Error: {e}")
    print("   (Esto es normal si la columna ya es VARCHAR(256))")
