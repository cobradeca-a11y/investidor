# FIIA — Análise Definitiva do Algoritmo

**Data:** 10/05/2026  
**Escopo:** todos os módulos do repositório cobradeca-a11y/investidor

---

## Veredicto geral

O projeto está arquiteturalmente correto. A separação em camadas (coleta → banco → processamento → decisão) é sólida e segue boas práticas. O código é legível, modular e sem gambiarras estruturais.

O problema não é a arquitetura. São os **pontos de falha silenciosa**: situações em que o sistema quebra ou produz resultado incorreto sem avisar claramente. Esses pontos estão identificados abaixo, módulo por módulo.

---

## O que está correto e deve ser mantido

### banco/db.py ✅
- WAL mode ativo: correto para SQLite com acesso concorrente (FastAPI + agendador).
- `row_factory = sqlite3.Row` com retorno em `dict`: padrão correto.
- `get_by_ticker` simples e reutilizável.
- `upsert` com `INSERT OR REPLACE`: certo para cache diário.
- **Manter tudo.**

### processamento/dividendo_recorrente.py ✅
- Uso de mediana (não média) para DY recorrente: tecnicamente correto. A mediana é resistente a outliers — exatamente o que se quer para separar dividendos extraordinários.
- Classificação por 2 desvios padrão da mediana: metodologia válida.
- Guard de `len(rows) < 3`: correto.
- **Manter tudo.**

### processamento/margem_seguranca.py ✅ (com ressalva)
- Taxa de desconto dinâmica `MAX(IPCA + 8%, SELIC + 1%)`: metodologia sênior correta.
- Distinção de valuation entre fundo de papel (P/VP) e tijolo (fluxo de caixa): correto.
- Stress test com redução de 15% na receita: razoável para cenário adverso.
- **Ressalva:** SELIC está hardcoded como `10.75`. A BCB já tem a série disponível (código 4189). Deve ser dinamizada — veja seção de correções.

### coleta/api_yfinance.py ✅
- Lida com timezone corretamente.
- Janela de 5 anos é adequada para o backtest.
- `INSERT OR REPLACE` via `db.upsert`: correto.
- Try/except granular por operação: bom.
- **Manter tudo.**

### coleta/api_bcb.py (não enviado, mas testado externamente) ✅
- SELIC e CDI respondendo. IPCA com delay normal (último dado de março/26).
- **Manter.**

### processamento/estrategia.py — filtros de sobrevivência ✅
- Lógica de pular filtro de vacância/diversificação para fundos de papel: correto.
- Retorno `(bool, [motivos])` é um padrão limpo.
- **Manter a lógica dos filtros.**

---

## O que está errado e deve ser corrigido

### 1. SELIC hardcoded em margem_seguranca.py 🔴

```python
selic = 10.75  # Fallback (deveria vir de uma API)
```

A SELIC é hardcoded em dois lugares (linhas 33 e 85). Isso significa que o valuation ignora a política monetária real. A BCB tem a série `11` (SELIC over) disponível — que você já coleta para outro fim.

**Correção:** `api_bcb.py` já deve ter `obter_selic_atual()` análogo ao `obter_ipca_atual()`. Chame-o com fallback:

```python
selic = api_bcb.obter_selic_atual() or 10.75
```

---

### 2. radar_oportunidades analisa só o #1 colocado com IA 🟡

```python
# MODO TESTE: Apenas o #1 para ajuste fino da IA
vencedores = oportunidades[:1]
```

Isso está em produção com comentário "MODO TESTE". O resultado é que o radar retorna somente 1 FII analisado, mesmo quando o código de exibição em `main.py` prepara para Top 15. O usuário vê um pódio de 1 elemento.

**Correção imediata (gratuita):** aumentar para Top 5 sem IA, Top 1 com IA:

```python
vencedores = oportunidades[:15]
for fii in vencedores[:1]:          # IA só no campeão
    fii["qualitativo"] = analisar_fundo_ia(fii["ticker"])
    time.sleep(4)
```

**Correção ideal (com plano pago Gemini):** Top 5 com IA, pausando 4s entre cada chamada.

---

### 3. coletar_mercado_inteiro sem fallback de encoding 🟡

O Fundamentus retorna HTML com encoding `latin-1` / `iso-8859-1`, e o requests pode interpretar errado dependendo do ambiente. Isso causa colunas com valores `None` em massa — e o radar descarta FIIs válidos.

**Correção:**

```python
res = requests.get(url, headers=headers, timeout=15)
res.encoding = 'latin-1'  # forçar encoding correto
```

Adicionar essa linha antes do `BeautifulSoup`.

---

### 4. vacancia_media com None causa crash silencioso no radar 🟡

```python
if fii["vacancia_media"] > 15.0: continue
```

Se `vacancia_media` for `None` (fundo de papel sem vacância informada), esse código lança `TypeError` silenciosamente — o FII é descartado sem aviso, como se tivesse vacância alta.

**Correção:**

```python
vacancia = fii.get("vacancia_media")
if vacancia is not None and vacancia > 15.0:
    continue
```

---

### 5. app.py expõe /api/radar sem timeout 🟡

O endpoint `/api/radar` chama `estrategia.radar_oportunidades()` de forma síncrona. Essa função pode levar **10 a 30 minutos** para completar (50 FIIs × coleta Fundamentus + yfinance). O FastAPI vai segurar o worker durante todo esse tempo, e o browser vai receber timeout antes de receber resposta.

**Correção necessária:** rodar o radar como tarefa de background com `BackgroundTasks` ou `asyncio`, retornar imediatamente um `job_id`, e expor um endpoint `/api/radar/status` para polling.

Isso é uma reescrita de médio porte do `app.py` — mas é obrigatória para o PWA funcionar.

---

### 6. app.py retorna `dados` (dict do SQLite) direto sem serialização 🟡

```python
return dados
```

`dados` é um `dict` com valores que podem ser `None`, `float`, `int`, `date`. O FastAPI serializa automaticamente, mas datas e `Decimal` podem causar erros. O retorno também não tem estrutura padronizada — às vezes é o dict de indicadores, às vezes é o resultado da coleta ao vivo.

**Correção:** criar um modelo Pydantic para a resposta, ou ao menos garantir que `None` e tipos especiais estejam tratados antes do retorno.

---

### 7. buscar_noticias_fii vs buscar_noticias — nome divergente 🔴

O `analise_qualitativa.py` original importa:

```python
from coleta.web_search import buscar_noticias_fii
```

Mas o `web_search.py` corrigido (entregue hoje) exporta `buscar_noticias`. Se você substituir apenas um dos dois arquivos, o import quebra com `ImportError` na hora que a IA for acionada — exatamente o momento crítico.

**Correção:** garantir que os dois arquivos usem o mesmo nome de função. O nome correto é `buscar_noticias` (sem `_fii`, mais genérico). Atualizar o import no `analise_qualitativa.py` entregue hoje — que já está correto.

---

### 8. auth.py com hash fixo em código 🟡

```python
# acesso/auth.py
# hash SHA-256 fixo comparado no código
```

O hash da senha está hardcoded no arquivo versionado. Qualquer pessoa que acesse o repositório pode tentar quebrar o hash offline. Para uso pessoal é aceitável, mas é um risco conhecido.

**Correção mínima:** mover o hash para o `.env` como `FIIA_SENHA_HASH`.

---

## O que está faltando e deve ser construído

### A. Log estruturado de erros de coleta

Hoje o sistema imprime erros no terminal e segue em frente. Não há como saber retrospectivamente quantos FIIs falharam na coleta, por qual motivo, e se estão sendo sistematicamente ignorados.

**Proposta:** gravar em tabela `erros_coleta(ticker, modulo, erro, timestamp)` a cada falha de coleta. O agendador ou o radar podem consultar essa tabela para alertar quando a taxa de falha ultrapassa 20%.

---

### B. Endpoint /api/radar/status para o PWA

Como descrito no item 5, o PWA não pode esperar 30 minutos em uma requisição. O fluxo correto é:

```
POST /api/radar/iniciar  → { "job_id": "abc123" }
GET  /api/radar/status/abc123 → { "status": "rodando", "progresso": "23/50" }
GET  /api/radar/resultado/abc123 → { "oportunidades": [...] }
```

---

### C. Campo `status` na resposta da IA propagado para o frontend

O `analise_qualitativa.py` corrigido hoje retorna `status: BLOQUEADO_DADOS_INSUFICIENTES` quando a análise não pode ser feita. Mas o `main.py` e o `app.py` ainda leem `qual.get('score', '?')` sem checar o status.

Se `score` for `None` (bloqueado), o frontend vai exibir `Score: None/10` — que confunde o usuário.

**Correção no main.py:**

```python
qual = op.get("qualitativo")
if qual and qual.get("status") == "OK":
    print(f"\n🔍 Score: {qual['score']}/10")
    print(f"Resumo: {qual['resumo']}")
elif qual:
    print(f"\n⚠️  Análise bloqueada: {qual['resumo']}")
```

---

## Resumo executivo

| Item | Status | Prioridade |
|------|--------|------------|
| SELIC hardcoded | Corrigir | Alta |
| Encoding latin-1 Fundamentus | Corrigir | Alta |
| vacancia_media None → crash | Corrigir | Alta |
| Nome buscar_noticias_fii vs buscar_noticias | Corrigir | Alta |
| Radar retorna só Top 1 | Corrigir | Média |
| /api/radar síncrono → timeout no PWA | Corrigir | Média |
| status da IA não checado no main.py | Corrigir | Média |
| app.py sem serialização Pydantic | Melhorar | Baixa |
| auth hash no código | Melhorar | Baixa |
| Log estruturado de erros de coleta | Construir | Média |
| Endpoints async para PWA | Construir | Alta (para uso mobile) |

O sistema está a 4 correções de funcionar de forma confiável no modo CLI. Para o PWA funcionar no celular, o endpoint assíncrono é obrigatório.
