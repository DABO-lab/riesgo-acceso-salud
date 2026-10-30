"""API de riesgo de acceso a la salud por municipio.

Ejecutar:  make api   (o: uv run uvicorn riesgo_salud.api.main:app --port 8000)
Contrato interactivo: http://127.0.0.1:8000/docs

Endpoints
- GET  /                       página para consultar un municipio (para personas no técnicas)
- GET  /health                 el servicio está listo: datos cargados y el modelo responde
- GET  /municipios/{cod_mpio}  índice, nivel y grupo de un municipio (código DIVIPOLA)
- GET  /municipios             ranking, con filtros por departamento, nivel o nombre
- POST /predict                riesgo que tendría un municipio con ciertos indicadores
- POST /predict/batch          lo mismo para varios municipios en una petición
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as Ruta
from fastapi.responses import HTMLResponse

from .esquemas import (
    Indicadores,
    LoteIndicadores,
    Municipio,
    RespuestaLote,
    RespuestaMunicipios,
    RespuestaPrediccion,
    Salud,
)
from .servicio import Servicio, cargar_servicio

log = logging.getLogger("riesgo_salud.api")
NIVELES = "Bajo|Medio|Alto|Muy alto"


def crear_app(carpeta_resultados: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        app.state.servicio = cargar_servicio(carpeta_resultados)
        s: Servicio = app.state.servicio
        log.info("Corte %s cargado: %d municipios, modelo %s", s.corte, len(s.tabla), s.origen_modelo)
        yield

    app = FastAPI(
        title="Riesgo de acceso a la salud por municipio",
        description="Índice de riesgo (0-100), nivel y grupo de los municipios de Colombia, "
        "según su dependencia de EPS intervenidas y su oferta de IPS. Datos abiertos de datos.gov.co.",
        version="1.0.0",
        lifespan=ciclo_de_vida,
    )

    def servicio(request: Request) -> Servicio:
        return request.app.state.servicio

    def metadata(s: Servicio, inicio: float) -> dict:
        return {
            "request_id": uuid.uuid4().hex[:12],
            "corte": s.corte,
            "modelo": s.origen_modelo,
            "latencia_ms": round((time.perf_counter() - inicio) * 1000, 2),
        }

    @app.get("/health", response_model=Salud, tags=["operación"])
    def health(request: Request):
        """Readiness: los datos del corte están cargados y el modelo predice un municipio conocido."""
        s = servicio(request)
        try:
            s.modelo.predict(s.tabla[s.variables].head(1))
        except Exception as e:  # el detalle va al log, no al cliente
            log.exception("El modelo no responde")
            raise HTTPException(status_code=503, detail="El modelo no está listo") from e
        return {"estado": "ok", "corte": s.corte, "municipios": len(s.tabla), "modelo": s.origen_modelo}

    @app.get("/municipios/{cod_mpio}", response_model=Municipio, tags=["consulta"])
    def municipio(request: Request, cod_mpio: str = Ruta(pattern=r"^\d{5}$", examples=["19050"])):
        """Índice, nivel, ranking y grupo de un municipio por su código DIVIPOLA de 5 dígitos."""
        m = servicio(request).municipio(cod_mpio)
        if m is None:
            raise HTTPException(status_code=404, detail=f"No existe el municipio {cod_mpio} en el corte")
        return m

    @app.get("/municipios", response_model=RespuestaMunicipios, tags=["consulta"])
    def municipios(
        request: Request,
        dpto: str | None = Query(None, description="Departamento, por ejemplo 'Cauca' o 'ANTIOQUIA'"),
        nivel: str | None = Query(None, pattern=f"(?i)^({NIVELES})$", description=NIVELES.replace("|", ", ")),
        buscar: str | None = Query(None, min_length=3, description="Parte del nombre del municipio"),
        limite: int = Query(20, ge=1, le=1122),
    ):
        """Ranking nacional (1 = mayor riesgo), con filtros opcionales."""
        inicio, s = time.perf_counter(), servicio(request)
        total, filas = s.ranking(dpto, nivel, limite if not buscar else len(s.tabla))
        if buscar:
            from ..limpieza import normalizar_texto

            clave = normalizar_texto(buscar)
            filas = [f for f in filas if clave in normalizar_texto(f["nom_mpio"])]
            total, filas = len(filas), filas[:limite]
        return {"total": total, "municipios": filas, "metadata": metadata(s, inicio)}

    @app.post("/predict", response_model=RespuestaPrediccion, tags=["predicción"])
    def predict(request: Request, entrada: Indicadores):
        """Riesgo que tendría un municipio con estos indicadores, frente al corte de referencia.

        Sirve para escenarios: por ejemplo, ¿qué pasa con un municipio si su EPS principal sale
        de la intervención (pct_intervenidas baja) o si abre una IPS (ips_x_10mil sube)?
        """
        inicio, s = time.perf_counter(), servicio(request)
        pred = s.predecir(pd.DataFrame([entrada.model_dump()]))[0]
        return {"entrada": entrada, "prediccion": pred, "metadata": metadata(s, inicio)}

    @app.post("/predict/batch", response_model=RespuestaLote, tags=["predicción"])
    def predict_batch(request: Request, lote: LoteIndicadores):
        """Varias predicciones en una sola petición (máximo 2.000)."""
        inicio, s = time.perf_counter(), servicio(request)
        preds = s.predecir(pd.DataFrame([m.model_dump() for m in lote.municipios]))
        return {"predicciones": preds, "metadata": metadata(s, inicio)}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def inicio():
        return PAGINA

    return app


PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Riesgo de acceso a la salud por municipio</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:980px;margin:32px auto;padding:0 16px;color:#1f2328}
 h1{font-size:22px;margin-bottom:4px} p.sub{color:#59636e;margin-top:0}
 form{display:flex;gap:8px;margin:16px 0} input,select,button{font-size:15px;padding:8px}
 input{flex:1} button{cursor:pointer}
 table{border-collapse:collapse;width:100%;font-size:14px} th,td{padding:6px 8px;border-bottom:1px solid #d1d9e0;text-align:left}
 td.n{text-align:right} .Muy{color:#b42318;font-weight:600} .Alto{color:#c4320a} .Medio{color:#8a6100} .Bajo{color:#1a7f37}
 small{color:#59636e}
</style></head><body>
<h1>Riesgo de acceso a la salud por municipio</h1>
<p class="sub">Índice de 0 a 100 según la dependencia de EPS intervenidas y la oferta de IPS. <a href="/docs">Documentación de la API</a></p>
<form id="f"><input id="q" placeholder="Nombre del municipio (mínimo 3 letras) o vacío para ver el ranking">
<select id="niv"><option value="">Todos los niveles</option><option>Muy alto</option><option>Alto</option><option>Medio</option><option>Bajo</option></select>
<button>Consultar</button></form>
<table><thead><tr><th>#</th><th>Municipio</th><th>Departamento</th><th>Índice</th><th>Nivel</th>
<th>% en EPS intervenidas</th><th>IPS por 10.000</th><th>EPS principal</th></tr></thead><tbody id="t"></tbody></table>
<p><small id="m"></small></p>
<script>
async function cargar(e){ if(e) e.preventDefault();
 const p=new URLSearchParams({limite:'30'}); const q=document.getElementById('q').value.trim(); const n=document.getElementById('niv').value;
 if(q.length>=3) p.set('buscar',q); if(n) p.set('nivel',n);
 const r=await fetch('/municipios?'+p); const d=await r.json(); const t=document.getElementById('t'); t.innerHTML='';
 if(!r.ok){ t.innerHTML='<tr><td colspan="8">Consulta no válida</td></tr>'; return; }
 for(const m of d.municipios){ const tr=document.createElement('tr');
  const celdas=[m.ranking_riesgo, m.nom_mpio, m.dpto, m.indice_riesgo.toFixed(1), m.nivel_riesgo,
   (m.pct_intervenidas*100).toFixed(0)+' %', m.ips_x_10mil.toFixed(2), m.eps_principal||''];
  celdas.forEach((v,i)=>{const td=document.createElement('td'); td.textContent=v; if([0,3,5,6].includes(i)) td.className='n';
   if(i===4) td.className=v.split(' ')[0]; tr.appendChild(td);}); t.appendChild(tr);}
 document.getElementById('m').textContent=d.total+' municipios · corte '+d.metadata.corte+' · '+d.metadata.latencia_ms+' ms';}
document.getElementById('f').addEventListener('submit',cargar); cargar();
</script></body></html>"""

app = crear_app()
