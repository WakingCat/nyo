from app import create_app, db
from app.models.user import Role

def crear_roles():
    app = create_app()
    with app.app_context():
        # Lista de roles basada en tu estructura
        roles = [
            # Nivel 1: Técnicos
            {'nombre': 'Tecnico Operaciones WH', 'depto': 'Operaciones'},
            {'nombre': 'Tecnico Operaciones Hydro', 'depto': 'Operaciones'},
            {'nombre': 'Tecnico Lab', 'depto': 'Laboratorio'},
            
            # Nivel 2: Supervisores
            {'nombre': 'Supervisor WH', 'depto': 'Operaciones'},
            {'nombre': 'Supervisor Hydro', 'depto': 'Operaciones'},
            {'nombre': 'Supervisor Lab', 'depto': 'Laboratorio'},
            {'nombre': 'Supervisor Deposito', 'depto': 'Logistica'},
            
            # Nivel 3: Jefes
            {'nombre': 'Coordinador WH', 'depto': 'Operaciones'},
            {'nombre': 'Coordinador Hydro', 'depto': 'Operaciones'},
            {'nombre': 'Coordinador Lab', 'depto': 'Laboratorio'},
            {'nombre': 'Site Manager', 'depto': 'Gerencia'}
        ]

        for r in roles:
            existe = Role.query.filter_by(nombre_puesto=r['nombre']).first()
            if not existe:
                nuevo_rol = Role(nombre_puesto=r['nombre'], departamento=r['depto'])
                db.session.add(nuevo_rol)
                print(f"✅ Rol creado: {r['nombre']}")
            else:
                print(f"🟡 Rol ya existe: {r['nombre']}")

        db.session.commit()
        print("\n🔥 Roles sincronizados.")

if __name__ == "__main__":
    crear_roles()