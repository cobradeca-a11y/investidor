from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
import main
from processamento import estrategia
import banco.db as db
from servicos import agendador
from sistema import observabilidade

app = FastAPI(title="FIIA API", version="1.0")

# Iniciar o Funcionário Digital (Rotinas em Segundo Plano)
agendador.iniciar_agendador_background()

# Servir a interface web
app.mount("/web", StaticFiles(directory="static"), name="static")

# Permitir acesso do celular/PWA
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/web/index.html")

@app.get("/api/radar")
def get_radar():
    try:
        vencedores = estrategia.radar_oportunidades()

        observabilidade.registrar_evento(
            "INFO",
            "api.radar",
            "Radar executado com sucesso",
            contexto={
                "quantidade_oportunidades": len(vencedores)
            }
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
            contexto={
                "endpoint": "/api/radar"
            }
        )

        # Nunca derrubar o frontend com traceback cru
        return {
            "status": "erro",
            "oportunidades": [],
            "quantidade": 0,
            "mensagem": "Falha controlada ao executar radar.",
            "detalhe": str(e),
        }

@app.get("/api/analisar/{ticker}")
def analisar_fundo(ticker: str):
    ticker = ticker.upper()

    try:
        dados = db.get_by_ticker("indicadores", ticker)

        if not dados:
            from coleta import api_fundamentus
            dados = api_fundamentus.coletar_fii(ticker)

        observabilidade.registrar_evento(
            "INFO",
            "api.analisar",
            "Análise executada",
            ticker=ticker,
        )

        return {
            "status": "ok",
            "ticker": ticker,
            "dados": dados,
        }

    except Exception as e:
        observabilidade.registrar_erro(
            "api.analisar",
            e,
            ticker=ticker,
            contexto={
                "endpoint": "/api/analisar/{ticker}"
            }
        )

        return {
            "status": "erro",
            "ticker": ticker,
            "mensagem": "Falha controlada ao analisar ativo.",
            "detalhe": str(e),
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
