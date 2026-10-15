const API = (window.FIELDRES_API || "").replace(/\/$/, "");
const DIAS_VISIBLES = 14;

const $ = (id) => document.getElementById(id);

const estado = {
  usuario: null,
  canchas: [],
  canchaId: null,
  fecha: null,
  horario: null,
};

function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

const ICONO_OK = `<svg viewBox="0 0 24 24" class="size-5 text-cancha-200" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12l5 5L20 7"/></svg>`;
const ICONO_ERROR = `<svg viewBox="0 0 24 24" class="size-5 text-red-300" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 8v5M12 16.5v.5"/><circle cx="12" cy="12" r="9"/></svg>`;

function avisar(texto, error = false) {
  $("aviso-texto").textContent = texto;
  $("aviso-icono").innerHTML = error ? ICONO_ERROR : ICONO_OK;
  $("aviso-caja").classList.toggle("bg-red-600", error);
  $("aviso-caja").classList.toggle("bg-slate-900", !error);
  $("aviso").classList.replace("opacity-0", "opacity-100");
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => $("aviso").classList.replace("opacity-100", "opacity-0"), 3500);
}

async function api(metodo, ruta, body) {
  const res = await fetch(API + ruta, {
    method: metodo,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
  return data;
}

function fechaLocal(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function formatoFecha(iso, opciones = {}) {
  return new Date(iso).toLocaleString("es-MX", {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", ...opciones,
  });
}

function canchaActual() {
  return estado.canchas.find((c) => c.canchaId === estado.canchaId);
}

function nombreCancha(id) {
  return estado.canchas.find((c) => c.canchaId === id)?.nombre || id;
}

// ---- sesion ----

async function iniciarSesion(correo) {
  estado.usuario = correo.trim().toLowerCase();
  try { localStorage.setItem("fieldres-correo", estado.usuario); } catch {}
  $("chip-correo").textContent = estado.usuario;
  $("chip-usuario").classList.replace("hidden", "flex");
  $("vista-login").classList.add("hidden");
  $("vista-app").classList.remove("hidden");
  pintarDias();
  await cargarCanchas();
  await cargarMisReservas();
}

function salir() {
  try { localStorage.removeItem("fieldres-correo"); } catch {}
  location.reload();
}

// ---- canchas ----

async function cargarCanchas() {
  $("canchas").innerHTML = Array(3).fill(`<div class="h-24 animate-pulse rounded-xl bg-slate-100"></div>`).join("");
  try {
    estado.canchas = await api("GET", "/canchas");
  } catch (e) {
    $("canchas").innerHTML = "";
    avisar(e.message, true);
    return;
  }
  estado.canchaId ??= estado.canchas[0]?.canchaId;
  pintarCanchas();
  await cargarHorarios();
}

function pintarCanchas() {
  $("canchas").innerHTML = estado.canchas.map((c) => {
    const activa = c.canchaId === estado.canchaId;
    return `
      <button type="button" data-cancha="${esc(c.canchaId)}"
        class="group relative rounded-xl p-4 text-left ring-1 transition ${activa ? "bg-cancha-50 ring-2 ring-cancha-500" : "bg-white ring-slate-200 hover:ring-cancha-200"}">
        <span class="absolute right-3 top-3 grid size-5 place-items-center rounded-full ${activa ? "bg-cancha-500 text-white" : "ring-1 ring-slate-300"}">
          ${activa ? `<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12l5 5L20 7"/></svg>` : ""}
        </span>
        <p class="font-semibold">${esc(c.nombre)}</p>
        <p class="mt-0.5 text-sm text-slate-500">${esc(c.tipo || "Cancha")}</p>
        <p class="mt-3 text-sm"><span class="text-lg font-bold">$${esc(c.precioHora)}</span><span class="text-slate-500"> / hora</span></p>
      </button>`;
  }).join("") || `<p class="text-sm text-slate-500">No hay canchas disponibles</p>`;

  $("canchas").querySelectorAll("[data-cancha]").forEach((b) => {
    b.onclick = () => {
      estado.canchaId = b.dataset.cancha;
      pintarCanchas();
      cargarHorarios();
    };
  });
}

// ---- dias ----

function pintarDias() {
  const hoy = new Date();
  estado.fecha ??= fechaLocal(hoy);
  const dias = Array.from({ length: DIAS_VISIBLES }, (_, i) => {
    const d = new Date(hoy);
    d.setDate(hoy.getDate() + i);
    return d;
  });

  $("dias").innerHTML = dias.map((d, i) => {
    const valor = fechaLocal(d);
    const activo = valor === estado.fecha;
    const etiqueta = i === 0 ? "Hoy" : i === 1 ? "Mañana" : d.toLocaleDateString("es-MX", { weekday: "short" });
    return `
      <button type="button" data-fecha="${valor}"
        class="flex w-16 shrink-0 flex-col items-center rounded-xl py-2.5 ring-1 transition ${activo ? "bg-cancha-600 text-white ring-cancha-600 shadow-md shadow-cancha-600/30" : "bg-white text-slate-700 ring-slate-200 hover:ring-cancha-200"}">
        <span class="text-[11px] font-medium capitalize ${activo ? "text-cancha-100" : "text-slate-500"}">${etiqueta}</span>
        <span class="text-xl font-bold">${d.getDate()}</span>
        <span class="text-[11px] capitalize ${activo ? "text-cancha-100" : "text-slate-400"}">${d.toLocaleDateString("es-MX", { month: "short" }).replace(".", "")}</span>
      </button>`;
  }).join("");

  $("dias").querySelectorAll("[data-fecha]").forEach((b) => {
    b.onclick = () => {
      estado.fecha = b.dataset.fecha;
      pintarDias();
      cargarHorarios();
    };
  });
}

// ---- horarios ----

const CLASE_LIBRE = "rounded-lg bg-white py-2.5 text-sm font-semibold text-cancha-700 ring-1 ring-cancha-200 transition hover:bg-cancha-50 hover:ring-cancha-500";
const CLASE_ELEGIDO = "rounded-lg bg-cancha-600 py-2.5 text-sm font-semibold text-white ring-1 ring-cancha-600 shadow-md shadow-cancha-600/30";

async function cargarHorarios() {
  estado.horario = null;
  pintarResumen();
  const cont = $("horarios");
  if (!estado.canchaId || !estado.fecha) return;

  cont.innerHTML = Array(12).fill(`<div class="h-11 animate-pulse rounded-lg bg-slate-100"></div>`).join("");
  let data;
  try {
    data = await api("GET", `/canchas/${encodeURIComponent(estado.canchaId)}/disponibilidad?fecha=${estado.fecha}`);
  } catch (e) {
    cont.innerHTML = "";
    avisar(e.message, true);
    return;
  }

  if (!data.horarios.some((h) => h.disponible)) {
    cont.innerHTML = `<p class="col-span-full rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">No quedan horarios libres este dia. Prueba con otra fecha o cancha.</p>`;
    return;
  }

  cont.innerHTML = "";
  for (const h of data.horarios) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = h.hora;
    b.disabled = !h.disponible;
    b.title = h.ocupado ? "Ocupado" : h.disponible ? "Disponible" : "Ya paso";
    b.className = h.disponible ? CLASE_LIBRE : "rounded-lg bg-slate-100 py-2.5 text-sm font-medium text-slate-400 line-through";
    b.onclick = () => {
      cont.querySelectorAll("[data-elegido]").forEach((x) => {
        delete x.dataset.elegido;
        x.className = CLASE_LIBRE;
      });
      b.dataset.elegido = "";
      b.className = CLASE_ELEGIDO;
      estado.horario = h;
      pintarResumen();
    };
    cont.appendChild(b);
  }
}

function pintarResumen() {
  const h = estado.horario;
  const c = canchaActual();
  $("btn-reservar").disabled = !h;
  $("resumen").className = h ? "mt-1 font-semibold text-slate-900" : "mt-1 font-semibold text-slate-400";
  $("resumen").innerHTML = h && c
    ? `${esc(c.nombre)} · <span class="capitalize">${formatoFecha(h.fechaHora)}</span> · <span class="text-cancha-600">$${esc(c.precioHora)}</span>`
    : "Elige un horario disponible";
}

async function reservar() {
  const h = estado.horario;
  if (!h) return;
  const boton = $("btn-reservar");
  boton.disabled = true;
  boton.textContent = "Reservando...";
  try {
    await api("POST", "/reservas", { userId: estado.usuario, canchaId: estado.canchaId, fechaHora: h.fechaHora });
    avisar("Reserva confirmada");
  } catch (e) {
    avisar(e.message, true);
  }
  boton.textContent = "Reservar";
  await Promise.all([cargarHorarios(), cargarMisReservas()]);
}

// ---- mis reservas ----

async function cargarMisReservas() {
  const lista = $("lista-reservas");
  let reservas;
  try {
    reservas = await api("GET", `/reservas?userId=${encodeURIComponent(estado.usuario)}`);
  } catch (e) {
    avisar(e.message, true);
    return;
  }

  if (!reservas.length) {
    lista.innerHTML = `
      <li class="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center">
        <p class="text-sm font-medium text-slate-600">Todavia no tienes reservas</p>
        <p class="mt-1 text-xs text-slate-400">Las que hagas van a aparecer aqui</p>
      </li>`;
    return;
  }

  const ahora = Date.now();
  lista.innerHTML = "";
  for (const r of reservas) {
    const futura = new Date(r.fechaHora).getTime() > ahora;
    const confirmada = r.estado === "CONFIRMADA";
    const etiqueta = !confirmada
      ? `<span class="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-600">Cancelada</span>`
      : futura
        ? `<span class="rounded-full bg-cancha-50 px-2 py-0.5 text-[11px] font-semibold text-cancha-700">Confirmada</span>`
        : `<span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">Jugada</span>`;

    const li = document.createElement("li");
    li.className = `rounded-xl p-3 ring-1 ring-slate-200 ${confirmada && futura ? "bg-white" : "bg-slate-50 opacity-70"}`;
    li.innerHTML = `
      <div class="flex items-start justify-between gap-2">
        <div>
          <p class="font-semibold">${esc(nombreCancha(r.canchaId))}</p>
          <p class="text-sm capitalize text-slate-500">${formatoFecha(r.fechaHora)}</p>
        </div>
        ${etiqueta}
      </div>`;
    if (confirmada && futura) {
      const b = document.createElement("button");
      b.className = "mt-3 w-full rounded-lg py-1.5 text-sm font-medium text-red-600 ring-1 ring-red-100 transition hover:bg-red-50";
      b.textContent = "Cancelar reserva";
      b.onclick = () => confirmarCancelacion(r);
      li.appendChild(b);
    }
    lista.appendChild(li);
  }
}

function confirmarCancelacion(r) {
  $("modal-texto").textContent = `${nombreCancha(r.canchaId)} · ${formatoFecha(r.fechaHora)}`;
  $("modal").classList.replace("hidden", "flex");
  $("modal-no").onclick = cerrarModal;
  $("modal-si").onclick = async () => {
    cerrarModal();
    try {
      await api("DELETE", `/reservas/${encodeURIComponent(r.reservaId)}`, { userId: estado.usuario });
      avisar("Reserva cancelada");
    } catch (e) {
      avisar(e.message, true);
    }
    await Promise.all([cargarMisReservas(), cargarHorarios()]);
  };
}

function cerrarModal() {
  $("modal").classList.replace("flex", "hidden");
}

// ---- notificaciones ----

async function suscribir() {
  try {
    const r = await api("POST", "/suscripciones", { userId: estado.usuario });
    avisar(r.estado === "CONFIRMADA" ? "Ya tienes los avisos activados" : "Te mandamos un correo para confirmar");
  } catch (e) {
    avisar(e.message, true);
  }
}

function init() {
  $("form-usuario").onsubmit = (e) => {
    e.preventDefault();
    iniciarSesion($("correo").value);
  };
  $("btn-reservar").onclick = reservar;
  $("btn-recargar").onclick = cargarMisReservas;
  $("btn-suscribir").onclick = suscribir;
  $("btn-salir").onclick = salir;
  $("modal").onclick = (e) => e.target === $("modal") && cerrarModal();

  if (!API) {
    avisar("Falta configurar la URL de la API (config.js)", true);
    return;
  }

  let guardado = null;
  try { guardado = localStorage.getItem("fieldres-correo"); } catch {}
  if (guardado) iniciarSesion(guardado);
}

init();
