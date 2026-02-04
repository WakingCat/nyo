from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE mineros ADD COLUMN garantia_vence DATE;"))
            conn.commit()
        print("✅ Columna garantia_vence agregada exitosamente.")
    except Exception as e:
        print(f"ℹ️ Nota: {e}")
