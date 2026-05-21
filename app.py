from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4
import main
from acesso.autenticacao import verificar_api_key
from processamento import estrategia
import banco.db as db
from servicos import agendador
from sistema import observabilidade
from api.auditoria import router as auditoria_router
from api.carteira import router as carteira_router
from api.aprendizado import router as aprendizado_router
from api.relatorios import router as relatorios_router
from api.fnet import router as fnet_router
from api.setup_cvm import router as setup_cvm_router
from api.assistente import router as assistente_router

app = FastAPI(title="FIIA API", version="1.0")

_RADAR_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_RADAR_JOBS: dict[str, dict] = {}
_RADAR_LOCK = Lock()
_ULTIMO_RADAR: dict | None = None


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _salvar_job(job_id: str, dados: dict) -> None:
    with _RADAR_LOCK:
        atual = dict(_RADAR_JOBS.get(job_id, {}))
        atual.update(dados)
        _RADAR_JOBS[job_id] = atual


def _executar_radar_job(job_id: str) -> None:
    global _ULTIMO_RADAR
    _salvar_job(job_id, {"status": "rodando", "iniciado_em": _agora_iso()})
    try:
        vencedores = estrategia.radar_oportunidades()
        resultado = {
            "status": "ok",
            "oportunidades": vencedores,
            "quantidade": len(vencedores),
            "finalizado_em": _agora_iso(),
        }
        _ULTIMO_RADAR = resultado
        _salvar_job(job_id, {"status": "concluido", "resultado": resultado, "finalizado_em": resultado["finalizado_em"]})
        observabilidade.registrar_evento(
            "INFO",
            "api.radar.jobs",
            "Radar assincrono concluido",
            contexto={"job_id": job_id, "quantidade_oportunidades": len(vencedores)},
        )
    except Exception as erro:
        observabilidade.registrar_erro(
            "api.radar.jobs",
            erro,
            contexto={"job_id": job_id},
        )
        _salvar_job(
            job_id,
            {
                "status": "erro",
                "mensagem": "Falha controlada ao executar radar assincrono.",
                "detalhe": str(erro),
                "finalizado_em": _agora_iso(),
            },
        )

# Iniciar o Funcionário Digital (Rotinas em Segundo Plano) no evento de startup controladamente
@app.on_event("startup")
def startup_event():
    agendador.iniciar_agendador_background()

# APIs
app.include_router(auditoria_router)
app.include_router(carteira_router)
app.include_router(aprendizado_router)
app.include_router(relatorios_router)
app.include_router(fnet_router)
app.include_router(setup_cvm_router)
app.include_router(assistente_router)

# Servir a interface web
app.mount("/web", StaticFiles(directory="static"), name="static")

from config.settings import CORS_ALLOWED_ORIGINS

# Permitir acesso do celular/PWA com origens restritas e sem credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/web/index.html")

@app.get("/api/radar", dependencies=[Depends(verificar_api_key)])
def get_radar():
    try:
        vencedores = estrategia.radar_oportunidades()

        observabilidade.registrar_evento(
            "INFO",
            "api.radar",
            "Radar executado com sucesso",
            contexto={"quantidade_oportunidades": len(vencedores)},
        )

        return {
            "status": "ok",
            "oportunidades": vencedores,
            "quantidade": len(vencedores),
        }

    except Exception as e:
        observabilidade.registrar_erro(
            "api.radar",
            e,
            contexto={"endpoint": "/api/radar"},
        )
        return {
            "status": "erro",
            "oportunidades": [],
            "quantidade": 0,
            "mensagem": "Falha controlada ao executar radar.",
            "detalhe": str(e),
        }


@app.post("/api/radar/jobs", dependencies=[Depends(verificar_api_key)])
def iniciar_radar_job():
    job_id = uuid4().hex
    _salvar_job(job_id, {"job_id": job_id, "status": "pendente", "criado_em": _agora_iso()})
    _RADAR_EXECUTOR.submit(_executar_radar_job, job_id)
    return {"status": "ok", "job_id": job_id, "job_status": "pendente"}


@app.get("/api/radar/jobs/{job_id}", dependencies=[Depends(verificar_api_key)])
def consultar_radar_job(job_id: str):
    with _RADAR_LOCK:
        job = dict(_RADAR_JOBS.get(job_id, {}))
    if not job:
        raise HTTPException(status_code=404, detail="Job de radar nao encontrado.")
    return {"status": "ok", "job": job}


@app.get("/api/radar/ultimo", dependencies=[Depends(verificar_api_key)])
def ultimo_radar():
    if not _ULTIMO_RADAR:
        return {"status": "vazio", "mensagem": "Nenhum radar concluido nesta instancia."}
    return _ULTIMO_RADAR


@app.get("/api/auditoria/health")
def health_basico():
    return {"status": "ok", "servico": "fiia", "modo": "health_basico_sem_scraping"}

@app.get("/api/analisar/{ticker}")
def analisar_fundo(ticker: str):
    """
    Endpoint técnico de dados brutos.

    Não executa o pipeline oficial de decisão do FIIA.
    Usar para debug, inspeção de coleta e comparação com o veredito profissional.
    """
    ticker = ticker.upper().replace(".SA", "")

    try:
        dados = db.get_by_ticker("indicadores", ticker)
        origem = "BANCO_LOCAL"

        if not dados:
            from coleta import api_fundamentus
            dados = api_fundamentus.coletar_fii(ticker)
            origem = "FUNDAMENTUS_FALLBACK"

        observabilidade.registrar_evento(
            "INFO",
            "api.analisar",
            "Consulta de dado bruto executada",
            ticker=ticker,
            contexto={"tipo": "DADO_BRUTO_NAO_OFICIAL", "origem": origem},
        )

        return {
            "status": "ok",
            "tipo": "DADO_BRUTO_NAO_OFICIAL",
            "endpoint": "/api/analisar/{ticker}",
            "aviso": "Este endpoint retorna dados brutos de indicadores e não executa o pipeline oficial de decisão do FIIA.",
            "usar_para": ["debug", "verificacao_de_coleta", "comparacao_com_decisao_final"],
            "pipeline_oficial": "Use os endpoints de relatorios/decisao para veredito profissional com CVM-first, confiança, gates e FNET.",
            "ticker": ticker,
            "origem": origem,
            "dados": dados,
        }

    except Exception as e:
        observabilidade.registrar_erro(
            "api.analisar",
            e,
            ticker=ticker,
            contexto={"endpoint": "/api/analisar/{ticker}", "tipo": "DADO_BRUTO_NAO_OFICIAL"},
        )
        return {
            "status": "erro",
            "tipo": "DADO_BRUTO_NAO_OFICIAL",
            "ticker": ticker,
            "mensagem": "Falha controlada ao consultar dado bruto do ativo.",
            "detalhe": str(e),
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
