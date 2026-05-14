# FIIA — Arquitetura Profissional da Engine Analítica

Este documento transforma a diretriz estratégica do FIIA em plano técnico executável.

O objetivo não é criar um dashboard de FIIs. O objetivo é construir uma engine analítica com foco em gestão de risco, rastreabilidade, validação de dados, explicabilidade e condução de carteira.

---

## 1. Princípio central

```text
investimento = gestão de risco
```

O FIIA não deve prometer previsão perfeita. A função do sistema é reduzir incerteza, detectar deterioração, evitar armadilhas de yield, identificar assimetrias favoráveis e melhorar a qualidade média das decisões.

---

## 2. Ordem de prioridade técnica

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

A IA é camada interpretativa. Ela não é fonte primária de verdade.

---

## 3. Hierarquia de fontes

### Fonte oficial principal

- CVM Dados Abertos
  - informes mensais;
  - informes trimestrais;
  - demonstrações financeiras;
  - informes anuais;
  - reapresentações.

### Fonte macroeconômica

- Banco Central do Brasil
  - Selic;
  - CDI;
  - IPCA;
  - IGP-M;
  - séries SGS;
  - Focus, quando integrado.

### Fonte documental

- B3/Fundos.NET
  - fatos relevantes;
  - regulamentos;
  - comunicados;
  - relatórios;
  - validação documental.

### Fontes auxiliares

- Yahoo Finance;
- brapi;
- Investing;
- Fundamentus;
- Status Invest;
- Funds Explorer;
- InfoMoney.

Fontes auxiliares servem para validação, redundância, enriquecimento e fallback. Elas não devem ser núcleo estrutural definitivo.

---

## 4. Identidade canônica

Toda análise deve convergir para:

```text
Ticker B3
↓
CNPJ Fundo
↓
CNPJ Classe CVM
↓
Identidade canônica do fundo
```

Essa identidade desbloqueia cruzamento entre mercado, CVM, FNET, rendimentos, documentos e análises qualitativas.

---

## 5. Módulos profissionais obrigatórios

### 5.1 Ingestão de dados

Responsável por coleta, parsing, retries, cache, fallback e persistência bruta.

Entregáveis:

- conectores CVM;
- conectores Banco Central;
- conectores FNET;
- conectores mercado;
- controle de falhas;
- log estruturado por fonte.

### 5.2 Normalização

Responsável por padronizar nomes, tickers, CNPJs, datas, competências, moeda, versões e reapresentações.

Entregáveis:

- identidade canônica;
- mapeamento ticker/CNPJ;
- normalização temporal;
- tratamento de reapresentações CVM.

### 5.3 Validação cruzada

Responsável por comparar campos entre fontes e calcular confiabilidade.

Exemplo:

```text
CVM diz X
Yahoo diz Y
Status Invest diz Z
Resultado: ok/divergente/revisar
```

Entregáveis:

- score de confiança por campo;
- tabela de divergências;
- marcação de dados ausentes;
- bloqueio de decisão quando campo crítico for inconsistente.

### 5.4 Gates

Cada gate deve ser independente, testável e explicável.

Cada gate deve retornar:

- status;
- score;
- motivo;
- dados usados;
- fonte;
- versão da regra;
- timestamp.

### 5.5 Motor macroeconômico

Responsável por ajustar exigências conforme ambiente econômico.

Exemplo:

```text
SELIC subindo
↓
aumenta exigência de DY
↓
penaliza FIIs premium
↓
favorece margem de segurança
```

### 5.6 Motor de margem de segurança

Responsável por preço justo, preço teto, zona de compra, zona parcial e zona de risco.

### 5.7 Motor de carteira

Responsável por alocação, concentração, diversificação, rebalanceamento e gatilhos de deterioração.

### 5.8 Backtesting e aprendizado operacional

Responsável por avaliar decisões passadas.

Janelas mínimas:

- 90 dias: timing;
- 365 dias: tese.

Métricas:

- retorno vs CDI;
- retorno vs IFIX;
- drawdown;
- falso positivo;
- falso negativo;
- acerto de tese;
- acerto de timing.

### 5.9 Observabilidade

Responsável por saber o que falhou, por que falhou e qual impacto teve.

Entregáveis:

- log estruturado;
- tempo por módulo;
- fonte com erro;
- ticker afetado;
- resultado parcial;
- rastreio de exceções.

---

## 6. Regras de decisão

Evitar decisão simplista. Usar estados operacionais:

- COMPRAR;
- COMPRAR_PARCIALMENTE;
- AGUARDAR;
- MONITORAR;
- MANTER;
- REDUZIR;
- VENDER;
- EVITAR_ENTRADA.

Toda decisão deve ter:

- justificativa;
- riscos;
- nível de confiança;
- margem;
- gatilhos de invalidação;
- cenário esperado;
- cenário adverso;
- dados e fontes usados.

---

## 7. Padrão mínimo de resiliência

Nenhuma fonte externa pode derrubar o radar inteiro.

Todo conector deve aplicar:

- timeout;
- retry;
- fallback;
- cache;
- tratamento de exceção;
- retorno parcial;
- registro de erro.

---

## 8. Padrão mínimo de armazenamento

Toda coleta relevante deve guardar:

- ticker;
- CNPJ fundo;
- CNPJ classe;
- fonte;
- campo;
- valor;
- competência;
- data de coleta;
- versão;
- confiabilidade;
- hash/assinatura quando aplicável.

---

## 9. Primeiras entregas recomendadas

### Fase 1 — Profissionalização da base

1. Criar camada de log estruturado.
2. Criar tabela/camada de qualidade dos dados.
3. Consolidar ticker -> CNPJ -> classe CVM.
4. Integrar CVM como fonte primária progressiva.
5. Impedir que falhas externas derrubem `/api/radar`.

### Fase 2 — Profissionalização da decisão

1. Formalizar objeto de decisão.
2. Adicionar confiança por decisão.
3. Separar decisão operacional de recomendação simples.
4. Integrar gatilhos de carteira.
5. Expor motivo de cada gate.

### Fase 3 — Profissionalização do aprendizado

1. Registrar decisão simulada.
2. Avaliar 90/365 dias.
3. Calcular falso positivo/falso negativo.
4. Ajustar pesos com rastreabilidade.
5. Versionar modelo.

---

## 10. O que não fazer

- Não usar scraping como núcleo definitivo.
- Não confiar em uma única fonte.
- Não usar IA para inventar dado ausente.
- Não tomar decisão baseada apenas em DY.
- Não permitir `500` genérico no radar.
- Não acoplar frontend à lógica analítica.
- Não criar score sem explicação.
- Não alterar pesos sem registrar versão.
- Não tratar rentabilidade passada como garantia.

---

## 11. Definição de profissional

O FIIA será considerado profissional quando conseguir:

1. coletar dados com rastreabilidade;
2. validar fontes;
3. detectar divergências;
4. sobreviver a falhas externas;
5. explicar cada decisão;
6. registrar versões dos critérios;
7. medir acerto/erro historicamente;
8. conduzir carteira após o investimento;
9. operar com resultado parcial em caso de falha;
10. evoluir por aprendizado operacional sem perder auditabilidade.
