# FIIA - Fundo Inteligente de Investimento em Ativos 🚀

FIIA é um agente autônomo de análise de Fundos Imobiliários (FIIs) brasileiros, projetado para atuar como um Analista Sênior, unindo dados quantitativos precisos com inteligência qualitativa via IA.

## 🧠 Como funciona?

O sistema opera em três camadas de inteligência para filtrar e ranquear oportunidades:

1.  **Filtros de Sobrevivência**: Corte automático baseado em Liquidez (> R$ 1M/dia), Vacância (< 15%) e Diversificação (> 5 ativos).
2.  **Motor Quantitativo**: Cálculo de Preço Justo e Stress Test baseado no fluxo de dividendos vs SELIC.
3.  **Analista Sênior (IA)**: Utiliza o **Gemini 2.0 Flash** para analisar notícias e sentimento do mercado em tempo real.

## 🛠️ Tecnologias

- **Linguagem**: Python 3.x
- **IA**: Google Gemini (google-genai)
- **Banco de Dados**: SQLite com cache de requisições HTTP.
- **Fontes de Dados**: Fundamentus, Yahoo Finance, Banco Central do Brasil.
- **Interface**: CLI (Terminal) e base para PWA em FastAPI.

## 🚀 Como Iniciar

1. **Instale as dependências**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure suas chaves**:
   Crie um arquivo `.env` na raiz e adicione sua chave:
   ```env
   GEMINI_API_KEY=sua_chave_aqui
   ```

3. **Inicie o banco de dados**:
   ```bash
   python main.py --setup
   ```

4. **Rode o Radar de Oportunidades**:
   ```bash
   python main.py --radar
   ```

## 📂 Estrutura do Projeto

- `/coleta`: Scrapers e APIs de dados.
- `/processamento`: Onde vive o cérebro das estratégias e cálculos.
- `/decisao`: Lógica de ranqueamento de oportunidades.
- `/sistema`: Utilitários e autoupdater.
- `app.py`: Servidor para a interface web.

---
*Este projeto foi desenvolvido como um assistente de investimentos para fins educacionais.*
