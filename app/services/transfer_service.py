"""
Servicio de Gestión de Solicitudes de Traslado
Maneja el workflow de aprobación de traslados de mineros
"""
from app.models.solicitud import SolicitudTraslado
from app.models.solicitud_pieza import SolicitudPieza
from app.models.diagnostico import Diagnostico
from app.models.miner import Miner
from app.models.user import User, Movimiento, Role
from app import db
from app.services.notification_service import send_notification
from datetime import datetime
from typing import List, Optional, Dict, Any


class TransferService:
    """Servicio para gestión de solicitudes de traslado"""
    
    @staticmethod
    def create_request(miner_id: int, destino: str, motivo: str, 
                      solicitante_id: int) -> SolicitudTraslado:
        """
        Crea una nueva solicitud de traslado
        
        Args:
            miner_id: ID del minero a trasladar
            destino: Destino del traslado ('LAB', 'WH2', etc.)
            motivo: Razón del traslado
            solicitante_id: ID del usuario que solicita
            
        Returns:
            SolicitudTraslado creada
        """
        minero = Miner.query.get(miner_id)
        if not minero:
            raise ValueError(f"Minero {miner_id} no encontrado")
        
        # Determinar sector basado en modelo
        modelo_lower = (minero.modelo or '').lower()
        sector = 'Hydro' if any(x in modelo_lower for x in ['hyd', 'm33', 'm53']) else 'WH'
        
        solicitud = SolicitudTraslado(
            miner_id=miner_id,
            origen_wh=minero.warehouse_id,
            origen_rack=minero.rack_id,
            origen_fila=minero.fila,
            origen_columna=minero.columna,
            destino=destino,
            sector=sector,
            motivo=motivo,
            solicitante_id=solicitante_id,
            estado='pendiente_lab'  # Nuevo estado inicial por defecto
        )
        
        # Bloquear miner de acciones RMA mientras tiene solicitud pendiente
        minero.proceso_estado = 'pendiente_traslado'

        # Si el traslado corresponde a RMA, registrar solución automática en historial de diagnóstico
        try:
            if (motivo or '').strip().upper().startswith('RMA'):
                ultimo_diag = Diagnostico.query.filter_by(miner_id=miner_id).order_by(Diagnostico.fecha.desc()).first()
                if ultimo_diag and not ultimo_diag.solucion:
                    ultimo_diag.solucion = 'RMA'
        except Exception:
            pass
        
        db.session.add(solicitud)
        db.session.commit()
        
        # NOTIFICAR AL LABORATORIO
        # Buscar ID del rol 'Lab' o notificar a todos con ese rol
        # Por simplicidad, asumiremos que existe un rol "Lab" o enviamos a Site Manager si no hay Lab definido
        lab_role = Role.query.filter(Role.nombre_puesto.ilike('%Lab%')).first()
        if lab_role:
            send_notification(
                message=f"Nueva solicitud de traslado: {minero.sn_fisica} ({motivo})",
                recipient_role_id=lab_role.id,
                link=f"/lab/aprobaciones/",
                type='info'
            )
        
        return solicitud
    
    @staticmethod
    def approve_request(solicitud_id: int, aprobador_id: int, 
                       comentario: str = '') -> bool:
        """
        Aprueba una solicitud de traslado
        
        Args:
            solicitud_id: ID de la solicitud
            aprobador_id: ID del usuario que aprueba
            comentario: Comentario opcional
            
        Returns:
            True si fue exitoso
        """
        solicitud = SolicitudTraslado.query.get(solicitud_id)
        # Puede aprobar si está en cualquier estado pendiente de coordinador
        if not solicitud or solicitud.estado not in ['pendiente_coordinador', 'pendiente_coordinador_hydro', 'pendiente']:
            return False
        
        aprobador = User.query.get(aprobador_id)
        aprobador_nombre = aprobador.username if aprobador else 'Usuario'

        solicitud.estado = 'aprobado'
        solicitud.aprobador_id = aprobador_id
        solicitud.fecha_resolucion = datetime.now()
        solicitud.comentario_resolucion = comentario or 'Aprobado'

        # Si hay solicitud de pieza vinculada a conciliación LAB, liberarla a Depósito
        solicitud_pieza = SolicitudPieza.query.filter_by(solicitud_traslado_id=solicitud.id).first()
        if solicitud_pieza and solicitud_pieza.estado == 'pendiente_coordinador':
            solicitud_pieza.estado = 'pendiente_deposito'

        db.session.commit()
        
        # Registrar en historial
        db.session.add(Movimiento(
            usuario_id=aprobador_id,
            accion="TRASLADO APROBADO",
            referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
            datos_nuevos=f"Destino: {solicitud.destino}. Aprobado por: {aprobador_nombre}"
        ))
        db.session.commit()
        
        # NOTIFICAR AL SOLICITANTE (FINAL)
        send_notification(
            message=f"¡Aprobado! Solicitud de traslado para {solicitud.miner.sn_fisica} autorizada.",
            recipient_user_id=solicitud.solicitante_id,
            type='success'
        )
        
        return True
    
    @staticmethod
    def reject_request(solicitud_id: int, aprobador_id: int, 
                      comentario: str = '') -> bool:
        """
        Rechaza una solicitud de traslado
        
        Args:
            solicitud_id: ID de la solicitud
            aprobador_id: ID del usuario que rechaza
            comentario: Razón del rechazo
            
        Returns:
            True si fue exitoso
        """
        solicitud = SolicitudTraslado.query.get(solicitud_id)
        # Solo puede rechazar si está pendiente de coordinador (o 'pendiente' legacy)
        if not solicitud or solicitud.estado not in ['pendiente_coordinador', 'pendiente']:
            return False
        
        solicitud.estado = 'rechazado'
        solicitud.aprobador_id = aprobador_id
        solicitud.fecha_resolucion = datetime.now()
        solicitud.comentario_resolucion = comentario or 'Rechazado'
        
        db.session.commit()
        
        return True
    
    @staticmethod
    def approve_bulk(solicitud_ids: List[int], aprobador_id: int) -> int:
        """
        Aprueba múltiples solicitudes a la vez
        
        Args:
            solicitud_ids: Lista de IDs de solicitudes
            aprobador_id: ID del usuario que aprueba
            
        Returns:
            Cantidad de solicitudes aprobadas
        """
        count = 0
        for sol_id in solicitud_ids:
            if TransferService.approve_request(sol_id, aprobador_id, 'Aprobación masiva'):
                count += 1
        
        return count
    
    @staticmethod
    def execute_transfer(solicitud_id: int) -> bool:
        """
        Ejecuta el traslado después de aprobación
        
        Args:
            solicitud_id: ID de la solicitud aprobada
            
        Returns:
            True si fue exitoso
        """
        solicitud = SolicitudTraslado.query.get(solicitud_id)
        if not solicitud or solicitud.estado != 'aprobado':
            return False
        
        minero = solicitud.miner
        
        # Si el destino es LAB, limpiar ubicación
        if solicitud.destino.upper() == 'LAB':
            minero.warehouse_id = None
            minero.rack_id = None
            minero.fila = None
            minero.columna = None
            minero.proceso_estado = 'en_laboratorio'
        
        solicitud.estado = 'ejecutado'
        db.session.commit()
        
        return True
    
    @staticmethod
    def get_pending_by_sector(sector: str = None) -> List[SolicitudTraslado]:
        """
        Obtiene solicitudes pendientes, opcionalmente filtradas por sector
        
        Args:
            sector: 'WH', 'Hydro' o None para todas
            
        Returns:
            Lista de solicitudes pendientes
        """
        query = SolicitudTraslado.query.filter(
            SolicitudTraslado.estado.in_(['pendiente_coordinador', 'pendiente_coordinador_hydro', 'pendiente'])
        )
        
        if sector:
            query = query.filter_by(sector=sector)
        
        return query.order_by(SolicitudTraslado.fecha_solicitud.desc()).all()
    
    @staticmethod
    def get_pending_count_by_sector() -> Dict[str, int]:
        """
        Obtiene contadores de solicitudes pendientes por sector
        
        Returns:
            Dict con contadores {'WH': 5, 'Hydro': 3, 'total': 8}
        """
        wh_count = SolicitudTraslado.query.filter(
            SolicitudTraslado.estado.in_(['pendiente_coordinador', 'pendiente']), 
            SolicitudTraslado.sector == 'WH'
        ).count()
        
        hydro_count = SolicitudTraslado.query.filter(
            SolicitudTraslado.estado.in_(['pendiente_coordinador', 'pendiente_coordinador_hydro']), 
            SolicitudTraslado.sector == 'Hydro'
        ).count()
        
        return {
            'WH': wh_count,
            'Hydro': hydro_count,
            'total': wh_count + hydro_count
        }
    
    @staticmethod
    def can_user_approve(user: User, solicitud: SolicitudTraslado) -> bool:
        """
        Verifica si un usuario puede aprobar una solicitud
        
        Args:
            user: Usuario a verificar
            solicitud: Solicitud a aprobar
            
        Returns:
            True si puede aprobar
        """
        if not user or not user.role:
            return False
        
        role_name = user.role.nombre_puesto
        
        # Site Manager puede aprobar todo
        if 'Site Manager' in role_name:
            return True
        
        # Coordinador Hydro solo puede aprobar solicitudes de Hydro en estado pendiente_coordinador_hydro
        if 'Coordinador Hydro' in role_name:
            return solicitud.sector == 'Hydro' and solicitud.estado == 'pendiente_coordinador_hydro'
        
        # Otros coordinadores pueden aprobar solicitudes en pendiente_coordinador (después de aprobación Hydro)
        if 'Coordinador' in role_name:
            # Si está pendiente de Coordinador Hydro, solo ese rol puede aprobar
            if solicitud.estado == 'pendiente_coordinador_hydro':
                return False
            return True
        
        return False

    @staticmethod
    def get_pending_lab_approval() -> List[SolicitudTraslado]:
        """Obtiene solicitudes pendientes de aprobación del laboratorio (incluye RMA)."""
        return SolicitudTraslado.query.filter(
            SolicitudTraslado.estado == 'pendiente_lab'
        ).order_by(SolicitudTraslado.fecha_solicitud.desc()).all()

    @staticmethod
    def lab_approve(solicitud_id: int, user_id: int) -> bool:
        """Laboratorio aprueba la solicitud -> pasa a Coordinador (según sector)"""
        solicitud = SolicitudTraslado.query.get(solicitud_id)
        if not solicitud or solicitud.estado != 'pendiente_lab':
            return False
        
        # Distinguir siguiente estado según sector
        if solicitud.sector == 'Hydro':
            solicitud.estado = 'pendiente_coordinador_hydro'
            msg = "Aprobado por Lab -> Enviado a Coordinador Hydro"
        else:
            solicitud.estado = 'pendiente_coordinador'
            msg = "Aprobado por Lab -> Enviado a Coordinador"

        # Si hay una conciliación asociada, avanzar pieza a pendiente de coordinador (no depósito aún)
        solicitud_pieza = SolicitudPieza.query.filter_by(solicitud_traslado_id=solicitud.id).first()
        if solicitud_pieza and solicitud_pieza.estado == 'pendiente_aprobacion_lab':
            solicitud_pieza.estado = 'pendiente_coordinador'
            db.session.add(Movimiento(
                usuario_id=user_id,
                accion="CONCILIACION VALIDADA LAB",
                referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
                datos_nuevos=f"Solicitud pieza #{solicitud_pieza.id} pasa a Coordinador"
            ))
        
        db.session.add(Movimiento(
            usuario_id=user_id,
            accion="PRE-APROBACION LAB",
            referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
            datos_nuevos=msg
        ))
        db.session.commit()
        
        # NOTIFICAR A COORDINADORES
        coord_role_name = 'Coordinador Hydro' if solicitud.sector == 'Hydro' else 'Coordinador'
        coord_role = Role.query.filter(Role.nombre_puesto.ilike(f'%{coord_role_name}%')).first()
        
        if coord_role:
             send_notification(
                message=f"Solicitud aprobada por Lab: {solicitud.miner.sn_fisica}. Pendiente de tu aprobación.",
                recipient_role_id=coord_role.id,
                link="/dashboard/coordinador", # Asumiendo ruta
                type='success'
            )

        return True
    
    @staticmethod
    def hydro_coordinator_approve(solicitud_id: int, user_id: int) -> bool:
        """Coordinador Hydro aprueba la solicitud -> pasa a Coordinador final o aprobado"""
        solicitud = SolicitudTraslado.query.get(solicitud_id)
        if not solicitud or solicitud.estado != 'pendiente_coordinador_hydro':
            return False
        
        # Después de aprobación de Coord Hydro, pasa directamente a aprobado
        # (Podría pasar a pendiente_coordinador si se requiere otra aprobación)
        solicitud.estado = 'aprobado'
        solicitud.aprobador_id = user_id
        solicitud.fecha_resolucion = datetime.now()
        solicitud.comentario_resolucion = 'Aprobado por Coordinador Hydro'
        
        db.session.add(Movimiento(
            usuario_id=user_id,
            accion="APROBACION COORD. HYDRO",
            referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
            datos_nuevos="Autorizado por Coordinador Hydro -> Listo para traslado"
        ))

        # En conciliaciones Hydro, la aprobación libera la pieza hacia Depósito
        solicitud_pieza = SolicitudPieza.query.filter_by(solicitud_traslado_id=solicitud.id).first()
        if solicitud_pieza and solicitud_pieza.estado == 'pendiente_coordinador':
            solicitud_pieza.estado = 'pendiente_deposito'
            db.session.add(Movimiento(
                usuario_id=user_id,
                accion="CONCILIACION HYDRO -> DEPOSITO",
                referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
                datos_nuevos=f"Solicitud pieza #{solicitud_pieza.id} habilitada para Depósito"
            ))

        db.session.commit()
        
        # NOTIFICAR AL SOLICITANTE (FINAL HYDRO)
        send_notification(
            message=f"¡Aprobado! Solicitud Hydro para {solicitud.miner.sn_fisica} autorizada.",
            recipient_user_id=solicitud.solicitante_id,
            type='success'
        )
        
        return True

    @staticmethod
    def lab_reject(solicitud_id: int, user_id: int, motivo: str) -> bool:
        """Laboratorio rechaza la solicitud -> Finaliza flujo"""
        solicitud = SolicitudTraslado.query.get(solicitud_id)
        if not solicitud or solicitud.estado != 'pendiente_lab':
            return False
            
        solicitud.estado = 'rechazado_lab'
        solicitud.fecha_resolucion = datetime.now()
        solicitud.comentario_resolucion = f"Rechazado por LAB: {motivo}"
        solicitud.aprobador_id = user_id

        solicitud_pieza = SolicitudPieza.query.filter_by(solicitud_traslado_id=solicitud.id).first()
        if solicitud_pieza:
            solicitud_pieza.estado = 'rechazado'
        
        # Restaurar miner a estado RMA para permitir reintento
        if solicitud.miner:
            solicitud.miner.proceso_estado = 'operativo'  # Vuelve a operativo con RMA (diagnostico_detalle aún existe)
        
        db.session.add(Movimiento(
            usuario_id=user_id,
            accion="TRASLADO CANCELADO",
            referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
            datos_nuevos=f"Motivo: {motivo}"
        ))
        db.session.commit()
        
        # NOTIFICAR AL SOLICITANTE
        send_notification(
            message=f"Solicitud rechazada para {solicitud.miner.sn_fisica}. Motivo: {motivo}",
            recipient_user_id=solicitud.solicitante_id,
            type='error'
        )
        
        return True


# Instancia global
transfer_service = TransferService()
