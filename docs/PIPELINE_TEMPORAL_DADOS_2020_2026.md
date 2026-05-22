# FIIA - Pipeline temporal de dados 2020-2026

## Objetivo

Montar a base temporal para tres usos:

- Radar em tempo real: decisao atual com dados rastreaveis.
- Maquina do tempo: decisao em uma data passada sem olhar dados futuros.
- Aprendizado: comparar decisoes antigas com resultado futuro e ajustar parametros.

## Estado dos dados enviados

Dados suficientes ja disponiveis:

- Informes mensais CVM 2020-2026.
- Informes trimestrais CVM 2020-2026.
- Informes anuais CVM 2020-2025.
- Cadastro CVM local.
- COTAHIST B3 2020 e 2021.

Dados ainda faltantes para cobertura temporal completa 2020-2026:

- `COTAHIST_A2022.ZIP`
- `COTAHIST_A2023.ZIP`
- `COTAHIST_A2024.ZIP`
- `COTAHIST_A2025.ZIP`
- `COTAHIST_A2026.ZIP`, quando disponivel

Sem esses COTAHIST, a Maquina do Tempo consegue usar fundamentos historicos, mas nao fecha preco, liquidez, retorno futuro e ranking auditavel para todos os anos.

## Prioridade de execucao

### P0 - Inventario local

Validar quais arquivos existem em `Downloads` e quais anos estao cobertos.

Comando:

```bash
python scripts/pipeline_temporal_local.py --downloads C:\Users\snake\Downloads --anos 2020 2021 2022 2023 2024 2025 2026
```

Status esperado:

- Lista de ZIPs mensais/trimestrais/anuais encontrados.
- Lista de COTAHIST faltantes.

### P1 - Importar informes mensais CVM

Importa patrimonio liquido, valor patrimonial por cota, numero de cotistas e cotas emitidas.

Comando:

```bash
python scripts/pipeline_temporal_local.py --downloads C:\Users\snake\Downloads --anos 2020 2021 2022 2023 2024 2025 2026 --importar-mensal
```

Criterio de conclusao:

- Todos os anos com `status: OK`.
- `registros_processados` preenchido.
- `calcular_pvp_cvm("HGLG11")` retorna `status: OK`.

Observacao operacional:

- O script pula anos ja existentes no banco para evitar reimportacao acidental.
- Para reprocessar explicitamente, usar `--force`.

### P2 - Precos e liquidez por COTAHIST

Implementar importador de COTAHIST para montar serie diaria de:

- ticker
- data
- preco abertura
- preco maximo
- preco minimo
- preco fechamento
- volume financeiro
- quantidade de negocios, se disponivel

Criterio de conclusao:

- Importar 2020-2026.
- Conseguir consultar preco em uma data historica.
- Conseguir calcular liquidez media anterior a data da decisao.

### P3 - Dividendos historicos

Usar duas camadas:

- yfinance como fallback de `data_com` e valor.
- FNET estruturado como fonte preferencial quando houver `data_com`, `data_pagamento`, valor e tipo de evento.

Criterio de conclusao:

- `data_com` nao pode ser gravada como `data_pagamento`.
- Rendimento entra no DY recorrente.
- Amortizacao nao entra no DY recorrente.

### P4 - Informes trimestrais e anuais locais

Adicionar importador local para os ZIPs trimestrais e anuais ja baixados.

Criterio de conclusao:

- Vacancia por imovel preenchida quando existir no informe trimestral.
- Dados anuais usados como enriquecimento, nao como preco ou decisao isolada.

### P5 - Snapshots historicos

Gerar snapshots por ticker/data usando apenas dados conhecidos ate aquela data.

Criterio de conclusao:

- Snapshot tem hash.
- Snapshot informa fontes.
- Snapshot invalido bloqueia backtest.

### P6 - Maquina do tempo

Executar ranking top 5 em datas passadas.

Criterio de conclusao:

- Entrada usa apenas snapshot anterior ou igual a data de referencia.
- Resultado futuro usa preco/dividendos apenas na avaliacao.
- Relatorio mostra acertos, erros e parametros sensiveis.

### P7 - Aprendizado

Comparar previsoes com resultados e sugerir ajuste de parametros.

Criterio de conclusao:

- Separar recomendacao tecnica de alteracao automatica.
- Nenhum parametro muda sem registro de justificativa.
- Backtest antes/depois documentado.

## Resumo objetivo

De dados CVM, a base esta suficiente para executar a primeira carga temporal.

De preco/liquidez B3, ainda faltam COTAHIST 2022-2026 para o ciclo completo. Com COTAHIST 2020-2021, ja e possivel validar o parser e uma primeira Maquina do Tempo limitada.
