// Función para solicitar traslado desde RMA (Existente, se mantiene)
async function solicitarTrasladoRMA() {
    const wh = document.getElementById('input-wh').value;
    const rack = document.getElementById('input-rack').value;
    const fila = document.getElementById('input-fila').value;
    const columna = document.getElementById('input-columna').value;

    const data = await ApiService.getMiner(wh, rack, fila, columna);

    if (!data || !data.diagnostico) {
        alert('No hay diagnóstico registrado para crear la solicitud');
        return;
    }

    const payload = {
        miner_id: data.id,
        destino: 'LAB',
        motivo: `RMA: ${data.diagnostico}`
    };

    try {
        const response = await fetch('/traslados/solicitar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.status === 'ok') {
            alert('✅ Solicitud de traslado creada exitosamente.');
            const modal = bootstrap.Modal.getInstance(document.getElementById('modalMiner'));
            if (modal) modal.hide();
            setTimeout(() => location.reload(), 500);
        } else {
            alert('❌ Error: ' + result.message);
        }
    } catch (error) {
        console.error('Error al crear solicitud:', error);
        alert('Error de conexión');
    }
}

// ==========================================
// NUEVA LÓGICA DE CONCILIACIÓN
// ==========================================

// Wrapper principal llamado desde el modal del minero
async function conciliarMiner() {
    const wh = document.getElementById('input-wh').value;
    const rack = document.getElementById('input-rack').value;
    const fila = document.getElementById('input-fila').value;
    const columna = document.getElementById('input-columna').value;

    iniciarConciliacion(wh, rack, fila, columna);
}

// Función core que recibe ubicación explicita (sirve para búsqueda rápida también)
async function iniciarConciliacion(wh, rack, fila, columna) {
    // Cerrar modales previos si existen
    const modalMinerEl = document.getElementById('modalMiner');
    if (modalMinerEl) {
        const modal = bootstrap.Modal.getInstance(modalMinerEl);
        if (modal) modal.hide();
    }

    const modalBusqueda = document.getElementById('modalBusquedaConciliacion');
    if (modalBusqueda) {
        const m = bootstrap.Modal.getInstance(modalBusqueda);
        if (m) m.hide();
    }

    // HYDRO (wh=100): Solo permite conciliación LAB, ir directo al formulario
    const HYDRO_WH_ID = 100;
    if (parseInt(wh) === HYDRO_WH_ID) {
        mostrarFormularioConciliacion('LAB', wh, rack, fila, columna);
        return;
    }

    // WH NORMAL: Modal de selección WH vs LAB
    const modalId = 'modalConciliacion';
    let modalEl = document.getElementById(modalId);
    if (modalEl) modalEl.remove();

    const html = `
    <div class="modal fade" id="${modalId}" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content bg-dark border-secondary shadow-lg">
          <div class="modal-header border-bottom border-secondary bg-black">
            <h5 class="modal-title text-success"><i class="bi bi-gear-wide-connected me-2"></i>Conciliación de Piezas</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body p-4">
            <p class="text-white mb-4 text-center">Datos del equipo: <strong>WH${wh}-R${rack} (F${fila}-C${columna})</strong><br>Seleccione dónde se realizará el cambio de pieza:</p>
            
            <div class="d-grid gap-3">
              <!-- OPCION WH -->
              <button class="btn btn-outline-warning btn-lg text-start p-3 hover-light" onclick="mostrarFormularioConciliacion('WH', '${wh}', '${rack}', '${fila}', '${columna}')">
                <div class="d-flex align-items-center">
                    <i class="bi bi-box-seam fs-1 me-3"></i>
                    <div>
                        <div class="fw-bold fs-5">EN WAREHOUSE (In Situ)</div>
                        <div class="text-white small">Cambio de pieza en el sitio. El equipo NO se mueve del rack.</div>
                        <div class="text-success small fst-italic mt-1"><i class="bi bi-check"></i> Genera Solicitud de Pieza al Lab</div>
                    </div>
                </div>
              </button>

              <!-- OPCION LAB -->
              <button class="btn btn-outline-info btn-lg text-start p-3 hover-light" onclick="mostrarFormularioConciliacion('LAB', '${wh}', '${rack}', '${fila}', '${columna}')">
                <div class="d-flex align-items-center">
                    <i class="bi bi-tools fs-1 me-3"></i>
                    <div>
                        <div class="fw-bold fs-5">EN LABORATORIO</div>
                        <div class="text-white small">El equipo se llevará a Mesa de Trabajo.</div>
                        <div class="text-info small fst-italic mt-1"><i class="bi bi-arrow-right"></i> Traslado Directo + Solicitud de Pieza</div>
                    </div>
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    const newModal = new bootstrap.Modal(document.getElementById(modalId));
    newModal.show();
}

async function mostrarFormularioConciliacion(tipo, wh, rack, fila, columna) {
    const modalSeleccion = bootstrap.Modal.getInstance(document.getElementById('modalConciliacion'));
    if (modalSeleccion) modalSeleccion.hide();

    const data = await ApiService.getMiner(wh, rack, fila, columna);
    if (!data || !data.id) {
        alert("Error al recuperar datos del minero.");
        return;
    }
    const minerId = data.id;

    const formModalId = 'modalFormConciliacion';
    let formModal = document.getElementById(formModalId);
    if (formModal) formModal.remove();

    const titulo = tipo === 'WH' ? 'Cambio en Warehouse' : 'Conciliación en Laboratorio';
    const color = tipo === 'WH' ? 'warning' : 'info';
    const bgHeader = 'bg-black';

    const htmlForm = `
    <div class="modal fade" id="${formModalId}" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content bg-dark border-${color} shadow-lg" style="border-width: 1px;">
          <div class="modal-header ${bgHeader} border-bottom border-secondary">
            <h5 class="modal-title text-${color}">${titulo}</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body p-4">
            <div class="mb-3">
                <label class="form-label text-white small fw-bold">PIEZA A CAMBIAR / REPARAR *</label>
                <select class="form-select bg-dark text-white border-secondary" id="conciliacion-pieza">
                    <option value="HASHBOARD">Hashboard</option>
                    <option value="PSU">Fuente de Poder (PSU)</option>
                    <option value="CONTROL_BOARD">Control Board</option>
                    <option value="FAN">Ventilador / Fan</option>
                    <option value="CABLE">Cables / Conectores</option>
                    <option value="OTRO">Otro</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label text-white small fw-bold">COMENTARIOS / DIAGNÓSTICO *</label>
                <textarea class="form-control bg-dark text-white border-secondary" id="conciliacion-comentario" rows="3" placeholder="Describa el problema..."></textarea>
            </div>
            <div class="alert alert-secondary small mb-0">
                <i class="bi bi-info-circle me-1"></i>
                ${tipo === 'WH' ? 'Se notificará al Lab para entregar la pieza. El equipo queda en WH.' : 'ATENCIÓN: El equipo saldrá del rack y pasará a estado EN REPARACIÓN inmediatamente.'}
            </div>
          </div>
          <div class="modal-footer border-top-0 pt-0">
            <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancelar</button>
            <button type="button" class="btn btn-${color} fw-bold" onclick="enviarConciliacion('${tipo}', ${minerId})">
                <i class="bi bi-send me-2"></i> Confirmar Solicitud
            </button>
          </div>
        </div>
      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', htmlForm);
    const fModal = new bootstrap.Modal(document.getElementById(formModalId));
    fModal.show();
}

async function enviarConciliacion(tipo, minerId) {
    const pieza = document.getElementById('conciliacion-pieza').value;
    const comentario = document.getElementById('conciliacion-comentario').value;

    if (!comentario) {
        alert("Por favor ingrese un comentario o diagnóstico.");
        return;
    }

    const btn = document.querySelector(`#modalFormConciliacion .btn-${tipo === 'WH' ? 'warning' : 'info'}`);
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Enviando...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/conciliacion/crear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tipo: tipo,
                miner_id: minerId,
                pieza: pieza,
                comentario: comentario
            })
        });

        const result = await response.json();

        if (result.status === 'ok') {
            const modal = bootstrap.Modal.getInstance(document.getElementById('modalFormConciliacion'));
            modal.hide();
            if (typeof Swal !== 'undefined') {
                Swal.fire('Éxito', result.message, 'success').then(() => location.reload());
            } else {
                alert(`✅ ${result.message}`);
                location.reload();
            }
        } else {
            alert(`❌ Error: ${result.message}`);
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    } catch (e) {
        console.error(e);
        alert("Error de conexión");
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// ==========================================
// FUNCIONES DE BÚSQUEDA RÁPIDA (DASHBOARD TÉCNICO)
// ==========================================

async function abrirModalBusquedaConciliacion() {
    const modalId = 'modalBusquedaConciliacion';
    let modalEl = document.getElementById(modalId);
    if (modalEl) modalEl.remove();

    const html = `
    <div class="modal fade" id="${modalId}" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content bg-dark border-success shadow-lg">
                <div class="modal-header border-bottom border-secondary bg-black">
                     <h5 class="modal-title text-success"><i class="bi bi-search me-2"></i>Conciliación Rápida</h5>
                     <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body p-4">
                    <label class="text-white mb-2">Ingrese SN o Ubicación del Equipo (WH-R-F-C):</label>
                    <div class="input-group mb-3">
                        <input type="text" id="input-busqueda-sn" class="form-control bg-dark text-white border-secondary" placeholder="Ej: SN12345 o IP..." onkeydown="if(event.key==='Enter') buscarParaConciliar()">
                        <button class="btn btn-success" type="button" onclick="buscarParaConciliar()">
                            <i class="bi bi-search"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    const m = new bootstrap.Modal(document.getElementById(modalId));
    m.show();
    setTimeout(() => document.getElementById('input-busqueda-sn').focus(), 500);
}

async function buscarParaConciliar() {
    const query = document.getElementById('input-busqueda-sn').value.trim();
    if (!query) return;

    const btn = document.querySelector('#modalBusquedaConciliacion .btn-success');
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    btn.disabled = true;

    try {
        const response = await fetch(`/api/buscar?q=${query}`);
        const data = await response.json();

        if (data.found && data.resultados.length > 0) {
            const r = data.resultados[0];
            // ID no siempre viene en resultados de búsqueda, a veces solo wh,rack... 
            // Pero iniciarConciliacion pide ubicación, no ID.
            if (r.wh && r.rack && r.fila && r.columna) {
                iniciarConciliacion(r.wh, r.rack, r.fila, r.columna);
            } else {
                alert('❌ Datos de ubicación incompletos en el resultado.');
            }
        } else {
            alert('❌ Minero no encontrado');
        }
    } catch (e) {
        alert('Error de conexión');
    } finally {
        if (btn) {
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    }
}
