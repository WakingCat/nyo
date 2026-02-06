from app.models.solicitud import SolicitudTraslado
from app.models.user import Movimiento
from app.extensions import db
from datetime import datetime
from typing import List

@staticmethod
def get_pending_lab_approval() -> List[SolicitudTraslado]:
    """Obtiene solicitudes pendientes de aprobación del laboratorio"""
    return SolicitudTraslado.query.filter_by(estado='pendiente_lab')\
        .order_by(SolicitudTraslado.fecha_solicitud.desc()).all()

@staticmethod
def lab_approve(solicitud_id: int, user_id: int) -> bool:
    """Laboratorio aprueba la solicitud -> pasa a Coordinador"""
    solicitud = SolicitudTraslado.query.get(solicitud_id)
    if not solicitud or solicitud.estado != 'pendiente_lab':
        return False
        
    solicitud.estado = 'pendiente_coordinador'
    # Podríamos guardar quién aprobó en 'comentario_resolucion' o campo nuevo
    # Por simplicidad lo dejamos así o lo logueamos
    db.session.add(Movimiento(
        usuario_id=user_id,
        accion="PRE-APROBACION LAB",
        referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
        datos_nuevos="Aprobado por Lab -> Enviado a Coordinador"
    ))
    db.session.commit()
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
        
    db.session.add(Movimiento(
        usuario_id=user_id,
        accion="TRASLADO CANCELADO",
        referencia_miner=f"SN: {solicitud.miner.sn_fisica}",
        datos_nuevos=f"Motivo: {motivo}"
    ))
    db.session.commit()
    return True
