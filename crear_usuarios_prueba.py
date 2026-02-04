from app import create_app, db
from app.models.user import User, Role
from werkzeug.security import generate_password_hash

def cargar_usuarios_prueba():
    app = create_app()
    with app.app_context():
        # Definición de usuarios (Agregué 'whs' para probar el sidebar)
        usuarios_lista = [
            # WH (Les asignamos WH específicos para probar)
            {'nombre': 'Salvador Santacruz', 'rol': 'Tecnico Operaciones WH', 'email': 'salvador.s@hivetech.com', 'whs': '1,2'},
            {'nombre': 'Bernardo Augusto', 'rol': 'Supervisor WH', 'email': 'bernardo.a@hivetech.com', 'whs': '1,2,3,4'},
            {'nombre': 'Vidal Rojas', 'rol': 'Coordinador WH', 'email': 'vidal.r@hivetech.com', 'whs': '1,2,3,4,5,6,7,8,9,10'},
            
            # HYDRO (Sin WH asignados de aire)
            {'nombre': 'Elias Cabral', 'rol': 'Tecnico Operaciones Hydro', 'email': 'elias.c@hivetech.com', 'whs': None},
            {'nombre': 'Jose Sosa', 'rol': 'Supervisor Hydro', 'email': 'jose.s@hivetech.com', 'whs': None},
            {'nombre': 'Lujan Figueredo', 'rol': 'Coordinador Hydro', 'email': 'lujan.f@hivetech.com', 'whs': None},
            
            # LAB
            {'nombre': 'Celso Colinas', 'rol': 'Tecnico Lab', 'email': 'celso.c@hivetech.com', 'whs': None},
            {'nombre': 'Oscar Fernandez', 'rol': 'Supervisor Lab', 'email': 'oscar.f@hivetech.com', 'whs': None},
            {'nombre': 'Daisy Fernandez', 'rol': 'Coordinador Lab', 'email': 'daisy.f@hivetech.com', 'whs': None},
            
            # DEPOSITO
            {'nombre': 'Rody Esquivel', 'rol': 'Supervisor Deposito', 'email': 'rody.e@hivetech.com', 'whs': None},
            
            # SITE MANAGER (Ve todo, no necesita asignación específica o se le pone todo)
            {'nombre': 'Edilzon Rivas', 'rol': 'Site Manager', 'email': 'edilzon.r@hivetech.com', 'whs': '1,2,3,4,5,6,7,8,9,10'}
        ]

        password_generica = generate_password_hash('hive2026') 

        for u in usuarios_lista:
            rol = Role.query.filter_by(nombre_puesto=u['rol']).first()
            
            if not rol:
                print(f"❌ Error: El rol '{u['rol']}' no existe. ¡CORRE setup_roles.py PRIMERO!")
                continue

            user_existente = User.query.filter_by(email=u['email']).first()
            if not user_existente:
                nuevo_usuario = User(
                    username=u['nombre'],
                    email=u['email'],
                    password_hash=password_generica,
                    role_id=rol.id,
                    wh_asignados=u.get('whs'), # Aquí cargamos sus zonas
                    is_active=True
                )
                db.session.add(nuevo_usuario)
                print(f"✅ Usuario creado: {u['nombre']} - WHs: {u.get('whs')}")
            else:
                print(f"🟡 Usuario ya existe: {u['nombre']}")

        db.session.commit()
        print("\n🔥 Usuarios cargados. Contraseña para todos: hive2026")

if __name__ == "__main__":
    cargar_usuarios_prueba()