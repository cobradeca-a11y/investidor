from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
import main
from processamento import estrategia
import banco.db as db
from servicos import agendador

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
        # Executa o radar de oportunidades
        vencedores = estrategia.radar_oportunidades()
        return {"oportunidades": vencedores}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analisar/{ticker}")
def analisar_fundo(ticker: str):
    ticker = ticker.upper()
    try:
        # Puxa dados do banco local (cache) ou coleta se não existir
        # Aqui simplificamos retornando os indicadores do banco
        dados = db.get_by_ticker("indicadores", ticker)
        if not dados:
            from coleta import api_fundamentus
            dados = api_fundamentus.coletar_fii(ticker)
            
        return dados
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
