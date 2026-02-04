"""
Servicio de Gestión de Mineros
Centraliza toda la lógica de negocio relacionada con mineros ASIC
"""
from app.models.miner import Miner
from app import db
from sqlalchemy import or_
from typing import Optional, Dict, List, Any


class MinerService:
    """Servicio para operaciones CRUD y búsqueda de mineros"""
    
    @staticmethod
    def get_miner_by_position(wh: int, rack: int, fila: int, columna: int) -> Optional[Miner]:
        """
        Obtiene un minero por su posición exacta en el warehouse
        
        Args:
            wh: ID del warehouse
            rack: ID del rack
            fila: Número de fila
            columna: Número de columna
            
        Returns:
            Objeto Miner o None si no existe
        """
        return Miner.query.filter_by(
            warehouse_id=wh,
            rack_id=rack,
            fila=fila,
            columna=columna
        ).first()
    
    @staticmethod
    def get_miner_by_id(miner_id: int) -> Optional[Miner]:
        """Obtiene un minero por su ID"""
        return Miner.query.get(miner_id)
    
    @staticmethod
    def save_miner_data(wh: int, rack: int, fila: int, columna: int, data: Dict[str, Any]) -> Miner:
        """
        Guarda o actualiza datos de un minero
        
        Args:
            wh, rack, fila, columna: Posición del minero
            data: Diccionario con los datos a guardar
            
        Returns:
            Objeto Miner guardado
        """
        # Buscar si ya existe
        minero = MinerService.get_miner_by_position(wh, rack, fila, columna)
        
        if not minero:
            # Crear nuevo
            minero = Miner(
                warehouse_id=wh,
                rack_id=rack,
                fila=fila,
                columna=columna
            )
        
        # Actualizar campos
        minero.modelo = data.get('modelo', minero.modelo)
        minero.sn_fisica = data.get('sn_fisica', minero.sn_fisica)
        minero.sn_digital = data.get('sn_digital', minero.sn_digital)
        minero.ths = float(data.get('ths', 0)) if data.get('ths') else minero.ths
        minero.ip_address = data.get('ip', minero.ip_address)
        minero.mac_address = data.get('mac', minero.mac_address)
        
        # Componentes internos
        minero.psu_model = data.get('psu_model', minero.psu_model)
        minero.psu_sn = data.get('psu_sn', minero.psu_sn)
        minero.cb_sn = data.get('cb_sn', minero.cb_sn)
        minero.hb1_sn = data.get('hb1_sn', minero.hb1_sn)
        minero.hb2_sn = data.get('hb2_sn', minero.hb2_sn)
        minero.hb3_sn = data.get('hb3_sn', minero.hb3_sn)
        
        # Diagnóstico (si viene)
        if 'diagnostico_detalle' in data:
            minero.diagnostico_detalle = data['diagnostico_detalle']
        if 'log_detalle' in data:
            minero.log_detalle = data['log_detalle']
        
        db.session.add(minero)
        db.session.commit()
        
        return minero
    
    @staticmethod
    def search_miners(query: str) -> List[Dict[str, Any]]:
        """
        Busca mineros por SN físico, IP o MAC address
        
        Args:
            query: Término de búsqueda
            
        Returns:
            Lista de diccionarios con datos de mineros encontrados
        """
        # Búsqueda flexible
        miners = Miner.query.filter(
            or_(
                Miner.sn_fisica.like(f'%{query}%'),
                Miner.ip_address.like(f'%{query}%'),
                Miner.mac_address.like(f'%{query}%')
            )
        ).all()
        
        resultados = []
        for m in miners:
            resultados.append({
                'id': m.id,
                'sn': m.sn_fisica,
                'modelo': m.modelo,
                'wh': m.warehouse_id,
                'rack': m.rack_id,
                'fila': m.fila,
                'columna': m.columna,
                'estado': m.proceso_estado,
                'tipo': 'HYDRO' if 'hydro' in (m.modelo or '').lower() else 'AIRE'
            })
        
        return resultados
    
    @staticmethod
    def get_dashboard_data(wh: int, rack: int) -> Dict[str, Any]:
        """
        Obtiene todos los mineros de un rack para el dashboard
        
        Args:
            wh: Warehouse ID
            rack: Rack ID
            
        Returns:
            Diccionario con mineros organizados por posición
        """
        miners = Miner.query.filter_by(
            warehouse_id=wh,
            rack_id=rack
        ).all()
        
        # Organizar por posición (fila, columna)
        grid = {}
        for m in miners:
            key = f"{m.fila}-{m.columna}"
            grid[key] = {
                'id': m.id,
                'modelo': m.modelo,
                'sn_fisica': m.sn_fisica,
                'ths': m.ths,
                'estado': m.proceso_estado,
                'ip_address': m.ip_address
            }
        
        return grid
    
    @staticmethod
    def get_miners_by_state(estado: str) -> List[Miner]:
        """
        Obtiene mineros filtrados por estado
        
        Args:
            estado: Estado del proceso (ej: 'en_laboratorio', 'operativo')
            
        Returns:
            Lista de objetos Miner
        """
        return Miner.query.filter_by(proceso_estado=estado).all()
    
    @staticmethod
    def validate_miner_data(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Valida los datos de un minero antes de guardar
        
        Args:
            data: Diccionario con datos a validar
            
        Returns:
            Tupla (es_válido, mensaje_error)
        """
        # SN Físico es obligatorio
        if not data.get('sn_fisica'):
            return False, "SN Físico es obligatorio"
        
        # Verificar que SN no esté duplicado
        existing = Miner.query.filter_by(sn_fisica=data['sn_fisica']).first()
        if existing and str(existing.warehouse_id) != str(data.get('wh')):
            # Si existe en otro warehouse, es duplicado
            return False, f"SN {data['sn_fisica']} ya existe en WH{existing.warehouse_id}"
        
        # TH/s debe ser positivo si se provee
        if data.get('ths'):
            try:
                ths_val = float(data['ths'])
                if ths_val < 0 or ths_val > 1000:
                    return False, "TH/s debe estar entre 0 y 1000"
            except ValueError:
                return False, "TH/s debe ser un número válido"
        
        return True, None


# Instancia global para importar
miner_service = MinerService()
