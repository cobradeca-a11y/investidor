# Pipeline de Execucao - Performance e Dados do Radar FIIA

Este documento organiza a proxima etapa do projeto depois da homologacao de CI, API, PWA, auditoria e replay.

Objetivo geral:
Reduzir bloqueios operacionais indevidos no Radar, melhorar qualidade dos dados de contexto e tornar a execucao mais rapida, auditavel e previsivel.

## Regras Gerais

- Nao alterar thresholds dos gates sem aprovacao humana.
- Nao alterar `decisao/motor_decisao.py` nem `decisao/motor_decisao_cvm_first.py` sem aprovacao explicita.
- Nao quebrar Zero DB Query Mode.
- Nao versionar `fiia.db`, `http_cache.sqlite`, logs, `.env`, `.venv`, caches ou artefatos locais.
- Em testes automatizados, nao depender de banco local populado.
- Em smoke visual/API local, informar se `uvicorn app:app --host 127.0.0.1 --port 8080 --reload` e necessario.

## Fase P1 - Diagnostico dos Bloqueios do Radar

Objetivo:
Identificar por que a maioria dos ativos fica bloqueada por `liquidez` e/ou aparece com `patrimonial=N/D`.

Arquivos permitidos:

- `coleta/contexto_ativo.py`
- `processamento/estrategia.py`
- `coleta/api_fundamentus.py`
- `coleta/api_yfinance.py`
- `banco/db.py`
- `teste_performance_radar.py`
- `teste_diagnostico_bloqueios_radar.py`

Arquivos proibidos:

- `decisao/motor_decisao.py`
- `decisao/motor_decisao_cvm_first.py`
- `schema.sql`, salvo aprovacao explicita
- `static/`, salvo fase visual especifica
- `logs/`
- bancos SQLite locais

Contratos obrigatorios:

- Cards bloqueados continuam visiveis.
- Motivos de bloqueio continuam explicitos.
- Radar nao pode esconder ativo bloqueado por falta de dado.
- Diagnostico deve separar falta real de dado de falha de mapeamento/fallback.

Comandos de verificacao:

```bat
python -m compileall -q coleta processamento banco decisao config
pytest teste_performance_radar.py teste_diagnostico_bloqueios_radar.py teste_regressao_zero_db.py
```

## Fase P2 - Correcao de `liquidez_diaria`

Objetivo:
Garantir que `liquidez_diaria` seja preenchida corretamente a partir do mercado inteiro, detalhe do Fundamentus, Yahoo ou ultimo indicador local valido.

Arquivos permitidos:

- `coleta/contexto_ativo.py`
- `processamento/estrategia.py`
- `coleta/api_fundamentus.py`
- `teste_diagnostico_bloqueios_radar.py`
- `teste_performance_radar.py`

Contratos obrigatorios:

- Nao reduzir `LIQUIDEZ_MINIMA_DIARIA`.
- Nao transformar liquidez ausente em liquidez aprovada artificialmente.
- Quando a liquidez vier do pre-filtro do mercado, registrar fonte/metricas no contexto.
- Quando continuar ausente, manter bloqueio fail-closed.

Comandos de verificacao:

```bat
python -m compileall -q coleta processamento config
pytest teste_diagnostico_bloqueios_radar.py teste_performance_radar.py teste_regressao_zero_db.py
```

## Fase P3 - Correcao Patrimonial e Fonte CVM/Fundamentus

Objetivo:
Reduzir `patrimonial=N/D` garantindo propagacao de `patrimonio_fonte`, `vpa`, `pvp` e `patrimonio_liquido` para cards bloqueados e decisoes persistidas.

Arquivos permitidos:

- `coleta/contexto_ativo.py`
- `processamento/estrategia.py`
- `decisao/persistencia_decisao.py`
- `teste_diagnostico_bloqueios_radar.py`
- `teste_replay_decisao.py`

Contratos obrigatorios:

- CVM continua sendo prioridade quando disponivel.
- Fundamentus permanece fallback patrimonial.
- Persistencia nao pode quebrar hash/replay.
- Cards bloqueados devem carregar `fonte_patrimonial` quando existir.

Comandos de verificacao:

```bat
python -m compileall -q coleta processamento decisao
pytest teste_diagnostico_bloqueios_radar.py teste_replay_decisao.py teste_auditoria_decisao.py
```

## Fase P4 - Payload Auditavel Completo nos Cards Bloqueados

Objetivo:
Enriquecer o card bloqueado do Radar com metadados auditaveis ja existentes no contexto.

Campos-alvo:

- `contexto_versao`
- `versao_motor`
- `fonte_patrimonial`
- `score_confianca_dados`
- `nivel_uso_dados`
- `permitir_decisao`
- `gates_detalhes`
- `confianca_dados`

Arquivos permitidos:

- `processamento/estrategia.py`
- `decisao/objeto_decisao.py`
- `teste_frontend_payload.py`
- `teste_frontend_explicabilidade.py`

Contratos obrigatorios:

- Frontend nao recalcula hash.
- Replay continua explicito.
- Card bloqueado continua visivel.
- Hash/payload persistido continuam validados pelo backend.

Comandos de verificacao:

```bat
python -m compileall -q processamento decisao
pytest teste_frontend_payload.py teste_frontend_explicabilidade.py teste_replay_decisao.py
```

## Fase P5 - Pre-Coleta Operacional Antes do Radar

Objetivo:
Separar coleta de dados e decisao, executando uma etapa operacional que prepara base local antes do Radar.

Arquivos permitidos:

- `operacional/`
- `coleta/contexto_ativo.py`
- `processamento/estrategia.py`
- `api/auditoria.py`
- `teste_healthcheck.py`
- novo teste: `teste_precoleta_operacional.py`

Contratos obrigatorios:

- Pre-coleta pode acessar rede apenas quando chamada explicitamente.
- Healthcheck nao pode executar scraping.
- Radar deve continuar funcionando sem pre-coleta, porem com mais bloqueios.

Comandos de verificacao:

```bat
python -m compileall -q operacional coleta processamento api
pytest teste_healthcheck.py teste_precoleta_operacional.py teste_performance_radar.py
```

## Fase P6 - Metricas de Performance Real

Objetivo:
Medir tempo por etapa, cache hit/miss, fontes falhas, bloqueios por motivo e custo operacional do Radar.

Arquivos permitidos:

- `sistema/observabilidade.py`
- `processamento/estrategia.py`
- `teste_observabilidade_performance.py`
- `teste_performance_radar.py`

Contratos obrigatorios:

- Logs estruturados em JSON.
- Testes Zero DB devem continuar bloqueando I/O de disco.
- Nao versionar `.jsonl`.

Comandos de verificacao:

```bat
python -m compileall -q sistema processamento
pytest teste_observabilidade_performance.py teste_performance_radar.py teste_proibicao_sqlite.py
```

## Template de Resposta Final por Bloco

```text
Bloco executado:
Arquivos alterados:
Contratos preservados:
Testes executados:
Commit:
Riscos/residuais:
Proximo bloco recomendado:
```
