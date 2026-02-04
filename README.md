# N&O Mining Management System

Sistema de gestión de mineros ASIC para operaciones en warehouse y laboratorio.

## 🚀 Características

- **Dashboard de Warehouse**: Visualización de racks con mineros
- **Gestión de RMA**: Flujo completo de reparaciones
- **Laboratorio**: Seguimiento de solicitudes, mesa de trabajo y stock
- **Sistema de Permisos**: Control granular por rol, departamento y warehouse
- **Google Sheets**: Exportación automática de movimientos

## 📋 Requisitos

- Python 3.10+
- MySQL 8.0+
- Node.js (opcional, para desarrollo frontend)

## ⚡ Instalación

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd nyo

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar BD (MySQL)
mysql -u root -p -e "CREATE DATABASE hive_mining_db"

# 5. Ejecutar
python run.py
```

## 🔧 Configuración

Editar `config.py`:

```python
SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://user:pass@localhost/hive_mining_db'
SECRET_KEY = 'tu-clave-secreta'
```

## 📁 Estructura del Proyecto

```
nyo/
├── app/
│   ├── models/          # Modelos SQLAlchemy
│   │   ├── miner.py     # Miner, MinerModel
│   │   └── user.py      # User, Role, Movimiento
│   ├── routes/          # Blueprints Flask
│   │   ├── main.py      # Rutas principales
│   │   ├── auth.py      # Autenticación
│   │   └── api.py       # APIs JSON
│   ├── services/        # Lógica de negocio
│   │   ├── miner_service.py
│   │   ├── movement_service.py
│   │   ├── repair_service.py
│   │   └── sheets_service.py
│   ├── utils/           # Utilidades
│   │   ├── auth_decorators.py
│   │   └── permission_decorators.py
│   ├── templates/       # Jinja2
│   └── static/          # CSS, JS
├── migrations/          # Scripts SQL
├── config.py
├── run.py
└── requirements.txt
```

## 👥 Roles del Sistema

| Rol | Acceso WH | Acceso Lab | Monitor |
|-----|-----------|------------|---------|
| Técnico WH | Solo asignados | ❌ | ❌ |
| Técnico Lab | ❌ | ✅ | ❌ |
| Supervisor | Solo asignados | Depende | ✅ |
| Coordinador | ✅ Todos | ✅ | ✅ |
| Site Manager | ✅ Todos | ✅ | ✅ |

## 🔄 Flujo de RMA

1. **Warehouse** → Detectar falla → Enviar a RMA
2. **Lab Solicitudes** → Recibir equipo
3. **Mesa de Trabajo** → Reparar
4. **Stock Lab** → Listo para reinstalar
5. O → **Cementerio** (baja definitiva)

## 🛠️ Tecnologías

- **Backend**: Flask, SQLAlchemy
- **Frontend**: Bootstrap 5, HTMX
- **Base de Datos**: MySQL
- **Integraciones**: Google Sheets (gspread)

## 📊 APIs Principales

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/buscar` | GET | Buscar mineros |
| `/api/get_miner/<wh>/<rack>/<f>/<c>` | GET | Obtener minero |
| `/api/guardar` | POST | Guardar minero |
| `/api/rma/enviar_y_exportar` | POST | Enviar a RMA |
| `/api/lab/iniciar` | POST | Iniciar reparación |
| `/api/lab/terminar` | POST | Finalizar reparación |

## 🧪 Testing

```bash
# Ejecutar tests
source venv/bin/activate
python -m pytest tests/ -v
```

## 📝 Licencia

Uso interno - N&O Tech
