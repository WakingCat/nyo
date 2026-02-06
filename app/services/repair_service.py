"""
Servicio de Reparaciones del Laboratorio
Gestiona el flujo: Solicitudes → Mesa de Trabajo → Stock Lab → Cementerio
"""
from app.models.miner import Miner
from app import db
from datetime import datetime
from typing import List, Dict, Any


class RepairService:
    """Servicio para flujo de reparaciones en laboratorio"""
    
    @staticmethod
    def get_lab_stats() -> Dict[str, int]:
        """
        Obtiene estadísticas del laboratorio
        
        Returns:
            Diccionario con contadores de cada estado
        """
        stats = {
            'c_pendientes': Miner.query.filter_by(proceso_estado='en_laboratorio').count(),
            'c_reparacion': Miner.query.filter_by(proceso_estado='en_reparacion').count(),
            'c_stock': Miner.query.filter_by(proceso_estado='stock_lab').count(),
            'c_scrap': Miner.query.filter(
                Miner.proceso_estado.in_(['baja_definitiva', 'donante_piezas'])
            ).count()
        }
        return stats
    
    @staticmethod
    def get_pending_requests() -> List[Miner]:
        """
        Obtiene solicitudes pendientes (recién llegados al lab)
        
        Returns:
            Lista de mineros en estado 'en_laboratorio'
        """
        return Miner.query.filter_by(proceso_estado='en_laboratorio').all()
    
    @staticmethod
    def get_in_repair() -> List[Miner]:
        """
        Obtiene equipos en mesa de trabajo
        
        Returns:
            Lista de mineros en estado 'en_reparacion'
        """
        return Miner.query.filter_by(proceso_estado='en_reparacion').all()
    
    @staticmethod
    def get_stock_lab(sector=None):
        """
        Obtiene equipos en stock listos para reinstalar
        
        Args:
            sector: 'WH', 'Hydro' o None para todos
            
        Returns:
            Lista de mineros en estado 'stock_lab'
        """
        from sqlalchemy import or_
        
        query = Miner.query.filter_by(proceso_estado='stock_lab')
        
        if sector:
            # Filtrar por modelo según sector
            if sector == 'Hydro':
                query = query.filter(
                    or_(
                        Miner.modelo.like('%hyd%'),
                        Miner.modelo.like('%M33%'),
                        Miner.modelo.like('%M53%')
                    )
                )
            elif sector == 'WH':
                query = query.filter(
                    ~or_(
                        Miner.modelo.like('%hyd%'),
                        Miner.modelo.like('%M33%'),
                        Miner.modelo.like('%M53%')
                    )
                )
        
        return query.order_by(Miner.fecha_diagnostico.desc()).all()
    
    @staticmethod
    def get_cemetery() -> List[Miner]:
        """
        Obtiene equipos dados de baja o donantes
        
        Returns:
            Lista de mineros en cementerio
        """
        return Miner.query.filter(
            Miner.proceso_estado.in_(['baja_definitiva', 'donante_piezas'])
        ).all()
    
    @staticmethod
    def start_repair(miner_id: int) -> bool:
        """
        Mueve un minero de solicitudes a mesa de trabajo
        
        Args:
            miner_id: ID del minero
            
        Returns:
            True si fue exitoso
        """
        minero = Miner.query.get(miner_id)
        if not minero or minero.proceso_estado != 'en_laboratorio':
            return False
        
        minero.proceso_estado = 'en_reparacion'
        db.session.commit()
        
        return True
    
    @staticmethod
    def finish_repair(miner_id: int, solucion: str = '') -> bool:
        """
        Marca una reparación como exitosa y mueve a Stock Lab
        
        Args:
            miner_id: ID del minero
            solucion: Descripción de la solución aplicada
            
        Returns:
            True si fue exitoso
        """
        minero = Miner.query.get(miner_id)
        if not minero or minero.proceso_estado != 'en_reparacion':
            return False
        
        minero.proceso_estado = 'stock_lab'
        
        # Guardar solución en observaciones
        if solucion:
            observacion_nueva = f"[{datetime.now().strftime('%Y-%m-%d')}] {solucion}"
            if minero.observaciones:
                minero.observaciones += f"\n{observacion_nueva}"
            else:
                minero.observaciones = observacion_nueva
        
        db.session.commit()
        
        return True
    
    @staticmethod
    def scrap_miner(miner_id: int, tipo: str, motivo: str = '') -> bool:
        """
        Da de baja un minero (cementerio)
        
        Args:
            miner_id: ID del minero
            tipo: 'baja_definitiva' o 'donante_piezas'
            motivo: Razón de la baja
            
        Returns:
            True si fue exitoso
        """
        minero = Miner.query.get(miner_id)
        if not minero:
            return False
        
        # Validar tipo
        if tipo not in ['baja_definitiva', 'donante_piezas']:
            tipo = 'baja_definitiva'
        
        minero.proceso_estado = tipo
        
        # Agregar motivo a observaciones
        if motivo:
            observacion_baja = f"[BAJA {datetime.now().strftime('%Y-%m-%d')}] {motivo}"
            if minero.observaciones:
                minero.observaciones += f"\n{observacion_baja}"
            else:
                minero.observaciones = observacion_baja
        
        db.session.commit()
        
        return True
    
    @staticmethod
    def return_to_warehouse(miner_id: int, wh: int, rack: int = None, fila: int = None, columna: int = None, use_origin: bool = False):
        """
        Devuelve un minero del Stock Lab al warehouse
        Si no se especifican rack/fila/columna, queda en estado 'pendiente_colocacion'
        Si use_origin=True, busca la ubicación original de la solicitud de traslado
        
        Args:
            miner_id: ID del minero
            wh: warehouse destino
            rack, fila, columna: Posición destino (opcionales)
            use_origin: Si True, intenta volver a la ubicación original
            
        Returns:
            dict con 'success' (bool) y 'message' (str) o 'error' (str)
        """
        minero = Miner.query.get(miner_id)
        if not minero or minero.proceso_estado != 'stock_lab':
            return {'success': False, 'error': 'Minero no encontrado o no está en stock lab'}
        
        # Si use_origin=True, buscar la solicitud de traslado original para obtener coordenadas
        if use_origin:
            from app.models.solicitud import SolicitudTraslado
            solicitud = SolicitudTraslado.query.filter(
                SolicitudTraslado.miner_id == miner_id,
                SolicitudTraslado.estado == 'ejecutado'
            ).order_by(SolicitudTraslado.fecha_solicitud.desc()).first()
            
            if solicitud and solicitud.origen_wh and solicitud.origen_rack:
                wh = solicitud.origen_wh
                rack = solicitud.origen_rack
                fila = solicitud.origen_fila
                columna = solicitud.origen_columna
        
        # Si vienen coordenadas completas -> Verificar que la posición NO esté ocupada
        if rack and fila and columna:
            # Buscar si hay otro minero en esa posición
            ocupante = Miner.query.filter(
                Miner.warehouse_id == wh,
                Miner.rack_id == rack,
                Miner.fila == fila,
                Miner.columna == columna,
                Miner.id != miner_id  # Excluir al mismo minero
            ).first()
            
            if ocupante:
                return {
                    'success': False, 
                    'error': f'La posición WH{wh}-R{rack}-{fila}:{columna} ya está ocupada por el minero {ocupante.sn_fisica}'
                }
            
            # Posición libre, asignar
            minero.warehouse_id = wh
            minero.rack_id = rack
            minero.fila = fila
            minero.columna = columna
            minero.proceso_estado = 'operativo'
        else:
            # Sin coordenadas completas -> Pendiente de colocación
            minero.warehouse_id = wh
            minero.rack_id = None
            minero.fila = None
            minero.columna = None
            minero.proceso_estado = 'pendiente_colocacion'
        
        # Limpiar diagnóstico anterior
        minero.diagnostico_detalle = None
        minero.log_detalle = None
        
        db.session.commit()
        
        return {'success': True, 'message': 'Minero reinstalado correctamente'}

    
    @staticmethod
    def get_dashboard_stats():
        """
        Obtiene estadísticas generales del laboratorio para dashboards
        
        Returns:
            Dict con contadores por estado
        """
        from app.models.miner import Miner
        
        c_pendientes = Miner.query.filter_by(proceso_estado='en_laboratorio').count()
        c_reparacion = Miner.query.filter_by(proceso_estado='en_reparacion').count()
        c_stock = Miner.query.filter_by(proceso_estado='stock_lab').count()
        c_scrap = Miner.query.filter_by(proceso_estado='scrap').count()
        
        return {
            'c_pendientes': c_pendientes,
            'c_reparacion': c_reparacion,
            'c_stock': c_stock,
            'c_scrap': c_scrap,
            'c_total': c_pendientes + c_reparacion + c_stock + c_scrap
        }


# Instancia global
repair_service = RepairService()
