// ==========================================
// 1. LÓGICA DEL BUSCADOR GLOBAL (MEJORADA)
// ==========================================
const HYDRO_WH_ID = 100;  // ID de warehouse para Hydro

// Helper: Generar URL correcta según tipo (Hydro vs WH)
function generarUrlMiner(r) {
    if (r.wh == HYDRO_WH_ID) {
        // Para Hydro: calcular contenedor desde rack_id
        // Container N tiene racks: (N*2-1) y (N*2), entonces Container = ceil(rack/2)
        const container = Math.ceil(r.rack / 2);
        return `/dashboard/hydro/container/${container}?rack=${r.rack}&target=${r.fila}-${r.columna}`;
    } else {
        // Para WH normal
        return `/dashboard/${r.wh}/${r.rack}?target=${r.fila}-${r.columna}`;
    }
}

async function handleSearch(event) {
    if (event.key === 'Enter') {
        const query = event.target.value.trim();
        if (!query) return;

        // Feedback visual
        event.target.style.opacity = "0.5";

        try {
            const response = await fetch(`/api/buscar?q=${query}`);

            // Si la respuesta redirige a login (sesión expirada)
            if (response.redirected || !response.ok) {
                if (response.redirected && response.url.includes('/login')) {
                    window.location.href = '/login';
                    return;
                }
                throw new Error('Error en la respuesta del servidor');
            }

            const data = await response.json();

            if (data.found) {
                // CASO A: Solo 1 resultado -> Redirección directa (Comportamiento clásico)
                if (data.total === 1) {
                    const r = data.resultados[0];
                    window.location.href = generarUrlMiner(r);
                }
                // CASO B: Varios resultados -> Mostrar Tabla Simplificada (NUEVO)
                else {
                    mostrarTablaResultados(data.resultados);
                }
            } else {
                alert("🚫 Equipo no encontrado en la base de datos.");
                event.target.focus();
            }
        } catch (error) {
            console.error(error);
            // Si hay error de parsing JSON, probablemente sesión expirada
            if (error.name === 'SyntaxError') {
                alert("Tu sesión ha expirado. Por favor, inicia sesión nuevamente.");
                window.location.href = '/login';
            } else {
                alert("Error de conexión con el servidor.");
            }
        } finally {
            event.target.style.opacity = "1";
        }
    }
}

// FUNCION AUXILIAR: Construye la tabla de resultados en el Modal
function mostrarTablaResultados(resultados) {
    const tbody = document.getElementById('tabla-resultados-body');
    if (!tbody) return; // Protección por si no existe el modal en esta vista

    tbody.innerHTML = ''; // Limpiar anterior

    resultados.forEach(r => {
        // Estilos según estado
        const colorEstado = (r.estado === 'en_laboratorio' || r.estado === 'en_reparacion') ? 'text-danger fw-bold' : 'text-success';
        const textoEstado = r.estado.replace('_', ' ').toUpperCase();

        // Badge Hydro/Aire
        const badgeTipo = r.tipo === 'HYDRO'
            ? '<span class="badge bg-primary bg-opacity-25 text-primary border border-primary">HYDRO</span>'
            : '<span class="badge bg-secondary bg-opacity-25 text-secondary border border-secondary">AIRE</span>';

        const row = `
            <tr>
                <td class="ps-4">
                    <div class="fw-bold text-white">${r.sn}</div>
                    <div class="small text-white">${r.modelo || 'Desconocido'}</div>
                </td>
                <td>${badgeTipo}</td>
                <td>
                    ${r.wh == HYDRO_WH_ID
                ? `<span class="text-info">C${Math.ceil(r.rack / 2)}</span> <i class="bi bi-chevron-right small text-white"></i> Rack ${r.rack % 2 === 1 ? 'A' : 'B'}`
                : `<span class="text-warning">WH ${r.wh}</span> <i class="bi bi-chevron-right small text-white"></i> Rack ${r.rack}`
            }
                </td>
                <td class="${colorEstado} small">${textoEstado}</td>
                <td class="text-end pe-4">
                    <a href="${generarUrlMiner(r)}" class="btn btn-sm btn-outline-light">
                        Ir <i class="bi bi-arrow-right"></i>
                    </a>
                </td>
            </tr>
        `;
        tbody.innerHTML += row;
    });

    // Abrir Modal (Asegúrate de tener el modalResultados en base.html)
    const myModal = new bootstrap.Modal(document.getElementById('modalResultados'));
    myModal.show();
}

// ==========================================
// 2. AUTO-OPEN & SCROLL (Al cargar la página)
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const urlParams = new URLSearchParams(window.location.search);
    const target = urlParams.get('target');

    if (target) {
        const [f, c] = target.split('-');

        // A. Buscar tarjeta y hacer scroll
        const tarjeta = document.getElementById(`cell-${f}-${c}`);
        if (tarjeta) {
            tarjeta.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
            tarjeta.classList.add('shining-gold');
            tarjeta.addEventListener('click', () => { tarjeta.classList.remove('shining-gold'); }, { once: true });
        }

        // B. Abrir modal automáticamente
        const path = window.location.pathname.split('/');
        const wh = path[2];
        const rack = path[3];

        if (wh && rack) {
            abrirModal(wh, rack, f, c);
        }

        // C. Limpiar URL
        window.history.replaceState({}, document.title, window.location.pathname);
    }
});

// ==========================================
// 3. FUNCIÓN PRINCIPAL: ABRIR MODAL
// ==========================================
// Variables globales para el flujo de selección
let currentMinerData = null;
let currentUbicacion = { wh: null, rack: null, fila: null, columna: null };

async function abrirModal(wh, rack, fila, columna) {
    const data = await ApiService.getMiner(wh, rack, fila, columna);

    if (data) {
        currentMinerData = data;
        currentUbicacion = { wh, rack, fila, columna };

        // 1. Si ya tiene RMA o está en laboratorio -> ABRIR MODAL ANTIGUO DIRECTAMENTE
        if (data.proceso_estado === 'en_laboratorio' || data.proceso_estado === 'en_reparacion' || data.diagnostico_detalle) {
            abrirModalMinerDirecto(data, wh, rack, fila, columna);
        }
        // 2. Si es un equipo "nuevo" o sin problemas -> ABRIR SELECCIÓN (Diagnóstico vs RMA)
        else {
            // Mostrar ubicación en formato correcto (Hydro vs WH)
            let ubicacionTxt;
            if (wh == HYDRO_WH_ID) {
                const container = Math.ceil(rack / 2);
                const rackLetra = rack % 2 === 1 ? 'A' : 'B';
                ubicacionTxt = `C${container}-${rackLetra} (${fila}-${columna})`;
            } else {
                ubicacionTxt = `WH ${wh} - Rack ${rack} (${fila}-${columna})`;
            }
            document.getElementById('decision-title').innerText = ubicacionTxt;
            const modalDecision = new bootstrap.Modal(document.getElementById('modalDecision'));
            modalDecision.show();
        }
    } else {
        // Si no hay datos (celda vacía o error), abrir modal antiguo vacío (para cargar nuevo)
        abrirModalMinerDirecto(null, wh, rack, fila, columna);
    }
}

// Nueva función que encapsula la lógica antigua de abrir el modal detallado
function abrirModalMinerDirecto(data, wh, rack, fila, columna) {
    // Cerrar otros modales si están abiertos
    const modalDecisionEl = document.getElementById('modalDecision');
    const modalDecision = bootstrap.Modal.getInstance(modalDecisionEl);
    if (modalDecision) modalDecision.hide();

    const titulo = document.getElementById('modal-titulo');
    const form = document.getElementById('formMiner');
    const headerModal = document.querySelector('#modalMiner .modal-header');

    const btnsNormal = document.getElementById('btns-normal');
    const btnsRMA = document.getElementById('btns-rma');

    titulo.innerText = `${fila}-${columna}`;
    form.reset();
    headerModal.classList.remove('bg-danger');
    headerModal.classList.add('bg-black');
    document.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));

    document.getElementById('input-wh').value = wh;
    document.getElementById('input-rack').value = rack;
    document.getElementById('input-fila').value = fila;
    document.getElementById('input-columna').value = columna;

    if (data) {
        // Llenado de inputs
        document.getElementById('input-modelo').value = data.modelo || '';
        document.getElementById('input-ths').value = data.ths || '';
        document.getElementById('input-mac').value = data.mac_address || '';
        document.getElementById('input-sn').value = data.sn_fisica || '';
        document.getElementById('input-sn-digital').value = data.sn_digital || '';
        document.getElementById('input-psu-model').value = data.psu_model || '';
        document.getElementById('input-psu').value = data.psu_sn || '';
        document.getElementById('input-cb').value = data.cb_sn || '';
        document.getElementById('input-hb1').value = data.hb1_sn || '';
        document.getElementById('input-hb2').value = data.hb2_sn || '';
        document.getElementById('input-hb3').value = data.hb3_sn || '';

        if (data.diagnostico) document.getElementById('input-falla').value = data.diagnostico;
        if (data.log) document.getElementById('input-log').value = data.log;

        // --- LÓGICA DE ESTADOS Y BOTONES ---
        const tieneRMA = (data.proceso_estado === 'en_laboratorio' || data.proceso_estado === 'en_reparacion' || data.diagnostico_detalle);
        const estadoBloqueado = (data.proceso_estado === 'pendiente_traslado' || data.proceso_estado === 'Conciliando');

        // NUEVO: Si está en estado bloqueado, mostrar solo info sin opciones
        if (estadoBloqueado) {
            headerModal.classList.remove('bg-black');
            headerModal.classList.add('bg-danger');

            if (data.proceso_estado === 'pendiente_traslado') {
                titulo.innerText += " (EN TRASLADO)";
            } else {
                titulo.innerText += " (EN CONCILIACIÓN)";
            }

            btnsNormal.style.display = 'none';
            btnsRMA.style.display = 'none'; // Sin botones RMA
            form.style.display = 'none';

            // Mostrar info del estado
            renderLockedInfo(data, form);
        }
        else if (tieneRMA) {
            headerModal.classList.remove('bg-black');
            headerModal.classList.add('bg-danger');
            titulo.innerText += " (CON RMA)";
            btnsNormal.style.display = 'none';
            btnsRMA.style.display = 'block';
            form.style.display = 'none';

            // Ocultar botón Cancelar RMA si hay traslado pendiente
            const btnCancelarRMA = document.querySelector('#btns-rma button[onclick="cancelarRMA()"]');
            const btnSolicitarTraslado = document.querySelector('#btns-rma button[onclick="solicitarTrasladoRMA()"]');
            if (btnCancelarRMA && data.traslado_pendiente) {
                btnCancelarRMA.style.display = 'none';
                // También ocultar solicitar traslado si ya está pendiente
                if (btnSolicitarTraslado) btnSolicitarTraslado.style.display = 'none';
            } else {
                if (btnCancelarRMA) btnCancelarRMA.style.display = 'block';
                if (btnSolicitarTraslado) btnSolicitarTraslado.style.display = 'block';
            }

            // Render info RMA (igual que antes)
            renderRMAInfo(data, form);
        } else {
            form.style.display = 'block';
            btnsNormal.style.display = 'block';
            btnsRMA.style.display = 'none';
            const container = document.getElementById('rma-info-container');
            if (container) container.innerHTML = '';
        }
    } else {
        titulo.innerText = `${fila}-${columna} (Nuevo)`;
        btnsNormal.style.display = 'none'; // Se activa al llenar datos? No, botones guardar o RMA. 
        // En lógica original btnsNormal se muestra si no es RMA. Pero 'Nuevo' podría requerir guardar primero.
        // Asumiremos comportamiento 'normal'.
        btnsNormal.style.display = 'block';
        btnsRMA.style.display = 'none';
    }

    const myModal = new bootstrap.Modal(document.getElementById('modalMiner'));
    myModal.show();
}

function renderRMAInfo(data, form) {
    let rmaInfoContainer = document.getElementById('rma-info-container');
    if (!rmaInfoContainer) {
        rmaInfoContainer = document.createElement('div');
        rmaInfoContainer.id = 'rma-info-container';
        form.parentElement.insertBefore(rmaInfoContainer, form);
    }
    rmaInfoContainer.innerHTML = '';

    const infoMinero = document.createElement('div');
    infoMinero.className = 'mb-3 p-3 bg-dark rounded border border-secondary';
    infoMinero.innerHTML = `
        <h6 class="text-white mb-2"><i class="bi bi-cpu me-2"></i>Información del Equipo</h6>
        <div class="row text-white small">
            <div class="col-6"><strong>SN:</strong> ${data.sn_fisica || 'N/A'}</div>
            <div class="col-6"><strong>Modelo:</strong> ${data.modelo || 'N/A'}</div>
            <div class="col-6"><strong>TH/s:</strong> ${data.ths || 'N/A'}</div>
            <div class="col-6"><strong>IP:</strong> ${data.ip_address || 'N/A'}</div>
        </div>
    `;
    rmaInfoContainer.appendChild(infoMinero);

    if (data.diagnostico_detalle) {
        const alertRMA = document.createElement('div');
        alertRMA.className = 'alert alert-danger mb-3';
        alertRMA.innerHTML = `<strong><i class="bi bi-exclamation-triangle me-2"></i>RMA Registrado:</strong><br>${data.diagnostico_detalle}`;
        rmaInfoContainer.appendChild(alertRMA);
    }
}

// Función para mostrar info cuando el equipo está bloqueado (en traslado o conciliación)
function renderLockedInfo(data, form) {
    let rmaInfoContainer = document.getElementById('rma-info-container');
    if (!rmaInfoContainer) {
        rmaInfoContainer = document.createElement('div');
        rmaInfoContainer.id = 'rma-info-container';
        form.parentElement.insertBefore(rmaInfoContainer, form);
    }
    rmaInfoContainer.innerHTML = '';

    const infoMinero = document.createElement('div');
    infoMinero.className = 'mb-3 p-3 bg-dark rounded border border-secondary';
    infoMinero.innerHTML = `
        <h6 class="text-white mb-2"><i class="bi bi-cpu me-2"></i>Información del Equipo</h6>
        <div class="row text-white small">
            <div class="col-6"><strong>SN:</strong> ${data.sn_fisica || 'N/A'}</div>
            <div class="col-6"><strong>Modelo:</strong> ${data.modelo || 'N/A'}</div>
            <div class="col-6"><strong>TH/s:</strong> ${data.ths || 'N/A'}</div>
            <div class="col-6"><strong>IP:</strong> ${data.ip_address || 'N/A'}</div>
        </div>
    `;
    rmaInfoContainer.appendChild(infoMinero);

    // Mensaje de estado bloqueado
    const alertEstado = document.createElement('div');
    if (data.proceso_estado === 'pendiente_traslado') {
        alertEstado.className = 'alert alert-warning mb-3';
        alertEstado.innerHTML = `
            <strong><i class="bi bi-hourglass-split me-2"></i>Traslado Pendiente</strong><br>
            Este equipo tiene una solicitud de traslado en proceso.<br>
            <small class="text-white">Espera la aprobación del coordinador para continuar.</small>
        `;
    } else {
        alertEstado.className = 'alert alert-info mb-3';
        alertEstado.innerHTML = `
            <strong><i class="bi bi-tools me-2"></i>En Conciliación</strong><br>
            Este equipo está en proceso de conciliación de piezas.<br>
            <small class="text-white">Espera a que finalice el proceso para tomar otras acciones.</small>
        `;
    }
    rmaInfoContainer.appendChild(alertEstado);

    if (data.diagnostico_detalle) {
        const alertRMA = document.createElement('div');
        alertRMA.className = 'alert alert-danger mb-0';
        alertRMA.innerHTML = `<strong><i class="bi bi-exclamation-triangle me-2"></i>RMA Registrado:</strong><br>${data.diagnostico_detalle}`;
        rmaInfoContainer.appendChild(alertRMA);
    }
}

// === NUEVAS FUNCIONES DE FLUJO ===

function abrirRMA() {
    if (currentMinerData) {
        abrirModalMinerDirecto(currentMinerData, currentUbicacion.wh, currentUbicacion.rack, currentUbicacion.fila, currentUbicacion.columna);
    }
}

function abrirFormularioDiagnostico() {
    // Cerrar modal selección
    const modalDecision = bootstrap.Modal.getInstance(document.getElementById('modalDecision'));
    if (modalDecision) modalDecision.hide();

    // Llenar datos form diagnóstico
    document.getElementById('diag-wh').value = currentUbicacion.wh;
    document.getElementById('diag-rack').value = currentUbicacion.rack;
    document.getElementById('diag-fila').value = currentUbicacion.fila;
    document.getElementById('diag-columna').value = currentUbicacion.columna;
    document.getElementById('diag-miner-id').value = currentMinerData.id || ''; // Asumiendo ID viene en data

    document.getElementById('diag-ubicacion-txt').innerText = `WH${currentUbicacion.wh} R${currentUbicacion.rack} (${currentUbicacion.fila}-${currentUbicacion.columna})`;
    document.getElementById('diag-sn-txt').innerText = currentMinerData.sn_fisica || 'No registrado';

    document.getElementById('diag-ip').value = currentMinerData.ip_address || '';
    document.getElementById('diag-sn-digital').value = currentMinerData.sn_digital || '';

    // Reset campos
    document.getElementById('diag-falla').value = '';
    document.getElementById('diag-solucion').value = '';
    document.getElementById('diag-observacion').value = '';

    const modalDiag = new bootstrap.Modal(document.getElementById('modalDiagnostico'));
    modalDiag.show();
}

function checkSolucionDiag(val) {
    if (val === 'RMA') {
        if (confirm("Al seleccionar RMA serás redirigido al formulario de solicitud de repuestos/traslado. ¿Continuar?")) {
            // Cerrar modal diag y abrir RMA
            const modalDiag = bootstrap.Modal.getInstance(document.getElementById('modalDiagnostico'));
            if (modalDiag) modalDiag.hide();
            abrirRMA();
        } else {
            document.getElementById('diag-solucion').value = ''; // Resetear selección
        }
    }
}

async function guardarDiagnostico() {
    // Validar
    const falla = document.getElementById('diag-falla').value;
    const solucion = document.getElementById('diag-solucion').value;

    if (!falla || !solucion) {
        alert("⚠️ Falla y Solución son obligatorios.");
        return;
    }

    const payload = {
        wh: document.getElementById('diag-wh').value,
        rack: document.getElementById('diag-rack').value,
        fila: document.getElementById('diag-fila').value,
        columna: document.getElementById('diag-columna').value,
        miner_id: document.getElementById('diag-miner-id').value,
        ip: document.getElementById('diag-ip').value,
        sn_digital: document.getElementById('diag-sn-digital').value,
        sn_fisica: currentMinerData.sn_fisica, // Tomar del original para referencia
        falla: falla,
        solucion: solucion,
        observacion: document.getElementById('diag-observacion').value
    };

    try {
        const res = await fetch('/api/diagnostico/guardar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const json = await res.json();

        if (res.ok) {
            alert("✅ Diagnóstico guardado correctamente.");
            location.reload();
        } else {
            alert("Error: " + json.message);
        }
    } catch (e) {
        alert("Error de conexión");
        console.error(e);
    }
}

// ==========================================
// 4. ACCIÓN: CONCILIAR (CON AUTO-GUARDADO)
// ==========================================
async function conciliarMiner() {
    const wh = document.getElementById('input-wh').value;
    const rack = document.getElementById('input-rack').value;
    const f = document.getElementById('input-fila').value;
    const c = document.getElementById('input-columna').value;

    const datosPantalla = {
        sn_digital: document.getElementById('input-sn-digital').value,
        mac: document.getElementById('input-mac').value,
        psu_sn: document.getElementById('input-psu').value,
        psu_model: document.getElementById('input-psu-model').value,
        cb_sn: document.getElementById('input-cb').value
    };

    const fallaActual = document.getElementById('input-falla').value;
    let cantCoolers = "";

    if (fallaActual === 'FAN') {
        const input = prompt("🔧 FALLA DE VENTILACIÓN DETECTADA\n\nIngrese la CANTIDAD de coolers dañados:", "1");
        if (input === null) return;
        cantCoolers = input;
    }

    if (confirm("¿Confirmar conciliación y solicitud de repuestos en Sheets?")) {
        try {
            const btn = document.querySelector('button[onclick="conciliarMiner()"]');
            if (btn) { btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> ...'; btn.disabled = true; }

            await fetch('/api/conciliar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wh, rack, f, c,
                    cant_coolers: cantCoolers,
                    ...datosPantalla
                })
            });

            alert("✅ Conciliación registrada y enviada con todos los datos.");
            if (btn) { btn.innerHTML = '<i class="bi bi-check2-circle"></i> CONCILIAR'; btn.disabled = false; }

        } catch (e) {
            alert("Error al conciliar");
            if (btn) btn.disabled = false;
        }
    }
}

// ==========================================
// 5. ACCIÓN: MOVER (TRASLADO) INTELIGENTE
// ==========================================
async function moverMiner() {
    const wh = document.getElementById('input-wh').value;
    const rack = document.getElementById('input-rack').value;
    const f = document.getElementById('input-fila').value;
    const c = document.getElementById('input-columna').value;

    const datosPantalla = {
        sn_digital: document.getElementById('input-sn-digital').value,
        mac: document.getElementById('input-mac').value,
        psu_sn: document.getElementById('input-psu').value,
        psu_model: document.getElementById('input-psu-model').value,
        cb_sn: document.getElementById('input-cb').value
    };

    const fallaDetectada = document.getElementById('input-falla').value;
    const logDetectado = document.getElementById('input-log').value;
    let motivoFinal = "";

    if (fallaDetectada && fallaDetectada !== "") {
        motivoFinal = fallaDetectada;
        if (logDetectado) motivoFinal += ` - ${logDetectado}`;
    } else {
        const inputUsuario = prompt("📋 TRASLADO A LABORATORIO\n\nIngrese el MOTIVO del traslado:", "Reubicación");
        if (inputUsuario === null) return;
        motivoFinal = inputUsuario;
    }

    if (confirm(`¿Mover a LABORATORIO?\n\nMotivo: ${motivoFinal}`)) {
        try {
            const btn = document.querySelector('#btns-rma button[onclick="moverMiner()"]');
            if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> ...'; }

            await fetch('/api/mover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wh, rack, f, c,
                    motivo: motivoFinal,
                    ...datosPantalla
                })
            });
            alert("✅ Equipo retirado y datos completos exportados.");
            location.reload();
        } catch (e) {
            alert("Error al mover.");
            if (btn) btn.disabled = false;
        }
    }
}

// ==========================================
// 6. ACCIÓN: ENVIAR A RMA (VALIDACIÓN)
// ==========================================
function validarYEnviarRMA() {
    document.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    let faltaAlgo = false;
    let mensajeError = "";

    const camposUniversales = ['input-sn', 'input-ip-rma', 'input-mac', 'input-ths', 'input-falla', 'input-log'];
    camposUniversales.forEach(id => {
        const input = document.getElementById(id);
        if (!input || !input.value.trim()) {
            if (input) input.classList.add('is-invalid');
            faltaAlgo = true;
        }
    });

    if (faltaAlgo) {
        mensajeError = "Faltan datos básicos obligatorios (SN, IP del puerto actual, MAC, TH, Falla o Log).";
    } else {
        const tipoFalla = document.getElementById('input-falla').value;
        if (tipoFalla === 'PSU') {
            const psuModel = document.getElementById('input-psu-model');
            const psuSn = document.getElementById('input-psu');
            if (!psuModel.value.trim()) { psuModel.classList.add('is-invalid'); faltaAlgo = true; }
            if (!psuSn.value.trim()) { psuSn.classList.add('is-invalid'); faltaAlgo = true; }
            if (faltaAlgo) mensajeError = "Para falla de PSU, debes completar Modelo y SN de la fuente.";
        } else if (tipoFalla === 'CONTROL BOARD') {
            const cbSn = document.getElementById('input-cb');
            if (!cbSn.value.trim()) { cbSn.classList.add('is-invalid'); faltaAlgo = true; mensajeError = "SN de Control Board obligatorio."; }
        } else if (tipoFalla === 'HASHBOARD') {
            const hb1 = document.getElementById('input-hb1').value.trim();
            const hb2 = document.getElementById('input-hb2').value.trim();
            const hb3 = document.getElementById('input-hb3').value.trim();
            if (!hb1 && !hb2 && !hb3) {
                ['input-hb1', 'input-hb2', 'input-hb3'].forEach(id => document.getElementById(id).classList.add('is-invalid'));
                faltaAlgo = true; mensajeError = "Ingresa al menos un SN de placa (HB).";
            }
        }
    }

    if (faltaAlgo) {
        alert("⚠️ DATOS INCOMPLETOS:\n\n" + mensajeError);
        return;
    }

    if (confirm("✅ Datos completos.\n\n¿Enviar a LABORATORIO y registrar en GOOGLE SHEETS?")) {
        const form = document.getElementById('formMiner');
        form.action = "/api/rma/enviar_y_exportar";
        form.submit();
    }
}

// ==========================================
// 7. ACCIÓN: CANCELAR RMA
// ==========================================
async function cancelarRMA() {
    const wh = document.getElementById('input-wh').value;
    const rack = document.getElementById('input-rack').value;
    const f = document.getElementById('input-fila').value;
    const c = document.getElementById('input-columna').value;

    if (confirm("¿Fue un error? \n\nEste equipo volverá a estado OPERATIVO.")) {
        try {
            const response = await fetch('/api/rma/cancelar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ wh, rack, f, c })
            });
            if (response.ok) { alert("✅ RMA Cancelado."); location.reload(); }
            else { alert("❌ Error al cancelar."); }
        } catch (e) { alert("Error de conexión."); }
    }
}

// ==========================================
// 8. FUNCIONES DE LABORATORIO (GLOBALES)
// ==========================================

// A. INICIAR REPARACIÓN (Para Solicitudes)
async function iniciarReparacion(id) {
    if (confirm("¿Recibir este equipo e iniciar diagnóstico en la Mesa de Trabajo?")) {
        try {
            const res = await fetch('/api/lab/iniciar', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id })
            });
            if (res.ok) location.reload();
        } catch (e) { alert("Error de conexión"); }
    }
}

// B. TERMINAR REPARACIÓN (Para Mesa de Trabajo)
async function finalizarReparacion(id) {
    const solucion = prompt("📝 Breve detalle de la reparación realizada:", "Cambio de ventilador");
    if (solucion) {
        try {
            const res = await fetch('/api/lab/terminar', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, solucion })
            });
            if (res.ok) { alert("✅ Equipo enviado a Stock."); location.reload(); }
        } catch (e) { alert("Error."); }
    }
}

// C. SCRAP / BAJA (Modal y Confirmación)
let modalScrap;
function abrirModalScrap(id, sn) {
    // Si el elemento no existe en esta página (ej: dashboard normal), salir
    if (!document.getElementById('scrap-id')) return;

    document.getElementById('scrap-id').value = id;
    document.getElementById('scrap-sn').innerText = sn;
    modalScrap = new bootstrap.Modal(document.getElementById('modalScrap'));
    modalScrap.show();
}

async function confirmarScrap(tipo) {
    const id = document.getElementById('scrap-id').value;
    const motivo = prompt("Motivo de la baja:", "Irreparable");
    if (motivo) {
        try {
            const res = await fetch('/api/lab/scrap', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, tipo, motivo })
            });
            if (res.ok) { alert("✅ Equipo dado de baja."); location.reload(); }
        } catch (e) { alert("Error."); }
    }
}