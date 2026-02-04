"""
Servicio de Movimientos y RMA
Gestiona traslados, RMA, conciliaciones y registro de movimientos
"""
from app.models.miner import Miner
from app.models.user import Movimiento
from app import db
from app.services.sheets_service import GoogleSheetsService
from datetime import datetime
from typing import Optional, Dict, Any
import threading


class MovementService:
    """Servicio para operaciones de movimiento y RMA de mineros"""
    
    def __init__(self):
        self.sheets_service = GoogleSheetsService()
    
    def send_to_rma(self, wh: int, rack: int, fila: int, columna: int, 
                    diagnostico: str, log: str, responsable: str) -> Optional[Miner]:
        """
        Envía un minero a RMA (laboratorio) y exporta a Google Sheets
        
        Args:
            wh, rack, fila, columna: Posición del minero
            diagnostico: Tipo de falla detectada
            log: Log detallado del error
            responsable: Usuario que reporta
            
        Returns:
            Objeto Miner actualizado o None si no existe
        """
        from app.services.miner_service import miner_service
        
        minero = miner_service.get_miner_by_position(wh, rack, fila, columna)
        if not minero:
            return None
        
        # Actualizar estado
        minero.proceso_estado = 'en_laboratorio'
        minero.diagnostico_detalle = diagnostico
        minero.log_detalle = log
        minero.responsable = responsable
        minero.fecha_diagnostico = datetime.now()
        
        # Limpiar posición (ya no está en el warehouse)
        minero.warehouse_id = None
        minero.rack_id = None
        minero.fila = None
        minero.columna = None
        
        db.session.commit()
        
        # Exportar a Google Sheets en segundo plano
        datos_sheets = {
            'fecha': datetime.now().strftime('%Y-%m-%d'),
            'responsable': responsable,
            'wh': wh,
            'rack': rack,
            'problem': diagnostico,
            'ip': minero.ip_address,
            'sn_digital': minero.sn_digital,
            'sn_fisico': minero.sn_fisica,
            'mac': minero.mac_address,
            'th': minero.ths,
            'psu_model': minero.psu_model,
            'psu_sn': minero.psu_sn,
            'hb1': minero.hb1_sn,
            'hb2': minero.hb2_sn,
            'hb3': minero.hb3_sn,
            'cb_sn': minero.cb_sn,
            'log': log
        }
        
        # Thread para no bloquear la respuesta
        thread = threading.Thread(
            target=self.sheets_service.exportar_rma_aire,
            args=(datos_sheets,)
        )
        thread.start()
        
        return minero
    
    def move_miner(self, wh: int, rack: int, fila: int, columna: int, 
                   motivo: str, responsable: str) -> Optional[Miner]:
        """
        Mueve un minero de RMA de vuelta al warehouse y registra movimiento
        
        Args:
            wh, rack, fila, columna: Posición destino
            motivo: Razón del traslado
            responsable: Usuario que ejecuta
            
        Returns:
            Objeto Miner actualizado
        """
        from app.services.miner_service import miner_service
        
        minero = miner_service.get_miner_by_position(wh, rack, fila, columna)
        if not minero:
            return None
        
        origen_wh = minero.warehouse_id or 'LAB'
        
        # Cambiar a laboratorio
        minero.proceso_estado = 'en_laboratorio'
        minero.warehouse_id = None
        minero.rack_id = None
        minero.fila = None
        minero.columna = None
        
        db.session.commit()
        
        # Registrar movimiento en Sheets
        datos_movimiento = {
            'fecha': datetime.now().strftime('%Y-%m-%d'),
            'sn_fisico': minero.sn_fisica,
            'origen': f'WH{origen_wh}',
            'destino': 'LAB',
            'observacion': motivo,
            'responsable': responsable,
            'motivo': motivo,
            'ip': minero.ip_address,
            'mac': minero.mac_address,
            'estado': 'EN LABORATORIO'
        }
        
        thread = threading.Thread(
            target=self.sheets_service.exportar_movimiento,
            args=(datos_movimiento,)
        )
        thread.start()
        
        return minero
    
    def cancel_rma(self, wh: int, rack: int, fila: int, columna: int) -> Optional[Miner]:
        """
        Cancela un RMA y devuelve el minero a estado operativo
        
        Args:
            wh, rack, fila, columna: Posición original
            
        Returns:
            Minero actualizado
        """
        from app.services.miner_service import miner_service
        
        minero = miner_service.get_miner_by_position(wh, rack, fila, columna)
        if not minero:
            return None
        
        # Restaurar posición y estado
        minero.warehouse_id = wh
        minero.rack_id = rack
        minero.fila = fila
        minero.columna = columna
        minero.proceso_estado = 'operativo'
        minero.diagnostico_detalle = None
        minero.log_detalle = None
        
        db.session.commit()
        return minero
    
    def conciliate_miner(self, wh: int, rack: int, fila: int, columna: int,
                        datos_adicionales: Dict[str, Any]) -> bool:
        """
        Concilia un minero en RMA y solicita cambio de piezas en Sheets
        
        Args:
            wh, rack, fila, columna: Posición original
            datos_adicionales: Datos extra del formulario
            
        Returns:
            True si fue exitoso
        """
        from app.services.miner_service import miner_service
        
        minero = miner_service.get_miner_by_position(wh, rack, fila, columna)
        if not minero:
            return False
        
        # Preparar datos para Sheets
        datos_cambio = {
            'fecha': datetime.now().strftime('%Y-%m-%d'),
            'problema': minero.diagnostico_detalle or 'N/A',
            'sn_maquina': minero.sn_fisica,
            'mac_digital': minero.mac_address,
            'ubicacion': f'WH{wh}-R{rack}',
            'modelo': minero.modelo,
            'modelo_especifico': f"{minero.psu_model} + {minero.ths}TH",
            'cant_coolers': datos_adicionales.get('cant_coolers', '0'),
            'psu_sn_viejo': minero.psu_sn,
            'cb_sn_viejo': minero.cb_sn,
            'detalles': minero.log_detalle or '',
            'tecnico': minero.responsable or 'Sistema',
            'ip': minero.ip_address,
            'estado': 'CONCILIADO - PENDIENTE REPUESTO'
        }
        
        # Exportar en thread
        thread = threading.Thread(
            target=self.sheets_service.exportar_cambio_piezas,
            args=(datos_cambio,)
        )
        thread.start()
        
        return True
    
    def log_movement(self, usuario_id: int, accion: str, miner_ref: str, 
                    datos_nuevos: str = '') -> Movimiento:
        """
        Registra un movimiento en el historial
        
        Args:
            usuario_id: ID del usuario que ejecuta
            accion: Descripción de la acción
            miner_ref: Referencia al minero (ej: 'WH1-R5-10:2')
            datos_nuevos: Datos adicionales en texto
            
        Returns:
            Objeto Movimiento creado
        """
        movimiento = Movimiento(
            usuario_id=usuario_id,
            accion=accion,
            referencia_miner=miner_ref,
            datos_nuevos=datos_nuevos
        )
        
        db.session.add(movimiento)
        db.session.commit()
        
        return movimiento


# Instancia global
movement_service = MovementService()
