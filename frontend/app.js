const API = (window.FIELDRES_API || "").replace(/\/$/, "");

const $ = (id) => document.getElementById(id);

const estado = {
  usuario: null,
  canchas: [],
  horario: null,
};

function avisar(texto, error = false) {
  const el = $("aviso");
  el.textContent = texto;
  el.classList.toggle("error", error);
  el.hidden = false;
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => (el.hidden = true), 4000);
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

function formatoFecha(iso) {
  return new Date(iso).toLocaleString("es-MX", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function nombreCancha(id) {
  return estado.canchas.find((c) => c.canchaId === id)?.nombre || id;
}

async function iniciarSesion(correo) {
  estado.usuario = correo.trim().toLowerCase();
  try { localStorage.setItem("fieldres-correo", estado.usuario); } catch {}
  $("correo").value = estado.usuario;
  $("estado-usuario").textContent = `Reservando como ${estado.usuario}`;
  $("btn-suscribir").hidden = false;
  $("seccion-reservar").hidden = false;
  $("seccion-mis-reservas").hidden = false;
  await cargarCanchas();
  await cargarMisReservas();
}

async function cargarCanchas() {
  try {
    estado.canchas = await api("GET", "/canchas");
  } catch (e) {
    avisar(e.message, true);
    return;
  }
  $("cancha").innerHTML = estado.canchas
    .map((c) => `<option value="${c.canchaId}">${c.nombre} · ${c.tipo || ""} · $${c.precioHora}/h</option>`)
    .join("");
  await cargarHorarios();
}

async function cargarHorarios() {
  estado.horario = null;
  actualizarSeleccion();
  const cont = $("horarios");
  const cancha = $("cancha").value;
  const fecha = $("fecha").value;
  if (!cancha || !fecha) return;

  cont.innerHTML = `<span class="nota">Cargando horarios...</span>`;
  let data;
  try {
    data = await api("GET", `/canchas/${encodeURIComponent(cancha)}/disponibilidad?fecha=${fecha}`);
  } catch (e) {
    cont.innerHTML = "";
    avisar(e.message, true);
    return;
  }

  cont.innerHTML = "";
  for (const h of data.horarios) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "horario";
    b.textContent = h.hora;
    b.disabled = !h.disponible;
    b.title = h.ocupado ? "Ocupado" : h.disponible ? "Disponible" : "Ya paso";
    b.onclick = () => {
      cont.querySelectorAll(".elegido").forEach((x) => x.classList.remove("elegido"));
      b.classList.add("elegido");
      estado.horario = h;
      actualizarSeleccion();
    };
    cont.appendChild(b);
  }
}

function actualizarSeleccion() {
  const h = estado.horario;
  $("btn-reservar").disabled = !h;
  $("seleccion").textContent = h
    ? `${nombreCancha($("cancha").value)} · ${formatoFecha(h.fechaHora)}`
    : "Elige un horario disponible";
}

async function reservar() {
  const h = estado.horario;
  if (!h) return;
  $("btn-reservar").disabled = true;
  try {
    await api("POST", "/reservas", {
      userId: estado.usuario,
      canchaId: $("cancha").value,
      fechaHora: h.fechaHora,
    });
    avisar("Reserva confirmada");
  } catch (e) {
    avisar(e.message, true);
  }
  await cargarHorarios();
  await cargarMisReservas();
}

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
    lista.innerHTML = `<li class="nota">Todavia no tienes reservas</li>`;
    return;
  }
  lista.innerHTML = "";
  const ahora = Date.now();
  for (const r of reservas) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="detalle">
        <strong>${nombreCancha(r.canchaId)}<span class="etiqueta ${r.estado}">${r.estado.toLowerCase()}</span></strong>
        <span>${formatoFecha(r.fechaHora)}</span>
      </div>`;
    if (r.estado === "CONFIRMADA" && new Date(r.fechaHora).getTime() > ahora) {
      const b = document.createElement("button");
      b.className = "peligro chico";
      b.textContent = "Cancelar";
      b.onclick = () => cancelar(r.reservaId, b);
      li.appendChild(b);
    }
    lista.appendChild(li);
  }
}

async function cancelar(reservaId, boton) {
  if (!confirm("¿Cancelar esta reserva?")) return;
  boton.disabled = true;
  try {
    await api("DELETE", `/reservas/${encodeURIComponent(reservaId)}`, { userId: estado.usuario });
    avisar("Reserva cancelada");
  } catch (e) {
    avisar(e.message, true);
    boton.disabled = false;
  }
  await cargarMisReservas();
  await cargarHorarios();
}

async function suscribir() {
  try {
    const r = await api("POST", "/suscripciones", { userId: estado.usuario });
    avisar(r.estado === "CONFIRMADA" ? "Ya recibes las confirmaciones por correo" : "Te mandamos un correo para confirmar la suscripcion");
  } catch (e) {
    avisar(e.message, true);
  }
}

function init() {
  const hoy = new Date();
  const max = new Date();
  max.setDate(max.getDate() + 30);
  $("fecha").value = fechaLocal(hoy);
  $("fecha").min = fechaLocal(hoy);
  $("fecha").max = fechaLocal(max);

  $("form-usuario").onsubmit = (e) => {
    e.preventDefault();
    iniciarSesion($("correo").value);
  };
  $("cancha").onchange = cargarHorarios;
  $("fecha").onchange = cargarHorarios;
  $("btn-reservar").onclick = reservar;
  $("btn-recargar").onclick = cargarMisReservas;
  $("btn-suscribir").onclick = suscribir;

  if (!API) {
    avisar("Falta configurar la URL de la API (config.js)", true);
    return;
  }

  let guardado = null;
  try { guardado = localStorage.getItem("fieldres-correo"); } catch {}
  if (guardado) iniciarSesion(guardado);
}

init();
