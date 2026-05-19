# FIIA - Fundo Inteligente de Investimento em Ativos 🚀

FIIA é uma engine analítica para Fundos Imobiliários (FIIs) brasileiros. O objetivo do projeto é sair da lógica de dashboard/agregador de indicadores e evoluir para uma infraestrutura própria de análise, decisão, acompanhamento de carteira, validação de dados e gestão de risco.

> Princípio central: investimento não é previsão perfeita; investimento é gestão de risco, preservação de capital e redução progressiva de decisões ruins.

---

## 🎯 Objetivo

O FIIA busca identificar FIIs com melhor relação entre:

- qualidade da renda;
- margem de segurança;
- saúde patrimonial;
- liquidez;
- risco estrutural;
- contexto macroeconômico;
- consistência documental;
- sustentabilidade dos rendimentos.

O sistema não deve operar como recomendador simplista. Ele deve entregar uma análise explicável, rastreável e baseada em múltiplas camadas de validação.

---

## 🧠 Como funciona

A arquitetura atual trabalha com uma esteira de qualidade baseada em Gates:

```text
Mercado completo de FIIs
↓
Pré-filtros de liquidez e vacância
↓
Gates 0-3: dados, elegibilidade, estrutura e renda
↓
Gate 4: margem de segurança
↓
Gate 5: confiança
↓
Gate 6: análise qualitativa / IA
↓
Decisão operacional
```

A decisão final não deve ser apenas "comprar" ou "vender". O sistema deve evoluir para ações operacionais como:

- comprar;
- comprar parcialmente;
- aguardar;
- monitorar;
- manter;
- reduzir;
- vender;
- evitar entrada.

Cada decisão precisa carregar justificativa, riscos, fontes, nível de confiança, margem de segurança e gatilhos de invalidação.

---

## 🏗️ Filosofia operacional

O FIIA deve priorizar, nesta ordem:

1. Robustez
2. Integridade dos dados
3. Auditabilidade
4. Explicabilidade
5. Rastreabilidade
6. Resiliência
7. Consistência histórica
8. Validação cruzada
9. Performance
10. Escalabilidade
11. Automação
12. IA
13. Interface visual

A IA é uma camada interpretativa. Ela não é fonte primária de verdade.

---

## 📊 Fontes de dados

### Fontes oficiais e estruturais

- CVM Dados Abertos: informes mensais, trimestrais, demonstrações e documentos estruturados.
- Banco Central do Brasil: SELIC, CDI, IPCA, IGP-M e séries macroeconômicas.
- B3/Fundos.NET: documentos, fatos relevantes, regulamentos, comunicados e validação documental.

### Fontes de mercado e apoio

- Yahoo Finance;
- brapi;
- Investing;
- Fundamentus;
- Status Invest;
- Funds Explorer;
- InfoMoney.

Fontes auxiliares devem servir para validação, redundância, enriquecimento e comparação, não como núcleo definitivo do sistema.

---

## 🔑 Identidade canônica dos fundos

O sistema deve manter a cadeia:

```text
Ticker B3
↓
CNPJ Fundo
↓
CNPJ Classe CVM
↓
Identidade canônica do fundo
```

Essa identidade é a base para cruzar dados de CVM, B3/FNET, mercado, rendimentos, relatórios e análise qualitativa.

---

## 🧩 Módulos principais

- `coleta/`: conectores, scrapers, APIs, CVM, FNET, Yahoo, Fundamentus e dados auxiliares.
- `processamento/`: estratégia, gates, análise quantitativa, margem de segurança e análise qualitativa.
- `decisao/`: motor de decisão, dimensionamento, zonas de entrada, gatilhos e tradução da decisão para linguagem operacional.
- `mercado/`: semáforo macroeconômico e contexto setorial.
- `aprendizado/`: avaliação das decisões, backtesting operacional e janelas 90/365 dias.
- `banco/`: persistência SQLite, schema e histórico.
- `web` ou `static/`: interface web/PWA.
- `app.py`: servidor FastAPI.
- `main.py`: entrada CLI.

---

## 🛠️ Tecnologias

- Python 3.x
- FastAPI / Uvicorn
- SQLite
- Yahoo Finance / yfinance
- Banco Central SGS
- CVM Dados Abertos
- Google Gemini para análise qualitativa
- Cache HTTP e persistência local

---

## 🚀 Como iniciar

1. Instale as dependências:

```bash
pip install -r requirements.txt
```

2. Configure o arquivo `.env` na raiz do projeto:

```env
FIIA_API_KEY=sua_chave_operacional
GEMINI_API_KEY=sua_chave_aqui
FIIA_OBSERVABILIDADE=1
```

3. Inicialize o banco:

```bash
python main.py --setup
```

4. Rode o radar via CLI:

```bash
python main.py --radar
```

5. Rode a interface web:

```bash
python app.py
```

A aplicação FastAPI sobe por padrão em:

```text
http://0.0.0.0:8080
```

---

## ✅ Produção, operação e release

Antes de tag, deploy ou uso operacional, siga obrigatoriamente:

- [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md): checklist técnico de release, CI, testes, segurança, logs, versionamento, migração e rollback.
- [`docs/OPERACAO.md`](docs/OPERACAO.md): guia de operação local/operacional, variáveis de ambiente, auditoria, backtest, logs e smoke tests.

Uma release só deve ser considerada pronta com CI verde e testes críticos aprovados.

---

## 🧪 Estado atual

O roadmap do projeto registra como base atual:

- Gates 0-6 em produção;
- motor de decisão gravando decisões no banco;
- uso de Fundamentus, Yahoo Finance e Banco Central;
- Gemini para análise qualitativa;
- integração progressiva com CVM e FNET;
- CNPJ via CVM em andamento/consolidação;
- módulos de semáforo macro, contexto setorial, dimensionamento, zonas de entrada, gatilhos e avaliação 90/365d em evolução.

Veja o arquivo [`ROADMAP.md`](ROADMAP.md) para o estado detalhado.

---

## ⚠️ Aviso importante

Este projeto é uma ferramenta analítica e educacional. Ele não garante rentabilidade, não elimina riscos e não substitui avaliação humana, planejamento financeiro ou orientação profissional habilitada.

O objetivo do FIIA é reduzir incerteza, melhorar a qualidade das decisões e tornar a análise de FIIs mais rastreável, robusta e explicável.