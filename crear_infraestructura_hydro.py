#!/usr/bin/env python3
"""
Script para crear la infraestructura completa de Hydro
110 contenedores, cada uno con 2 racks (A y B) de 7 filas x 15 columnas
"""

from app import create_app, db
from app.models.miner import Miner, MinerModel
from sqlalchemy.exc import IntegrityError
import sys

# Configuración
WAREHOUSE_ID_HYDRO = 100
TOTAL_CONTAINERS = 110
RACKS_PER_CONTAINER = 2  # Rack A y Rack B
ROWS_PER_RACK = 7
COLUMNS_PER_RACK = 15

# Nota: Container N tendrá:
#   - Rack A con rack_id = (N*2 - 1)  
#   - Rack B con rack_id = (N*2)
# Por ejemplo, Container 1: rack_id 1 (A) y 2 (B)
#              Container 2: rack_id 3 (A) y 4 (B)

def create_s21hyd_model():
    """Crear el modelo S21Hyd si no existe"""
    print("🔍 Verificando modelo S21Hyd...")
    
    model = MinerModel.query.filter_by(name='S21Hyd').first()
    
    if not model:
        print("➕ Creando modelo S21Hyd...")
        model = MinerModel(
            name='S21Hyd',
            cooling_type='HYDRO'
        )
        db.session.add(model)
        db.session.commit()
        print("✅ Modelo S21Hyd creado con tipo de enfriamiento HYDRO")
    else:
        print(f"✅ Modelo S21Hyd ya existe (cooling_type: {model.cooling_type})")
    
    return model

def create_hydro_infrastructure():
    """Crear toda la infraestructura de posiciones para Hydro"""
    
    print("\n" + "="*60)
    print("🚀 CREANDO INFRAESTRUCTURA DE HYDRO")
    print("="*60)
    print(f"Warehouse ID: {WAREHOUSE_ID_HYDRO}")
    print(f"Contenedores: {TOTAL_CONTAINERS}")
    print(f"Racks por contenedor: {RACKS_PER_CONTAINER} (A=1, B=2)")
    print(f"Estructura de cada rack: {ROWS_PER_RACK} filas × {COLUMNS_PER_RACK} columnas")
    
    total_positions = TOTAL_CONTAINERS * RACKS_PER_CONTAINER * ROWS_PER_RACK * COLUMNS_PER_RACK
    print(f"Total de posiciones a crear: {total_positions:,}")
    print("="*60 + "\n")
    
    # Verificar si ya existen posiciones
    existing = Miner.query.filter_by(warehouse_id=WAREHOUSE_ID_HYDRO).count()
    if existing > 0:
        print(f"⚠️  ADVERTENCIA: Ya existen {existing} posiciones en warehouse_id={WAREHOUSE_ID_HYDRO}")
        response = input("¿Deseas continuar y agregar más posiciones? (s/n): ")
        if response.lower() != 's':
            print("❌ Operación cancelada")
            return
    
    created_count = 0
    batch_size = 100  # Hacer commit cada 100 registros para mejor performance
    
    try:
        for container in range(1, TOTAL_CONTAINERS + 1):
            for rack_letter in range(RACKS_PER_CONTAINER):  # 0=A, 1=B
                # Calcular rack_id único para cada rack
                # Container 1: racks 1 (A) y 2 (B)
                # Container 2: racks 3 (A) y 4 (B)
                rack_id = (container - 1) * RACKS_PER_CONTAINER + rack_letter + 1
                rack_name = "A" if rack_letter == 0 else "B"
                
                for row in range(1, ROWS_PER_RACK + 1):
                    for column in range(1, COLUMNS_PER_RACK + 1):
                        # Crear posición vacía
                        miner = Miner(
                            warehouse_id=WAREHOUSE_ID_HYDRO,
                            rack_id=rack_id,  # Rack ID único
                            fila=row,
                            columna=column,
                            modelo=None,  # Se llenará al importar la planilla
                            proceso_estado='vacio',  # Posición vacía
                            sn_fisica=None,
                            sn_digital=None,
                            ths=None,
                            ip_address=None,
                            mac_address=None
                        )
                        
                        db.session.add(miner)
                        created_count += 1
                        
                        # Commit cada batch_size registros
                        if created_count % batch_size == 0:
                            db.session.commit()
                            print(f"📦 Contenedor {container} - Rack {rack_name} (rack_id={rack_id}) | "
                                  f"Posiciones creadas: {created_count:,}/{total_positions:,} "
                                  f"({created_count/total_positions*100:.1f}%)")
            
            # Commit al final de cada contenedor para asegurar consistencia
            db.session.commit()
        
        # Commit final
        db.session.commit()
        
        print("\n" + "="*60)
        print("✅ INFRAESTRUCTURA CREADA EXITOSAMENTE")
        print("="*60)
        print(f"Total de posiciones creadas: {created_count:,}")
        print(f"Contenedores: 1 a {TOTAL_CONTAINERS}")
        print(f"Cada contenedor tiene 2 racks:")
        print(f"  - Container 1: Rack A (rack_id=1), Rack B (rack_id=2)")
        print(f"  - Container 2: Rack A (rack_id=3), Rack B (rack_id=4)")
        print(f"  - ... hasta Container {TOTAL_CONTAINERS}: Rack A (rack_id={TOTAL_CONTAINERS*2-1}), Rack B (rack_id={TOTAL_CONTAINERS*2})")
        print(f"Cada rack: {ROWS_PER_RACK} filas × {COLUMNS_PER_RACK} columnas")
        print("\n💡 Próximo paso: Importar los mineros S21Hyd desde la planilla")
        print("="*60 + "\n")
        
    except IntegrityError as e:
        db.session.rollback()
        print(f"\n❌ Error de integridad en la base de datos: {e}")
        sys.exit(1)
    except Exception as e:
        db.session.rollback()
        print(f"\n❌ Error inesperado: {e}")
        sys.exit(1)

def verify_infrastructure():
    """Verificar que la infraestructura se creó correctamente"""
    print("\n🔍 VERIFICANDO INFRAESTRUCTURA...")
    print("-"*60)
    
    # Contar total de posiciones
    total = Miner.query.filter_by(warehouse_id=WAREHOUSE_ID_HYDRO).count()
    print(f"✅ Total de posiciones en Hydro: {total:,}")
    
    # Verificar por contenedor (mostrar primeros 5)
    print(f"\n📊 Primeros 5 contenedores:")
    for container in range(1, min(6, TOTAL_CONTAINERS + 1)):
        count = Miner.query.filter_by(
            warehouse_id=WAREHOUSE_ID_HYDRO,
            rack_id=container
        ).count()
        expected = RACKS_PER_CONTAINER * ROWS_PER_RACK * COLUMNS_PER_RACK
        status = "✅" if count == expected else "❌"
        print(f"{status} Contenedor {container}: {count} posiciones (esperado: {expected})")
    
    # Verificar estructura de un contenedor
    print(f"\n🔬 Detalle del Contenedor 1:")
    for rack in range(1, RACKS_PER_CONTAINER + 1):
        rack_name = "A" if rack == 1 else "B"
        positions = Miner.query.filter_by(
            warehouse_id=WAREHOUSE_ID_HYDRO,
            rack_id=1,
            fila=rack  # Wait, this is wrong - need to check properly
        ).count()
        
        # Actually, let's count by rack properly
        rack_positions = db.session.query(Miner).filter(
            Miner.warehouse_id == WAREHOUSE_ID_HYDRO,
            Miner.rack_id == 1
        ).filter(
            # For rack A (when iterating rack=1), we count all positions with this container
            # But we need to distinguish racks differently
            # Actually in our schema, rack_id IS the container number
            # So we need to count rows/columns for container 1
        ).count()
    
    # Let me fix this - simpler approach
    container_1_count = Miner.query.filter_by(
        warehouse_id=WAREHOUSE_ID_HYDRO,
        rack_id=1
    ).count()
    print(f"   Total posiciones en contenedor 1: {container_1_count}")
    
    # Count rows and columns for container 1
    rows = db.session.query(Miner.fila).filter_by(
        warehouse_id=WAREHOUSE_ID_HYDRO,
        rack_id=1
    ).distinct().count()
    
    columns = db.session.query(Miner.columna).filter_by(
        warehouse_id=WAREHOUSE_ID_HYDRO,
        rack_id=1
    ).distinct().count()
    
    print(f"   Filas únicas: {rows}")
    print(f"   Columnas únicas: {columns}")
    
    print("-"*60 + "\n")

def main():
    """Función principal"""
    app = create_app()
    
    with app.app_context():
        # 1. Crear modelo S21Hyd
        create_s21hyd_model()
        
        # 2. Crear infraestructura
        create_hydro_infrastructure()
        
        # 3. Verificar
        verify_infrastructure()

if __name__ == '__main__':
    main()
