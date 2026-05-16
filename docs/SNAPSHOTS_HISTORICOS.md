# SNAPSHOTS HISTÓRICOS — ARQUITETURA FUTURA

Objetivo:
Permitir replay histórico institucional do motor de decisão sem look-ahead bias.

IMPORTANTE:
Este documento NÃO ativa snapshots históricos.
Define apenas a arquitetura futura.

## Problema atual

`backtest/maquina_tempo.py`
utiliza:

```python
decidir(ticker)
```

com estado atual do banco.

Isso significa:
- indicadores históricos reais NÃO são reconstruídos;
- decisões antigas usam dados modernos;
- validade institucional permanece limitada.

O sistema atualmente declara corretamente:

```python
validade_institucional = False
```

## Objetivo futuro

Criar replay temporal auditável:

```txt
estado do banco em T0
→ decisão em T0
→ avaliação em T+n
```

sem contaminação de informação futura.

---

# Estrutura proposta

Tabela:

```sql
snapshots_indicadores
```

Campos mínimos:

- ticker
- data_snapshot
- origem_snapshot
- payload_json
- hash_snapshot
- criado_em

Campos derivados opcionais:

- score_total
- score_segmentado
- score_cvm
- confiabilidade
- semaforo_macro

---

# Estratégia de gravação

Momento ideal:

- após coleta consolidada diária;
- antes de qualquer decisão operacional;
- granularidade diária.

Fluxo:

```txt
coleta → consolidação → snapshot → radar → decisão
```

---

# Estratégia de replay histórico

Backtest futuro:

```txt
1. localizar snapshot <= data_decisao
2. reconstruir indicadores
3. executar decidir(snapshot)
4. congelar contexto macro
5. avaliar resultado futuro
```

---

# Prevenção de look-ahead bias

Regras obrigatórias:

- nunca usar snapshot posterior à decisão;
- nunca recalcular score usando estado atual;
- congelar semáforo macro;
- congelar confiabilidade;
- congelar preço disponível no momento;
- congelar DY conhecido na data.

---

# Estratégia de armazenamento

Formato preferencial:

```txt
payload_json compactado
```

Motivos:
- menor acoplamento;
- replay resiliente a mudanças de schema;
- versionamento simples.

---

# Impacto esperado

Benefícios:
- validade institucional futura;
- backtest auditável;
- comparação real vs simulado;
- aprendizado temporal confiável.

Custos:
- aumento de storage;
- aumento de IO;
- necessidade de política de retenção.

---

# Estratégia recomendada de retenção

- snapshots diários: 5 anos;
- snapshots mensais agregados: permanente.

---

# Estado atual

- arquitetura NÃO implementada;
- apenas documentada;
- sistema permanece operacional sem snapshots.
