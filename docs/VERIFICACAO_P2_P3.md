# VERIFICAÇÃO P2 + P3 — PENDÊNCIAS RESIDUAIS

Documento consolidado de auditoria estrutural após execução das prioridades P2 e P3.

## Pendências residuais identificadas

### `coleta/cvm_informe_mensal.py`
- `_inferir_ano_do_nome()` retorna fallback `0` quando regex falha.
- Recomendação: usar `None` ao invés de `0`.

### `coleta/fnet_dividendos.py`
- Separar aliases de `data_base` e `data_com` sem cruzamento semântico.
- Campos possuem significado legal distinto.

### `processamento/analise_dre.py`
- Verificar sincronização da tabela `inf_trimestral_imoveis` com schema operacional.
- Hoje o módulo falha silenciosamente de forma segura quando a tabela não existe.

### `processamento/score_segmentado.py`
- Validar peso de `pvp` para segmento PAPEL.
- Evitar penalização excessiva de fundos CRI.

### `mercado/semaforo_macro.py`
- Média de spread ainda considera múltiplos snapshots do mesmo ticker.
- Futuramente aplicar agregação por ticker.

### `processamento/confiabilidade.py`
- `relatorio_confiabilidade()` chama `_aplicar_teto_preco(100, ind)`.
- Ideal: usar score real para refletir teto exato no relatório.

### `backtest/maquina_tempo.py`
- Continua sem snapshots históricos institucionais.
- `validade_institucional: False` permanece correto.
- Gap residual aceito.

## Estado geral

- P2 permanece validada.
- P3 permanece validada.
- Nenhuma pendência bloqueia operação atual.
- Pendências restantes são evolutivas/auditáveis.
