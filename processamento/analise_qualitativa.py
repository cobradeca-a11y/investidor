import json
from google import genai
from config import settings
from coleta.web_search import buscar_noticias_fii
import banco.db as db

def analisar_fundo_ia(ticker: str) -> dict:
    """
    Analista Sênior FIIA: Interpreta notícias e indicadores fundamentais.
    """
    # 1. Busca indicadores no banco para dar contexto à IA
    dados_banco = db.get_by_ticker("indicadores", ticker) or {}
    fii_info = db.get_by_ticker("fiis", ticker) or {}
    
    contexto_financeiro = f"""
    Indicadores Atuais de {ticker}:
    - Setor: {fii_info.get('segmento', 'Não informado')}
    - P/VP: {dados_banco.get('pvp', 'N/A')}
    - Dividend Yield (12M): {dados_banco.get('dy_12m', 'N/A')}%
    - Vacância: {dados_banco.get('vacancia_fisica', 'N/A')}%
    - Liquidez Diária: R$ {dados_banco.get('liquidez_diaria', 0):,.2f}
    """

    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "SUA_CHAVE_AQUI":
        return {"score": 5, "resumo": "⚠️ Chave de API não configurada.", "riscos": []}

    # 2. Coleta notícias (Pode falhar por ratelimit)
    noticias_brutas = buscar_noticias_fii(ticker)
    
    # 3. Configura o Cliente (Novo SDK) com Retry Automático
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        model_id = 'gemini-2.0-flash'
        
        print(f"[ia] Analista Sênior processando {ticker}...")
        
        prompt = f"""
        Você é um Analista de Investimentos Sênior especializado em FIIs.
        Sua tarefa é cruzar os indicadores financeiros com o sentimento das notícias (se houver).

        {contexto_financeiro}

        Notícias e Sentimento do Mercado:
        {noticias_brutas if noticias_brutas else "Nenhuma notícia recente encontrada (busque focar apenas nos indicadores)."}

        Analise:
        1. A sustentabilidade dos dividendos frente ao setor.
        2. Se o P/VP indica uma oportunidade real ou uma "armadilha de valor" (risco de queda).
        3. Atribua um Score de 0 a 10.

        Responda obrigatoriamente em formato JSON puro:
        {{
          "score": int,
          "resumo": "string (máximo 3 parágrafos)",
          "riscos": ["string", "string"]
        }}
        """
        
        # Tentativa com retry inteligente para 429
        import time
        for tentativa in range(3):
            try:
                response = client.models.generate_content(model=model_id, contents=prompt)
                break
            except Exception as e:
                if "429" in str(e) and tentativa < 2:
                    # No plano grátis, o bloqueio costuma ser de 60 segundos
                    print(f"[ia] Limite de quota atingido (429). Iniciando pausa estratégica de 65s para resetar limites...")
                    time.sleep(65)
                else:
                    raise e
        
        texto_puro = response.text
        if "```json" in texto_puro:
            texto_puro = texto_puro.split("```json")[1].split("```")[0]
        elif "```" in texto_puro:
            texto_puro = texto_puro.split("```")[1].split("```")[0]
            
        data = json.loads(texto_puro.strip())
        print(f"[ia] Veredito Sênior para {ticker} concluído.")
        return data

    except Exception as e:
        print(f"[ia] Erro: {e}")
        return {
            "score": 5,
            "resumo": f"Análise limitada por erro técnico. {str(e)[:50]}",
            "riscos": ["Erro na comunicação com o cérebro da IA"]
        }
