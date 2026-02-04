from flask import Blueprint, render_template, request, session, jsonify
from app.utils.auth_decorators import login_required
from app.services.transfer_service import transfer_service
from app.models.solicitud import SolicitudTraslado

lab_approvals_bp = Blueprint('lab_approvals', __name__, url_prefix='/lab/aprobaciones')

@lab_approvals_bp.route('/')
@login_required
def panel():
    """Panel de pre-aprobación del laboratorio"""
    solicitudes = transfer_service.get_pending_lab_approval()
    return render_template('lab_approvals.html', solicitudes=solicitudes)

@lab_approvals_bp.route('/aprobar/<int:solicitud_id>', methods=['POST'])
@login_required
def aprobar(solicitud_id):
    """Aprueba solicitud para que pase a Coordinador"""
    if transfer_service.lab_approve(solicitud_id, session['user_id']):
        # HTMX: Retornar vacío para eliminar fila
        return '', 200
    return '<div class="alert alert-danger">Error al aprobar</div>', 400

@lab_approvals_bp.route('/rechazar/<int:solicitud_id>', methods=['POST'])
@login_required
def rechazar(solicitud_id):
    """Rechaza solicitud definitivamente"""
    motivo = request.form.get('motivo', 'Rechazado por Laboratorio')
    if transfer_service.lab_reject(solicitud_id, session['user_id'], motivo):
        return '', 200
    return '<div class="alert alert-danger">Error al rechazar</div>', 400
