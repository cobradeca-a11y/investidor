# FIIA — Roadmap & Pipeline de Execução
**Versão:** 2.0 | **Atualizado:** 2026-05-11 | **Modo:** Analista Sênior Autônomo

---

## Estado Atual (Baseline)

| Componente | Status | Observação |
|---|---|---|
| Gates 0–6 (funil de qualidade) | ✅ Produção | 30 finalistas por ciclo |
| Gemini 2.5 Flash | ✅ Produção | Score qualitativo funcionando |
| BCB (SELIC/CDI/IPCA) | ✅ Produção | Dados diários |
| Fundamentus scraper | ✅ Produção | Encoding corrigido |
| Yahoo Finance dividendos | ✅ Produção | 5 anos de histórico |
| Motor de decisão v2.0 | ✅ Produção | COMPRAR→EVITAR |
| Decisões gravadas no banco | ✅ Produção | Base para aprendizado |
| FNET relatórios gerenciais | 🟡 Parcial | Aguardando CNPJ |
| CNPJ via CVM informe mensal | 🟡 Em progresso | ZIP/CSV identificado |
| Dimensionamento de posição | ❌ Pendente | Passo 4 |
| Semáforo macro | ❌ Pendente | Passo 2 |
| Contexto setorial | ❌ Pendente | Passo 2.5 |
| Zonas de entrada | ❌ Pendente | Passo 5 |
| Gestão com gatilhos | ❌ Pendente | Passo 6 |
| Avaliação dupla 90/365d | ❌ Pendente | Passo 7 |
| PWA cards de decisão | ❌ Pendente | Interface final |

---

## Pipeline de Execução — 8 Passos

```
[2] MACRO → [2.5] SETORIAL → [3] SELEÇÃO → [4] DIMENSIONAMENTO
         → [5] ZONAS DE ENTRADA → [6] GESTÃO → [7] AVALIAÇÃO
```

---

## Bloco A — Fechar Infraestrutura (Sessão Atual)

### A1. CNPJ via Informe Mensal CVM
- **Arquivo:** `coleta/cnpj_fundo.py`
- **Fonte:** `dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip`
- **Lógica:** ISIN `BRHGLGCTF004` → ticker `HGLG11`
- **Status:** Código pronto, aguardando teste em produção
- **Dependência:** Desbloqueia FNET

### A2. FNET com CNPJ
- **Arquivo:** `coleta/relatorio_fnet.py`
- **Lógica:** `cnpjFundo=XX.XXX.XXX/XXXX-XX` evita bloqueio por texto
- **Status:** Código pronto, bloqueado por A1

### A3. Informe Diário CVM
- **Arquivo:** `coleta/informe_diario.py` ← criar
- **Fonte:** `dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{AAAAMM}.zip`
- **Dados:** VL_QUOTA, VL_PATRIM_LIQ, NR_COTST por CNPJ/dia
- **Uso:** Monitoramento diário de patrimônio e cotas — base para alertas
- **Dependência:** A1 (CNPJ para cruzar com ticker)

---

## Bloco B — Semáforo Macro + Setorial (Passo 2 e 2.5)

### B1. Semáforo Macro
- **Arquivo:** `mercado/semaforo_macro.py`
- **Lógica:**
  ```
  SELIC > 13.5% e subindo    → VERMELHO (reduzir exposição)
  SELIC 11-13.5% estável     → AMARELO  (seletivo)
  SELIC < 11% ou caindo      → VERDE    (aumentar exposição)
  ```
- **Impacto:** Gate 0 do radar passa a checar semáforo antes de prosseguir
- **Fonte:** BCB série 4189 (meta SELIC) + tendência 3 meses

### B2. Contexto Setorial
- **Arquivo:** `mercado/contexto_setorial.py`
- **Segmentos mapeados:**
  ```
  PAPEL      → sensível à curva de juros (IPCA+, CDI+)
  LOGÍSTICA  → sensível à atividade econômica e e-commerce
  LAJES      → sensível ao desemprego e absorção corporativa
  SHOPPINGS  → sensível ao consumo das famílias e ICVA
  HÍBRIDO    → média ponderada
  ```
- **Output:** score setorial 0-10 por segmento no momento atual

---

## Bloco C — Dimensionamento (Passo 4)

### C1. Motor de Dimensionamento
- **Arquivo:** `decisao/dimensionamento.py`
- **Regras:**
  ```
  Margem > 40% e histórico > 36m e sem travas   → até 8% da carteira
  Margem 25-40% ou histórico 24-36m              → até 5% da carteira
  Margem 15-25% ou histórico 12-24m              → até 3% da carteira
  Qualquer trava ativa                           → máximo 2% (monitorar)
  ```
- **Output:** `{"pct_carteira": 5.0, "valor_ref_10k": 500.0, "lote_minimo": 100}`

---

## Bloco D — Zonas de Entrada (Passo 5)

### D1. Calculador de Zonas
- **Arquivo:** `decisao/zonas_entrada.py`
- **Três zonas em R$:**
  ```
  ZONA_FORTE   = preco_justo * 0.75  (margem > 33%)
  ZONA_PARCIAL = preco_justo * 0.85  (margem > 18%)
  ZONA_ESPERA  = preco_justo * 0.95  (margem > 5%)
  ```
- **Output:** preços concretos em R$ para o usuário

---

## Bloco E — Gestão com Gatilhos (Passo 6)

### E1. Monitor de Gatilhos
- **Arquivo:** `decisao/gatilhos.py`
- **Gatilhos de saída por deterioração:**
  ```
  vacancia_fisica > 20%                → REDUZIR
  dy_recorrente cai > 25% em 3 meses  → REDUZIR
  score_ia < 3 por 2 ciclos seguidos  → VENDER
  ```
- **Gatilhos de realização parcial:**
  ```
  P/VP > 1.20                          → REALIZAR 30%
  margem_seguranca < 0%                → REALIZAR 50%
  ```
- **Gatilhos de adição:**
  ```
  preco cai > 10% sem mudança de fund. → ADICIONAR
  entrada na zona forte                → ADICIONAR
  ```

---

## Bloco F — Avaliação Dupla (Passo 7)

### F1. Avaliador de Decisões
- **Arquivo:** `aprendizado/avaliador.py`
- **Janela 90 dias:** avalia timing — o preço caiu depois da compra? Era o momento?
- **Janela 365 dias:** avalia tese — os fundamentos se mantiveram? A renda foi entregue?
- **Métricas:**
  ```
  retorno_total vs CDI_periodo
  retorno_total vs IFIX_periodo
  acerto_timing (%)
  acerto_tese (%)
  ```
- **Output:** grava em `decisoes_resultado`, atualiza `versoes_modelo`

---

## Bloco G — Interface PWA (Fase 9)

### G1. Cards de Decisão
- **Arquivo:** `static/` (index.html + app.js + style.css)
- **Cada card mostra:**
  ```
  Ticker | Decisão | Margem | Zona atual
  Preço entrada | Preço justo | Dimensionamento
  Score IA | Tom gestor | Fonte qualitativa
  Gatilhos ativos | Confiança | Data
  ```

---

## Sequência de Implementação

```
Sessão atual:
  [A1] cnpj_fundo.py          → testar em produção
  [A2] relatorio_fnet.py      → validar com CNPJ
  [A3] informe_diario.py      → criar módulo

Próxima sessão:
  [B1] semaforo_macro.py
  [B2] contexto_setorial.py
  [C1] dimensionamento.py
  [D1] zonas_entrada.py

Sessão seguinte:
  [E1] gatilhos.py
  [F1] avaliador.py
  [G1] PWA cards
```

---

## Arquivos por Entregar (Fila)

| # | Arquivo | Bloco | Depende de |
|---|---|---|---|
| 1 | `coleta/informe_diario.py` | A3 | A1 testado |
| 2 | `mercado/semaforo_macro.py` | B1 | — |
| 3 | `mercado/contexto_setorial.py` | B2 | B1 |
| 4 | `decisao/dimensionamento.py` | C1 | B1, B2 |
| 5 | `decisao/zonas_entrada.py` | D1 | C1 |
| 6 | `decisao/gatilhos.py` | E1 | D1 |
| 7 | `aprendizado/avaliador.py` | F1 | E1 |
| 8 | `static/` PWA atualizada | G1 | F1 |

---

## Regra de Atualização

Este arquivo é atualizado automaticamente ao fim de cada janela de contexto com:
- Status de cada item (✅ / 🟡 / ❌)
- Próximo arquivo a entregar
- Decisões técnicas tomadas
- Bugs encontrados e corrigidos
