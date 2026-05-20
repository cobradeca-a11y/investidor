# Roadmap de Conclusao e Performance do App FIIA

Documento operacional para levar o app do estado atual ate uma versao concluida, estavel e performando em uso local/producao.

## Estado Atual

- CI ativo e verde no GitHub Actions.
- Zero DB Query Mode protegido por testes.
- Auditoria, replay, hash, API key, healthcheck, relatorios e exportacao implementados.
- Radar executa com contexto unificado e cards bloqueados visiveis.
- PWA consome API key pelo `localStorage`.
- Banco local (`fiia.db`) e cache HTTP (`http_cache.sqlite`) sao artefatos runtime e nao devem ser versionados.

## Regra de Uvicorn

- Testes Python, `compileall`, `python main.py --setup` e `python main.py --radar`: `uvicorn` nao e necessario.
- Smoke visual da PWA, chamadas `curl` contra API local e validacao no navegador: `uvicorn app:app --host 127.0.0.1 --port 8080 --reload` e necessario.

## Fase 1 - Sanidade Local

Objetivo: garantir que o clone local esta sincronizado e sem artefatos indevidos.

Comandos:

```bat
git pull
git status
python -m compileall -q acesso api aprendizado backtest banco cadastro carteira coleta config decisao educacao mercado operacional processamento relatorios servicos sistema validacao app.py main.py
```

Aceite:

- `git status` limpo.
- `compileall` sem erros.
- Nenhum `.db`, `.sqlite`, `.jsonl`, `.env` ou `.venv` versionado.

## Fase 2 - Banco e Configuracao

Objetivo: preparar ambiente local seguro.

Comandos:

```bat
python main.py --setup
python -c "from config.settings import FIIA_API_KEY; print(bool(FIIA_API_KEY), len(FIIA_API_KEY))"
```

Aceite:

- Banco criado/migrado.
- `FIIA_API_KEY` existe e tem tamanho seguro.
- Em producao, nao usar chave padrao.

## Fase 3 - Testes Criticos

Objetivo: garantir que os contratos principais continuam validos.

Comandos:

```bat
pytest teste_proibicao_sqlite.py teste_regressao_zero_db.py teste_contrato_gates.py teste_contrato_decisao.py teste_auditoria_decisao.py
pytest teste_healthcheck.py teste_seguranca_api.py teste_replay_decisao.py teste_relatorios_auditaveis.py teste_exportacao_relatorios.py
pytest teste_performance_radar.py teste_diagnostico_bloqueios_radar.py teste_precoleta_operacional.py teste_relatorio_fnet.py teste_observabilidade_performance.py
```

Aceite:

- Todos os testes passam.
- Zero DB continua sem SQLite/rede/log de disco no caminho decisorio com contexto.

## Fase 4 - Radar Operacional

Objetivo: executar o Radar com base local e medir resultado real.

Comando:

```bat
python main.py --radar
```

Aceite:

- Radar nao quebra.
- Erros de fonte externa sao tratados como bloqueio/fallback, nao traceback.
- Quantidade de bloqueios por `liquidez` cai quando o dado existe no pre-filtro/Fundamentus.
- Decisoes sao persistidas com payload auditavel.

## Fase 5 - PWA e API Local

Objetivo: validar experiencia visual e endpoints.

Comando:

```bat
uvicorn app:app --host 127.0.0.1 --port 8080 --reload
```

Abrir:

```text
http://127.0.0.1:8080/web/index.html
```

No navegador:

```js
localStorage.setItem("fiia_api_key", "SUA_CHAVE_FIIA")
```

Aceite:

- `/api/carteira/posicoes` retorna 200 com chave.
- `/api/radar` retorna cards.
- Cards bloqueados aparecem com motivo, campos ausentes e fontes falhas.
- Historico carrega sem replay automatico.
- Replay so executa por botao explicito.

## Fase 6 - Healthcheck e Jobs

Objetivo: validar operacao sem scraping involuntario.

Comandos:

```bat
curl http://127.0.0.1:8080/api/auditoria/health
curl -H "x-api-key: SUA_CHAVE_FIIA" http://127.0.0.1:8080/api/auditoria/health/profundo
curl -X POST -H "x-api-key: SUA_CHAVE_FIIA" http://127.0.0.1:8080/api/auditoria/jobs/verificacao-operacional
curl -X POST -H "x-api-key: SUA_CHAVE_FIIA" "http://127.0.0.1:8080/api/auditoria/jobs/precoleta-operacional?executar=false&tickers=HGLG11,KNCR11"
```

Aceite:

- Health basico OK.
- Health profundo pode retornar ALERTA se CVM/FNET locais estiverem vazios, sem rede.
- Pre-coleta com `executar=false` nao faz scraping.
- Pre-coleta real so com `executar=true` e chamada explicita.

## Fase 7 - Performance Real

Objetivo: medir e reduzir gargalos.

Indicadores a acompanhar:

- tempo total do Radar;
- tempo de coleta;
- tempo de decisao;
- tempo de IA;
- cache hit/miss;
- bloqueios por motivo;
- falhas por fonte;
- quantidade de finalistas com margem calculada.

Aceite:

- Radar conclui sem traceback.
- Logs estruturados mostram metricas.
- Fontes instaveis nao derrubam o processo.
- Ativos bloqueados continuam auditaveis.

## Fase 8 - Ajustes Finais Para Performance

Prioridades:

1. Reduzir chamadas qualitativas IA para ativos ja bloqueados.
2. Preencher `liquidez_diaria` por pre-filtro/Fundamentus antes do fail-closed.
3. Melhorar cobertura CVM/FNET local por jobs explicitos.
4. Reusar contexto por ciclo respeitando `VERSAO_CONTEXTO`.
5. Evitar chamadas externas duplicadas por ticker.

Arquivos sensiveis:

- Nao alterar `decisao/motor_decisao.py` sem aprovacao.
- Nao alterar thresholds sem aprovacao.
- Nao versionar runtime data.

## Fase 9 - Release

Checklist:

- CI verde.
- `git status` limpo.
- Smoke local PWA aprovado.
- `python main.py --radar` aprovado.
- Health basico OK.
- Health profundo sem stacktrace.
- Replay explicito funcionando.
- Exportacao CSV/JSON funcionando.
- Documentacao atualizada.

## Resposta Padrao de Fechamento

```text
Bloco executado:
Arquivos alterados:
Contratos preservados:
Testes executados:
Commit:
Riscos/residuais:
Proximo bloco recomendado:
```
