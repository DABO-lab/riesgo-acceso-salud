/* Dashboard de riesgo de acceso a la salud.
   Lee los resultados de cada corte (datos/<fecha>/) que publica GitHub Actions y consulta
   en vivo el estado de la última ejecución del pipeline en la API pública de GitHub. */
"use strict";

const REPO = "DABO-lab/riesgo-acceso-salud";
const WORKFLOW = "pipeline_mensual.yml";
const NIVELES = ["Bajo", "Medio", "Alto", "Muy alto"];
const POR_PAGINA = 25;

const fmtEntero = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const fmt1 = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmtPct = (x, d = 1) => (x == null || isNaN(x) ? "—" : `${(x * 100).toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d })} %`);
const fmtFecha = (iso) => new Date(iso + (iso.length === 10 ? "T12:00:00" : "")).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
const css = (v) => getComputedStyle(document.querySelector(".viz-root")).getPropertyValue(v).trim();
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const titulo = (s) => String(s ?? "").toLowerCase().replace(/(^|[\s\-(.])(\p{L})/gu, (m, a, b) => a + b.toUpperCase());

const estado = {
  corte: null, municipios: [], datos: {}, filtrados: [],
  filtros: { dpto: "", nivel: "", grupo: "", eps: "", texto: "" },
  colorPor: "nivel", orden: { k: "ranking_riesgo", dir: 1 }, pagina: 0, seleccionado: null,
};
let mapa, capaPuntos, marcadores = new Map();

/* ---------- Carga de datos ---------- */
function parseCSV(texto) {
  texto = texto.replace(/^﻿/, "");
  const filas = []; let fila = [], campo = "", comillas = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (comillas) {
      if (c === '"' && texto[i + 1] === '"') { campo += '"'; i++; }
      else if (c === '"') comillas = false;
      else campo += c;
    } else if (c === '"') comillas = true;
    else if (c === ",") { fila.push(campo); campo = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && texto[i + 1] === "\n") i++;
      fila.push(campo); filas.push(fila); fila = []; campo = "";
    } else campo += c;
  }
  if (campo || fila.length) { fila.push(campo); filas.push(fila); }
  const cab = filas.shift();
  return filas.filter((f) => f.length === cab.length).map((f) => {
    const o = {};
    cab.forEach((k, i) => {
      const v = f[i];
      if (v === "True" || v === "False") o[k] = v === "True";
      else if (v !== "" && !isNaN(v) && !/^0\d/.test(v)) o[k] = Number(v);
      else o[k] = v;
    });
    return o;
  });
}

async function obtener(ruta, tipo) {
  const r = await fetch(ruta, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${ruta}: ${r.status}`);
  return tipo === "csv" ? parseCSV(await r.text()) : r.json();
}

async function cargarCorte(corte) {
  const base = `datos/${corte.fecha}/`;
  const tiene = new Set(corte.archivos);
  const pedir = async (nombre) => (tiene.has(nombre) ? obtener(base + nombre, nombre.endsWith(".csv") ? "csv" : "json") : null);
  const nombres = ["municipios_riesgo.csv", "resumen_departamentos.csv", "resumen_eps.csv", "perfiles_grupos.csv",
    "comparacion_modelos.csv", "calidad.json", "monitoreo.json", "metadatos_corte.json", "metricas_indice.json", "equidad.json",
    "contraste_noticias.json", "noticias.json", "vulnerabilidad.json", "fichas_municipios.json", "validacion_ia.json"];
  const res = await Promise.all(nombres.map(pedir));
  const d = Object.fromEntries(nombres.map((n, i) => [n.replace(/\.(csv|json)$/, ""), res[i]]));
  d.municipios_riesgo.forEach((m) => { m.cod_mpio = String(m.cod_mpio).padStart(5, "0"); });
  return d;
}

/* ---------- Utilidades de color ---------- */
const colorNivel = (n) => css(`--nivel-${NIVELES.indexOf(n) + 1}`) || css("--tinta-3");
const colorGrupo = (g) => css(`--grupo-${g}`) || css("--tinta-3");
const colorDe = (m) => (estado.colorPor === "nivel" ? colorNivel(m.nivel_riesgo) : colorGrupo(m.grupo));
const chipNivel = (n) => `<span class="chip"><i style="background:${colorNivel(n)}"></i>${esc(n)}</span>`;
const icono = (tipo) => `<span class="icono ${tipo}" aria-hidden="true">${{ ok: "✓", alerta: "!", critico: "✕", neutro: "…" }[tipo]}</span>`;
const pctTexto = (x) => fmtPct(x, 0);

/* ---------- Tooltip ---------- */
const tip = () => $("#tooltip");
function mostrarTip(html, ev) {
  const t = tip(); t.innerHTML = html; t.hidden = false;
  const x = ev.clientX + 14, y = ev.clientY + 14, w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = `${Math.min(x, innerWidth - w - 8)}px`;
  t.style.top = `${y + h > innerHeight - 8 ? ev.clientY - h - 10 : y}px`;
}
const ocultarTip = () => { tip().hidden = true; };

/* ---------- Estado del corte y de la ejecución ---------- */
function pintarEstado() {
  const { calidad, monitoreo } = estado.datos;
  const criticos = calidad.filter((c) => c.critico);
  const fallan = calidad.filter((c) => !c.ok);
  const fallanCrit = fallan.filter((c) => c.critico);
  const tipoC = fallanCrit.length ? "critico" : fallan.length ? "alerta" : "ok";
  $("#estado-calidad").innerHTML = `${icono(tipoC)}<div><strong>${calidad.length - fallan.length} de ${calidad.length} validaciones superadas</strong>
    <span>${fallan.length ? `Revisar: ${fallan.map((c) => esc(c.chequeo)).join(", ")}` : `Incluye ${criticos.length} reglas críticas de calidad de datos`}</span></div>`;

  if (monitoreo && monitoreo.fecha_anterior) {
    const al = monitoreo.alertas || [];
    const tipoM = monitoreo.reentrenar ? "critico" : al.length ? "alerta" : "ok";
    $("#estado-monitoreo").innerHTML = `${icono(tipoM)}<div><strong>${monitoreo.reentrenar ? "Se recomienda reentrenar" : al.length ? `${al.length} alerta(s) de monitoreo` : "Datos y modelo estables"}</strong>
      <span>Frente al corte del ${fmtFecha(monitoreo.fecha_anterior)}: ${fmtPct(monitoreo.pct_municipios_cambian_nivel)} de municipios cambian de nivel</span></div>`;
  } else {
    $("#estado-monitoreo").innerHTML = `${icono("neutro")}<div><strong>Primer corte</strong><span>No hay corte anterior con qué comparar</span></div>`;
  }
}

async function pintarEjecucion() {
  const caja = $("#estado-ejecucion");
  const enlace = `https://github.com/${REPO}/actions/workflows/${WORKFLOW}`;
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`, { cache: "no-cache" });
    if (!r.ok) throw new Error(r.status);
    const run = (await r.json()).workflow_runs?.[0];
    if (!run) throw new Error("sin ejecuciones");
    const cuando = new Date(run.created_at).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
    let tipo = "neutro", txt = "En ejecución…", det = `Iniciada el ${cuando}. El tablero se actualizará al terminar.`;
    if (run.status === "completed") {
      if (run.conclusion === "success") { tipo = "ok"; txt = "Última ejecución del pipeline exitosa"; det = cuando; }
      else { tipo = "critico"; txt = "La última ejecución falló"; det = `${cuando}. Se muestra el último corte válido.`; }
    }
    caja.innerHTML = `${icono(tipo)}<div><strong>${txt}</strong><span>${esc(det)} · <a href="${run.html_url}" target="_blank" rel="noopener">ver en GitHub</a></span></div>`;
    if (run.status !== "completed") setTimeout(pintarEjecucion, 60000);
  } catch {
    caja.innerHTML = `${icono("neutro")}<div><strong>Estado de la ejecución no disponible</strong><span><a href="${enlace}" target="_blank" rel="noopener">Consultar en GitHub Actions</a></span></div>`;
  }
}

/* ---------- Filtros ---------- */
function llenarFiltros() {
  const ms = estado.municipios;
  const opciones = (sel, valores, etiqueta = (v) => v) => {
    const s = $(sel), actual = s.value;
    s.length = 1;
    valores.forEach((v) => s.add(new Option(etiqueta(v), v)));
    s.value = valores.map(String).includes(actual) ? actual : "";
  };
  opciones("#f-dpto", [...new Set(ms.map((m) => m.dpto))].sort((a, b) => a.localeCompare(b, "es")), titulo);
  opciones("#f-nivel", NIVELES.filter((n) => ms.some((m) => m.nivel_riesgo === n)));
  const grupos = [...new Map(ms.map((m) => [m.grupo, m.nombre_grupo])).entries()].sort((a, b) => a[0] - b[0]);
  opciones("#f-grupo", grupos.map((g) => String(g[0])), (g) => grupos.find((x) => String(x[0]) === g)[1]);
  const eps = Object.entries(ms.reduce((a, m) => ((a[m.eps_principal] = (a[m.eps_principal] || 0) + 1), a), {}))
    .sort((a, b) => b[1] - a[1]).map((e) => e[0]);
  opciones("#f-eps", eps);
  Object.assign(estado.filtros, { dpto: $("#f-dpto").value, nivel: $("#f-nivel").value, grupo: $("#f-grupo").value, eps: $("#f-eps").value });
}

const sinTildes = (s) => String(s).normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
function aplicarFiltros() {
  const f = estado.filtros, q = sinTildes(f.texto.trim());
  estado.filtrados = estado.municipios.filter((m) =>
    (!f.dpto || m.dpto === f.dpto) && (!f.nivel || m.nivel_riesgo === f.nivel) &&
    (!f.grupo || String(m.grupo) === f.grupo) && (!f.eps || m.eps_principal === f.eps) &&
    (!q || sinTildes(m.nom_mpio).includes(q)));
  estado.pagina = 0;
  $("#conteo").textContent = `${fmtEntero.format(estado.filtrados.length)} de ${fmtEntero.format(estado.municipios.length)} municipios`;
  pintarKPIs(); pintarMapa(); pintarDistribucion(); pintarTabla(); pintarDepartamentos();
}

/* ---------- KPIs ---------- */
function pintarKPIs() {
  const ms = estado.filtrados;
  const afil = ms.reduce((s, m) => s + m.afiliados, 0);
  const muy = ms.filter((m) => m.nivel_riesgo === "Muy alto");
  const afilMuy = muy.reduce((s, m) => s + m.afiliados, 0);
  const interv = afil ? ms.reduce((s, m) => s + m.afiliados * m.pct_intervenidas, 0) / afil : null;
  const indice = afil ? ms.reduce((s, m) => s + m.afiliados * m.indice_riesgo, 0) / afil : null;
  const epsPrinInt = ms.filter((m) => m.eps_principal_intervenida).length;
  const filtrado = estado.filtrados.length !== estado.municipios.length;
  const k = (etq, val, det) => `<div class="kpi"><div class="etq">${etq}</div><div class="val">${val}</div><div class="det">${det}</div></div>`;
  $("#kpis").innerHTML =
    k("Municipios", fmtEntero.format(ms.length), filtrado ? "según los filtros" : "con datos completos en el corte") +
    k("Afiliados", afil >= 1e6 ? `${fmt1.format(afil / 1e6)} M` : fmtEntero.format(afil), "contributivo + subsidiado (BDUA)") +
    k("Municipios en riesgo muy alto", fmtEntero.format(muy.length), `${fmtEntero.format(afilMuy)} afiliados`) +
    k("Afiliados en EPS intervenidas", interv == null ? "—" : fmtPct(interv), `${(estado.datos.metadatos_corte?.eps_intervenidas?.lista || []).length} EPS bajo medida de la Supersalud`) +
    k("EPS principal intervenida", fmtEntero.format(epsPrinInt), `municipios (${fmtPct(ms.length ? epsPrinInt / ms.length : null, 0)})`) +
    k("Índice promedio ponderado", indice == null ? "—" : fmt1.format(indice), "0 = menor riesgo · 100 = mayor");
}

/* ---------- Mapa ---------- */
const vistaPais = () => mapa.fitBounds([[-4.3, -79.1], [12.6, -66.8]], { padding: [10, 10] });
const rangoTexto = (r) => (Array.isArray(r) ? `${pctTexto(r[0])} y ${pctTexto(r[1])}` : esc(r));
function iniciarMapa() {
  mapa = L.map("mapa", { zoomControl: true, preferCanvas: true, attributionControl: true, zoomSnap: 0.25 });
  vistaPais();
  const oscuro = matchMedia("(prefers-color-scheme: dark)").matches;
  // Mapa base gris de Esri (sin API key); en modo oscuro, su versión oscura
  const base = oscuro ? "Dark_Gray_Base" : "Light_Gray_Base";
  L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${base}/MapServer/tile/{z}/{y}/{x}`, {
    attribution: "Mapa base &copy; Esri, HERE, Garmin, &copy; colaboradores de OpenStreetMap",
    maxZoom: 12, minZoom: 4,
  }).addTo(mapa);
  capaPuntos = L.layerGroup().addTo(mapa);
}

function crearMarcadores() {
  capaPuntos.clearLayers(); marcadores.clear();
  const sup = css("--superficie");
  [...estado.municipios].sort((a, b) => b.afiliados - a.afiliados).forEach((m) => {
    if (typeof m.latitud !== "number" || typeof m.longitud !== "number") return;
    const c = L.circleMarker([m.latitud, m.longitud], {
      radius: 2.5 + Math.sqrt(m.afiliados) / 170, weight: 1, color: sup, fillColor: colorDe(m), fillOpacity: 0.9,
    });
    c.on("mouseover", (e) => { c.setStyle({ weight: 2, color: css("--tinta") }); mostrarTip(htmlTip(m), e.originalEvent); });
    c.on("mousemove", (e) => mostrarTip(htmlTip(m), e.originalEvent));
    c.on("mouseout", () => { c.setStyle({ weight: 1, color: sup }); ocultarTip(); });
    c.on("click", () => seleccionar(m, false));
    marcadores.set(m.cod_mpio, c);
  });
}

const htmlTip = (m) => `<b>${esc(titulo(m.nom_mpio))}</b><span class="t2">${esc(titulo(m.dpto))}</span><br>
  Índice <b style="display:inline">${fmt1.format(m.indice_riesgo)}</b> · ${esc(m.nivel_riesgo)} · puesto ${m.ranking_riesgo}<br>
  <span class="t2">${fmtEntero.format(m.afiliados)} afiliados · ${pctTexto(m.pct_intervenidas)} en EPS intervenidas</span>`;

function pintarMapa() {
  const visibles = new Set(estado.filtrados.map((m) => m.cod_mpio));
  marcadores.forEach((c, cod) => {
    const m = estado.municipios.find((x) => x.cod_mpio === cod);
    c.setStyle({ fillColor: colorDe(m) });
    if (visibles.has(cod)) { if (!capaPuntos.hasLayer(c)) capaPuntos.addLayer(c); }
    else capaPuntos.removeLayer(c);
  });
  // Reordena para que los pequeños queden encima
  [...estado.filtrados].sort((a, b) => a.afiliados - b.afiliados).forEach((m) => marcadores.get(m.cod_mpio)?.bringToFront());
  const pts = estado.filtrados.filter((m) => typeof m.latitud === "number").map((m) => [m.latitud, m.longitud]);
  if (estado.filtros.dpto && pts.length) mapa.fitBounds(pts, { padding: [30, 30], maxZoom: 9 });
  else if (!estado.filtros.dpto) vistaPais();
  pintarLeyenda();
}

function pintarLeyenda() {
  const items = estado.colorPor === "nivel"
    ? NIVELES.map((n) => [colorNivel(n), n])
    : estado.datos.perfiles_grupos.map((g) => [colorGrupo(g.grupo), `${g.nombre} — ${g.descripcion}`]);
  $("#leyenda-mapa").innerHTML = items.map(([c, t]) => `<span><i style="background:${c}"></i>${esc(t)}</span>`).join("");
}

/* ---------- Barras horizontales genéricas ---------- */
function barras(cont, filas, { max, fmt, alClic, color } = {}) {
  const mx = (max ?? Math.max(...filas.map((f) => f.v), 0)) || 1;
  cont.innerHTML = filas.map((f, i) => `<div class="fila-barra ${alClic ? "clic" : ""} ${f.sel ? "sel" : ""}" data-i="${i}">
    <span class="nom" title="${esc(f.nombre)}">${esc(f.nombre)}</span>
    <span class="pista"><span class="relleno" style="display:block;width:${(f.v / mx) * 100}%;${color ? `background:${color(f)}` : ""}"></span></span>
    <span class="v">${fmt ? fmt(f.v) : f.v}</span></div>`).join("");
  cont.querySelectorAll(".fila-barra").forEach((el) => {
    const f = filas[+el.dataset.i];
    el.addEventListener("mousemove", (e) => f.tip && mostrarTip(f.tip, e));
    el.addEventListener("mouseleave", ocultarTip);
    if (alClic) el.addEventListener("click", () => alClic(f));
  });
}

function pintarDistribucion() {
  const ms = estado.filtrados;
  const filas = NIVELES.map((n) => {
    const sub = ms.filter((m) => m.nivel_riesgo === n);
    const afil = sub.reduce((s, m) => s + m.afiliados, 0);
    return { nombre: n, v: sub.length, nivel: n, sel: estado.filtros.nivel === n,
      tip: `<b>${n}</b>${fmtEntero.format(sub.length)} municipios<br><span class="t2">${fmtEntero.format(afil)} afiliados</span>` };
  });
  barras($("#dist-niveles"), filas, {
    fmt: fmtEntero.format, color: (f) => colorNivel(f.nivel),
    alClic: (f) => { $("#f-nivel").value = estado.filtros.nivel === f.nivel ? "" : f.nivel; $("#f-nivel").dispatchEvent(new Event("change")); },
  });
}

function pintarDepartamentos() {
  const filas = [...estado.datos.resumen_departamentos].sort((a, b) => b.indice_ponderado - a.indice_ponderado).map((d) => ({
    nombre: titulo(d.dpto), dpto: d.dpto, v: d.indice_ponderado, sel: estado.filtros.dpto === d.dpto,
    tip: `<b>${esc(titulo(d.dpto))}</b>Índice ponderado ${fmt1.format(d.indice_ponderado)}<br>
      <span class="t2">${d.municipios} municipios · ${d.municipios_muy_alto} en muy alto<br>${fmtEntero.format(d.afiliados)} afiliados · ${pctTexto(d.pct_intervenidas)} en EPS intervenidas</span>`,
  }));
  barras($("#barras-dptos"), filas, {
    max: 100, fmt: fmt1.format,
    alClic: (f) => { $("#f-dpto").value = estado.filtros.dpto === f.dpto ? "" : f.dpto; $("#f-dpto").dispatchEvent(new Event("change")); },
  });
}

function pintarEPS() {
  const top = estado.datos.resumen_eps.slice(0, 15);
  const filas = top.map((e) => ({
    nombre: `${e.eps}${e.eps_intervenida ? " · intervenida" : ""}`, v: e.afiliados, interv: e.eps_intervenida,
    tip: `<b>${esc(e.eps)}</b>${fmtEntero.format(e.afiliados)} afiliados (${fmtPct(e.pct_nacional)} del país)<br><span class="t2">${e.eps_intervenida ? "Bajo medida de intervención de la Supersalud" : "No intervenida"}</span>`,
  }));
  barras($("#barras-eps"), filas, {
    fmt: (v) => `${fmt1.format(v / 1e6)} M`,
    color: (f) => (f.interv ? css("--nivel-3") : css("--barra")),
  });
  $("#barras-eps").insertAdjacentHTML("beforeend",
    `<div class="leyenda"><span><i style="background:${css("--nivel-3")}"></i>Intervenida por la Supersalud</span><span><i style="background:${css("--barra")}"></i>No intervenida</span></div>`);
}

/* ---------- Ranking ---------- */
function ordenar(lista) {
  const { k, dir } = estado.orden;
  return [...lista].sort((a, b) => {
    const x = a[k], y = b[k];
    return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "es")) * dir;
  });
}

function pintarTabla() {
  const lista = ordenar(estado.filtrados);
  const paginas = Math.max(1, Math.ceil(lista.length / POR_PAGINA));
  estado.pagina = Math.min(estado.pagina, paginas - 1);
  const trozo = lista.slice(estado.pagina * POR_PAGINA, (estado.pagina + 1) * POR_PAGINA);
  $("#tabla-ranking tbody").innerHTML = trozo.map((m) => `<tr data-cod="${m.cod_mpio}" class="${estado.seleccionado === m.cod_mpio ? "sel" : ""}">
    <td class="num">${m.ranking_riesgo}</td><td>${esc(titulo(m.nom_mpio))}</td><td>${esc(titulo(m.dpto))}</td>
    <td class="num">${fmt1.format(m.indice_riesgo)}</td><td>${chipNivel(m.nivel_riesgo)}</td>
    <td class="num">${fmtEntero.format(m.afiliados)}</td><td class="num">${pctTexto(m.pct_intervenidas)}</td>
    <td class="num">${fmt1.format(m.ips_x_10mil)}</td><td>${esc(m.eps_principal)}${m.eps_principal_intervenida ? " <span class=\"nota\">(interv.)</span>" : ""}</td>
    <td class="num">${pctTexto(m.prob_top10)}<span class="mini-barra"><b style="width:${m.prob_top10 * 100}%"></b></span></td></tr>`).join("")
    || `<tr><td colspan="10" class="vacio">Ningún municipio cumple los filtros.</td></tr>`;
  $("#pag-info").textContent = `Página ${estado.pagina + 1} de ${paginas}`;
  $("#pag-ant").disabled = estado.pagina === 0;
  $("#pag-sig").disabled = estado.pagina >= paginas - 1;
  document.querySelectorAll("#tabla-ranking th").forEach((th) => {
    th.classList.toggle("orden-asc", th.dataset.k === estado.orden.k && estado.orden.dir === 1);
    th.classList.toggle("orden-desc", th.dataset.k === estado.orden.k && estado.orden.dir === -1);
  });
}

function descargarCSV() {
  const cols = Object.keys(estado.municipios[0]);
  const q = (v) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v);
  const txt = "﻿" + [cols.join(","), ...ordenar(estado.filtrados).map((m) => cols.map((c) => q(m[c])).join(","))].join("\n");
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(new Blob([txt], { type: "text/csv;charset=utf-8" })),
    download: `municipios_riesgo_${estado.corte.fecha}_filtrado.csv`,
  });
  a.click(); URL.revokeObjectURL(a.href);
}

/* ---------- Detalle ---------- */
function seleccionar(m, centrar = true) {
  estado.seleccionado = m.cod_mpio;
  const comps = [["Dependencia de EPS intervenidas", "comp_dependencia"], ["Baja oferta de IPS", "comp_oferta"],
    ["Concentración de la afiliación", "comp_concentracion"], ["Ruralidad", "comp_ruralidad"], ["Régimen subsidiado", "comp_subsidiado"]];
  $("#detalle").innerHTML = `<h2>Detalle del municipio</h2>
    <p class="det-titulo">${esc(titulo(m.nom_mpio))}</p>
    <p class="det-sub">${esc(titulo(m.dpto))} · DIVIPOLA ${m.cod_mpio} · ${esc(m.nombre_grupo)}</p>
    <div class="det-indice"><span class="n">${fmt1.format(m.indice_riesgo)}</span>${chipNivel(m.nivel_riesgo)}<span class="nota">puesto ${m.ranking_riesgo} de ${estado.municipios.length}</span></div>
    <dl class="det-lista">
      <dt>Afiliados</dt><dd>${fmtEntero.format(m.afiliados)}</dd>
      <dt>En EPS intervenidas</dt><dd>${fmtPct(m.pct_intervenidas)}</dd>
      <dt>EPS principal</dt><dd>${esc(m.eps_principal)} (${pctTexto(m.pct_eps_principal)})${m.eps_principal_intervenida ? " · intervenida" : ""}</dd>
      <dt>Número de EPS</dt><dd>${m.n_eps}</dd>
      <dt>Sedes de IPS</dt><dd>${fmtEntero.format(m.sedes_ips)} (${fmtEntero.format(m.sedes_ips_publicas)} públicas)</dd>
      <dt>IPS por 10.000 afiliados</dt><dd>${fmt1.format(m.ips_x_10mil)}</dd>
      <dt>Rural · subsidiado</dt><dd>${pctTexto(m.pct_rural)} · ${pctTexto(m.pct_subsidiado)}</dd>
      <dt>Prob. de estar en el 10 % más alto</dt><dd>${pctTexto(m.prob_top10)}</dd>
      ${(() => { const v = (estado.datos.vulnerabilidad?.por_municipio || []).find((x) => x.cod_mpio === m.cod_mpio);
        return v ? `<dt>Pobreza multidimensional (DANE 2018)</dt><dd>${v.ipm == null ? "—" : fmt1.format(v.ipm) + " %"}</dd><dt>Municipio PDET</dt><dd>${v.pdet ? "Sí" : "No"}</dd>` : ""; })()}
    </dl>
    <div class="componentes"><div class="rotulo">Componentes del índice (percentil 0–100)</div><div class="barras-h" id="det-comp"></div></div>`;
  barras($("#det-comp"), comps.map(([n, k]) => ({ nombre: n, v: m[k], tip: `<b>${n}</b>Percentil ${fmt1.format(m[k])}` })), { max: 100, fmt: (v) => fmtEntero.format(v) });
  document.querySelectorAll("#tabla-ranking tbody tr").forEach((tr) => tr.classList.toggle("sel", tr.dataset.cod === m.cod_mpio));
  const c = marcadores.get(m.cod_mpio);
  if (c && centrar) { mapa.setView(c.getLatLng(), Math.max(mapa.getZoom(), 8)); }
  if (c) { c.bringToFront(); c.setStyle({ weight: 3, color: css("--tinta") }); setTimeout(() => c.setStyle({ weight: 1, color: css("--superficie") }), 1600); }
}

/* ---------- Grupos, calidad, monitoreo, equidad, método ---------- */
function pintarGrupos() {
  $("#grupos").innerHTML = estado.datos.perfiles_grupos.map((g) => `<div class="grupo">
    <h3><i style="background:${colorGrupo(g.grupo)}"></i>${esc(g.nombre)}</h3>
    <p>${esc(g.descripcion.charAt(0).toUpperCase() + g.descripcion.slice(1))}.</p>
    <div class="cifras"><span><b>${fmtEntero.format(g.municipios)}</b> municipios</span><span><b>${fmtPct(g.pct_afiliados, 0)}</b> de los afiliados</span>
      <span>Índice promedio <b>${fmt1.format(g.indice_promedio)}</b></span><span><b>${pctTexto(g.pct_intervenidas)}</b> en EPS intervenidas</span>
      <span><b>${fmt1.format(g.ips_x_10mil)}</b> IPS × 10 mil</span><span><b>${pctTexto(g.pct_rural)}</b> rural</span></div></div>`).join("") +
    `<p class="nota">Se compararon ${estado.datos.comparacion_modelos?.length ?? "varios"} modelos de clustering (K-means, jerárquico, etc.) y se eligió el que cumplió la regla de selección; todos quedan registrados en MLflow.</p>`;
}

function pintarCalidad() {
  const st = (c) => (c.ok ? `<span class="st ok">${icono("ok")} Cumple</span>`
    : `<span class="st ${c.critico ? "critico" : "alerta"}">${icono(c.critico ? "critico" : "alerta")} No cumple</span>`);
  $("#tabla-calidad").innerHTML = `<thead><tr><th>Regla</th><th>Resultado</th><th>Detalle</th></tr></thead><tbody>${
    estado.datos.calidad.map((c) => `<tr><td>${esc(c.chequeo.replace(/_/g, " "))}${c.critico ? "" : ' <span class="nota">(no crítica)</span>'}</td><td>${st(c)}</td><td class="nota">${esc(c.detalle)}</td></tr>`).join("")}</tbody>`;
}

function pintarMonitoreo() {
  const mo = estado.datos.monitoreo;
  if (!mo || !mo.psi) { $("#monitoreo").innerHTML = '<p class="vacio">Es el primer corte: no hay contra qué comparar.</p>'; return; }
  const nombres = { pct_intervenidas: "% en EPS intervenidas", hhi: "Concentración (HHI)", ips_x_10mil: "IPS por 10.000", pct_rural: "% rural", pct_subsidiado: "% subsidiado", indice_riesgo: "Índice de riesgo" };
  const lectura = (p) => (p < 0.1 ? `<span class="st ok">${icono("ok")} Estable</span>` : p < 0.25 ? `<span class="st alerta">${icono("alerta")} Cambio moderado</span>` : `<span class="st critico">${icono("critico")} Cambio fuerte</span>`);
  $("#monitoreo").innerHTML = `<p class="nota">Comparación con el corte del ${fmtFecha(mo.fecha_anterior)}. PSI &lt; 0,10 = estable; 0,10–0,25 = moderado; &gt; 0,25 = fuerte.</p>
    <div class="tabla-envoltura"><table class="tabla"><thead><tr><th>Variable</th><th class="num">PSI</th><th>Lectura</th></tr></thead><tbody>
    ${Object.entries(mo.psi).map(([k, v]) => `<tr><td>${nombres[k] || k}</td><td class="num">${v.toFixed(4).replace(".", ",")}</td><td>${lectura(v)}</td></tr>`).join("")}
    </tbody></table></div>
    <dl class="det-lista" style="margin-top:12px">
      <dt>Variación del total de afiliados</dt><dd>${fmtPct(mo.variacion_total_afiliados, 2)}</dd>
      <dt>Municipios que cambian de nivel</dt><dd>${fmtPct(mo.pct_municipios_cambian_nivel)}</dd>
      <dt>Municipios que cambian de grupo</dt><dd>${fmtPct(mo.pct_municipios_cambian_grupo)}</dd>
      ${mo.ari_modelo_anterior_vs_nuevo != null ? `<dt>Acuerdo modelo anterior vs. nuevo (ARI)</dt><dd>${mo.ari_modelo_anterior_vs_nuevo.toFixed(3).replace(".", ",")}</dd>` : ""}
      <dt>¿Reentrenar?</dt><dd>${mo.reentrenar ? "Sí" : "No"}</dd>
    </dl>
    ${(mo.alertas || []).length ? `<ul class="lista-alertas">${mo.alertas.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}`;
}

function pintarEquidad() {
  const eq = estado.datos.equidad;
  if (!eq) { $("#equidad").innerHTML = '<p class="vacio">Este corte no incluye la auditoría de equidad.</p>'; return; }
  $("#equidad").innerHTML = `${(eq.alertas || []).length ? `<ul class="lista-alertas">${eq.alertas.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
    <div class="tabla-envoltura"><table class="tabla"><thead><tr><th>Tamaño (afiliados)</th><th class="num">Municipios</th><th class="num">Índice prom.</th><th class="num">% muy alto</th><th class="num">IPS × 10 mil</th></tr></thead><tbody>
    ${eq.por_tamano.map((b) => `<tr><td>${esc(b.banda)}</td><td class="num">${b.municipios}</td><td class="num">${fmt1.format(b.indice_promedio)}</td><td class="num">${pctTexto(b.pct_muy_alto)}</td><td class="num">${fmt1.format(b.ips_x_10mil_mediana)}</td></tr>`).join("")}
    </tbody></table></div>
    ${eq.incertidumbre_top10 ? `<p class="nota" style="margin-top:10px">${eq.incertidumbre_top10.municipios} municipios tienen una probabilidad de estar en el 10 % de mayor riesgo entre ${rangoTexto(eq.incertidumbre_top10.rango)}: su posición depende de los pesos elegidos.</p>` : ""}`;
}

const TIPOS_NOTICIA = { medicamentos: "Medicamentos", cierre_servicios: "Cierre de servicios", deudas_pagos: "Deudas y pagos",
  tutelas_quejas: "Tutelas y quejas", intervencion_supersalud: "Intervención Supersalud", protesta: "Protesta", otro: "Otro" };
const GRAVEDAD = { 1: "Advertencia", 2: "Afectación", 3: "Sin atención" };
const enlaceSeguro = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");

function pintarNoticias() {
  const c = estado.datos.contraste_noticias, lista = estado.datos.noticias || [];
  const cuerpo = $("#noticias-cuerpo"), meta = $("#noticias-meta");
  if (!c || c.estado !== "ok") {
    meta.textContent = "";
    cuerpo.innerHTML = `<p class="vacio">Este corte no tiene contraste con noticias${c?.motivo ? ` (${esc(c.motivo)})` : ""}.
      El agente corre con cada ejecución del pipeline cuando la clave de Gemini está configurada.</p>`;
    return;
  }
  const vi = estado.datos.validacion_ia;
  const valida = vi?.estado === "ok"
    ? ` · Acierto de la IA frente a revisión humana: ${fmtPct(vi.relevancia.acuerdo, 0)} (${vi.revisadas} noticias)`
    : " · Validación humana de la IA: pendiente";
  meta.textContent = `Últimos ${c.ventana_dias} días · ${c.noticias_relevantes} de ${c.noticias_total} noticias relevantes · ${c.modelo_ia}${valida}`;
  const k = (etq, val, det) => `<div class="kpi"><div class="etq">${etq}</div><div class="val">${val}</div><div class="det">${det}</div></div>`;
  const co = c.correlacion || {};
  const num = (x) => (x == null ? "—" : x.toFixed(2).replace(".", ","));
  const cats = { coinciden: [], riesgo_silencioso: [], posible_punto_ciego: [] };
  (c.departamentos || []).forEach((d) => cats[d.categoria]?.push(titulo(d.dpto)));
  const caja = (t, desc, l) => `<div class="categoria"><h3>${t} (${l.length})</h3><p>${desc}</p><div class="lista">${l.length ? esc(l.join(", ")) : "Ninguno"}</div></div>`;
  const top = [...lista].filter((n) => n.relevante).sort((a, b) => b.gravedad - a.gravedad || String(b.fecha).localeCompare(String(a.fecha))).slice(0, 10);
  const tabla = (c.departamentos || []).filter((d) => d.menciones > 0).slice(0, 12);
  cuerpo.innerHTML = `<p class="informe">${esc(c.informe)}</p>
    <div class="correl">
      ${k("Noticias vs. índice de riesgo", co.suficiente ? num(co.spearman_indice) : "—", co.suficiente ? `Spearman · p = ${num(co.p_valor_indice)}` : "Pocos departamentos con noticias")}
      ${k("Noticias vs. tamaño de la población", co.suficiente ? num(co.spearman_tamano) : "—", "Control: ¿las noticias siguen solo el tamaño?")}
      ${k("Noticias sobre EPS intervenidas", fmtPct(c.pct_sobre_eps_intervenidas, 0), `${c.noticias_nacionales} noticias son nacionales (sin departamento)`)}
    </div>
    <p class="nota" style="margin:-4px 0 12px">${esc(co.lectura || "")} La correlación la calcula el código; la IA solo lee y clasifica las noticias.</p>
    <div class="categorias">
      ${caja("Coinciden", "Riesgo alto y noticias de problemas: el índice ve lo que ya está pasando.", cats.coinciden)}
      ${caja("Riesgo silencioso", "Riesgo alto sin noticias: lo que el índice busca anticipar.", cats.riesgo_silencioso)}
      ${caja("Posible punto ciego", "Noticias de problemas con riesgo bajo: revisar qué no está midiendo el índice.", cats.posible_punto_ciego)}
    </div>
    <section class="grid-2">
      <div><h3 style="font-size:13px;margin:0 0 8px">Departamentos con más noticias</h3>
        <div class="tabla-envoltura"><table class="tabla"><thead><tr><th>Departamento</th><th class="num">Índice</th><th class="num">Noticias</th><th class="num">Gravedad sumada</th></tr></thead><tbody>
        ${tabla.map((d) => `<tr><td>${esc(titulo(d.dpto))}</td><td class="num">${fmt1.format(d.indice_ponderado)}</td><td class="num">${d.menciones}</td><td class="num">${d.senal}</td></tr>`).join("") || '<tr><td colspan="4" class="vacio">Sin noticias por departamento</td></tr>'}
        </tbody></table></div></div>
      <div><h3 style="font-size:13px;margin:0 0 8px">Noticias más graves</h3>
        <ul class="lista-noticias">${top.map((n) => `<li><span class="grav">${GRAVEDAD[n.gravedad] || ""}</span>
          <a href="${esc(enlaceSeguro(n.enlace))}" target="_blank" rel="noopener noreferrer">${esc(n.titulo)}</a>
          <div class="meta">${esc(n.fuente)} · ${esc(n.fecha || "")} · ${esc(TIPOS_NOTICIA[n.tipo] || n.tipo)} · ${esc((n.departamentos || []).map(titulo).join(", ") || "Nacional")}</div></li>`).join("")}</ul></div>
    </section>`;
}

const RESULTADO = { se_cumple: ["ok", "Se cumple"], debil: ["alerta", "Relación débil"], no_se_cumple: ["critico", "No se cumple"] };

function pintarVulnerabilidad() {
  const v = estado.datos.vulnerabilidad, cuerpo = $("#vul-cuerpo");
  if (!v || v.estado !== "ok") {
    $("#vul-meta").textContent = "";
    cuerpo.innerHTML = `<p class="vacio">Este corte no tiene el cruce con vulnerabilidad${v?.motivo ? ` (${esc(v.motivo)})` : ""}.</p>`;
    return;
  }
  $("#vul-meta").textContent = `Rúbrica registrada el ${v.fecha_registro_rubrica} · DANE (IPM 2018) y ART (PDET)`;
  const num = (x) => String(x).replace(".", ",");
  const hip = Object.entries(v.hipotesis).map(([k, h]) => {
    const [cls, txt] = RESULTADO[h.resultado] || ["neutro", h.resultado];
    return `<div class="hipo"><h3>${esc(k.split("_")[0])} · ${esc(h.descripcion)}</h3>
      <span class="st ${cls}">${icono(cls)} ${txt}</span>
      <p>${esc(h.prueba)}: ${num(h.estadistico)} · p = ${num(h.p_valor)}${h.detalle ? `<br>${esc(h.detalle)}` : ""}</p>
      <p class="nota">Regla: ${esc(h.umbral)}</p></div>`;
  }).join("");
  const d = v.doble_vulnerabilidad;
  const filas = d.lista.slice(0, 12).map((m) => `<tr><td>${esc(titulo(m.nom_mpio))}</td><td>${esc(titulo(m.dpto))}</td>
    <td class="num">${fmt1.format(m.indice_riesgo)}</td><td class="num">${fmt1.format(m.ipm)} %</td><td>${m.pdet ? "Sí" : "No"}</td></tr>`).join("");
  cuerpo.innerHTML = `<p class="informe">${esc(v.informe)}</p><div class="hipotesis">${hip}</div>
    <h3 style="font-size:13px;margin:0 0 8px">Doble vulnerabilidad: ${d.municipios} municipios en el 20 % más alto de riesgo y de pobreza (${fmtEntero.format(d.afiliados)} afiliados, ${d.pdet} PDET)</h3>
    <div class="tabla-envoltura"><table class="tabla"><thead><tr><th>Municipio</th><th>Departamento</th><th class="num">Índice</th><th class="num">IPM 2018</th><th>PDET</th></tr></thead>
    <tbody>${filas}</tbody></table></div>`;
}

function pintarFichas() {
  const f = estado.datos.fichas_municipios, cuerpo = $("#fichas-cuerpo");
  if (!f || f.estado !== "ok") { $("#fichas-meta").textContent = ""; cuerpo.innerHTML = '<p class="vacio">Este corte no tiene fichas.</p>'; return; }
  $("#fichas-meta").textContent = f.redactado_por === "plantilla" ? "Armadas con plantilla" : `Redactadas por ${f.redactado_por} solo con datos del corte`;
  cuerpo.innerHTML = f.fichas.map((x) => {
    const h = x.hechos;
    const notas = [...(h.noticias_del_municipio || []), ...(h.noticias_del_departamento || [])].slice(0, 2);
    return `<div class="ficha"><h3>${h.ranking}. ${esc(h.municipio)}</h3>
      <p class="sub nota">${esc(h.departamento)} · índice ${fmt1.format(h.indice_riesgo)} · ${esc(h.nivel_riesgo)} · ${fmtEntero.format(h.afiliados)} afiliados${h.municipio_pdet ? " · PDET" : ""}</p>
      <p style="margin:0;font-size:13.5px">${esc(x.resumen)}</p>
      <ul>${(x.por_que || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
      <div class="accion"><b>Acción recomendada</b>${esc(x.accion_recomendada)}</div>
      ${(x.advertencias || []).map((a) => `<p class="adv">${esc(a)}</p>`).join("")}
      ${notas.length ? `<div class="enlaces">Noticias: ${notas.map((n) => `<a href="${esc(enlaceSeguro(n.enlace))}" target="_blank" rel="noopener noreferrer">${esc(n.fuente || "enlace")}</a>`).join(" · ")}</div>` : ""}
      <button type="button" class="boton boton-sec" style="margin-top:8px" data-cod="${esc(h.cod_mpio)}">Ver en el mapa</button></div>`;
  }).join("");
  cuerpo.querySelectorAll("button[data-cod]").forEach((b) => b.addEventListener("click", () => {
    const m = estado.municipios.find((x) => x.cod_mpio === b.dataset.cod);
    if (m) { seleccionar(m); $("#mapa").scrollIntoView({ behavior: "smooth", block: "center" }); }
  }));
}

function pintarMetodo() {
  const mi = estado.datos.metricas_indice || {}, md = estado.datos.metadatos_corte || {};
  const ei = md.eps_intervenidas || {};
  $("#metodo").innerHTML = `
    <div><h3>1. Datos</h3><p>Cada corte descarga de datos.gov.co la BDUA (afiliados por EPS y municipio), el REPS (sedes de IPS) y la DIVIPOLA. Corte del ${fmtFecha(md.fecha_corte || estado.corte.fecha)}.</p></div>
    <div><h3>2. Índice de riesgo (0–100)</h3><p>Promedio ponderado de percentiles: dependencia de EPS intervenidas (35 %), baja oferta de IPS (30 %), concentración de la afiliación (15 %), ruralidad (10 %) y régimen subsidiado (10 %). Niveles por cuantiles: 30 % Bajo, 40 % Medio, 20 % Alto y 10 % Muy alto.</p></div>
    <div><h3>3. Robustez</h3><p>Al mover los pesos al azar 500 veces, el orden de los municipios se mantiene (Spearman mediano ${mi.sens_spearman_mediana != null ? mi.sens_spearman_mediana.toFixed(2).replace(".", ",") : "—"}). Por eso se informa la probabilidad de estar en el 10 % más alto.</p></div>
    <div><h3>4. EPS intervenidas</h3><p>${esc((ei.lista || []).join(", "))}. ${ei.fuente ? `Fuente: ${esc(ei.fuente)}.` : ""}</p></div>`;
}

/* ---------- Arranque ---------- */
async function mostrarCorte(corte) {
  estado.corte = corte;
  estado.datos = await cargarCorte(corte);
  estado.municipios = estado.datos.municipios_riesgo;
  estado.seleccionado = null;
  crearMarcadores(); llenarFiltros();
  pintarEstado(); pintarGrupos(); pintarCalidad(); pintarMonitoreo(); pintarEPS(); pintarEquidad(); pintarNoticias(); pintarVulnerabilidad(); pintarFichas(); pintarMetodo();
  aplicarFiltros();
  const top = estado.municipios.find((m) => m.ranking_riesgo === 1);
  if (top) seleccionar(top, false);
}

function enlazarEventos() {
  const mapaFiltros = { "#f-dpto": "dpto", "#f-nivel": "nivel", "#f-grupo": "grupo", "#f-eps": "eps" };
  Object.entries(mapaFiltros).forEach(([sel, k]) => $(sel).addEventListener("change", (e) => { estado.filtros[k] = e.target.value; aplicarFiltros(); }));
  let t; $("#f-buscar").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { estado.filtros.texto = e.target.value; aplicarFiltros(); }, 200); });
  $("#f-limpiar").addEventListener("click", () => {
    Object.keys(mapaFiltros).forEach((s) => ($(s).value = "")); $("#f-buscar").value = "";
    estado.filtros = { dpto: "", nivel: "", grupo: "", eps: "", texto: "" }; aplicarFiltros();
  });
  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("activo", x === b));
    estado.colorPor = b.dataset.color; pintarMapa();
  }));
  document.querySelectorAll("#tabla-ranking th").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.k;
    estado.orden = { k, dir: estado.orden.k === k ? -estado.orden.dir : (["indice_riesgo", "afiliados", "pct_intervenidas", "prob_top10"].includes(k) ? -1 : 1) };
    pintarTabla();
  }));
  $("#tabla-ranking tbody").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-cod]"); if (!tr) return;
    seleccionar(estado.municipios.find((m) => m.cod_mpio === tr.dataset.cod));
    $("#mapa").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("#pag-ant").addEventListener("click", () => { estado.pagina--; pintarTabla(); });
  $("#pag-sig").addEventListener("click", () => { estado.pagina++; pintarTabla(); });
  $("#descargar").addEventListener("click", descargarCSV);
}

(async function iniciar() {
  $("#btn-actualizar").href = `https://github.com/${REPO}/actions/workflows/${WORKFLOW}`;
  $("#btn-actualizar").title = "Abre el pipeline en GitHub Actions: pulse «Run workflow» (requiere ser colaborador del repositorio)";
  $("#enlace-repo").href = `https://github.com/${REPO}`;
  try {
    const { cortes } = await obtener("datos/cortes.json", "json");
    const sel = $("#sel-corte");
    cortes.forEach((c, i) => sel.add(new Option(`${fmtFecha(c.fecha)}${i === 0 ? " (último)" : ""}`, c.fecha)));
    sel.addEventListener("change", () => mostrarCorte(cortes.find((c) => c.fecha === sel.value)));
    iniciarMapa(); enlazarEventos();
    await mostrarCorte(cortes[0]);
    pintarEjecucion();
  } catch (err) {
    console.error(err);
    $("main").innerHTML = `<div class="error-carga">No fue posible cargar los resultados (${esc(err.message)}).<br>Si está abriendo el archivo directamente, use <code>make dashboard</code> para verlo en http://localhost:8080.</div>`;
  }
})();
