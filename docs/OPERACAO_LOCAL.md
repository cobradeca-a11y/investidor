# FIIA - Guia de Operacao Local

Este guia descreve o fluxo local para bootstrap, execucao, testes e diagnostico do FIIA.

## Arquivos locais nao versionados

| Arquivo/Pasta | Descricao |
|---|---|
| `fiia.db` | Banco SQLite principal: decisoes, carteira, cache e historico |
| `.env` | Chaves de API (`FIIA_API_KEY`, `GEMINI_API_KEY`) |
| `tabela_mestre_fiia_fiis_b3_cvm.csv` | Mapeamento ticker -> CNPJ CVM |
| `http_cache.sqlite` | Cache local de requisicoes HTTP usado por bibliotecas/coletas |
| `__pycache__/` | Cache Python |
| `logs/` | Logs de observabilidade |

Esses arquivos nao devem ser commitados. O `.gitignore` protege os principais artefatos locais, mas antes de qualquer push confirme com `git status`.

## Primeira vez

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Criar o `.env`

```bash
FIIA_API_KEY=sua_chave_operacional
GEMINI_API_KEY=sua_chave_gemini
```

A `FIIA_API_KEY` pode ser qualquer string segura gerada localmente. Sem ela, endpoints protegidos retornam `401`.

Sem `GEMINI_API_KEY`, a analise qualitativa fica indisponivel ou limitada por fallback; o radar deve continuar operando sem derrubar o job.

### 3. Inicializar o banco

```bash
python main.py --setup
```

### 4. Importar tabela mestre ticker -> CNPJ CVM

```bash
python -c "from coleta.tabela_mestre_fiis import importar_csv; print(importar_csv('tabela_mestre_fiia_fiis_b3_cvm.csv'))"
```

Esperado:

```text
{'registros': 513, 'ignorados': 0, ...}
```

### 5. Coletar informes mensais CVM

```bash
python -c "from coleta.cvm_informe_mensal import coletar_ano; print(coletar_ano(2025))"
python -c "from coleta.cvm_informe_mensal import coletar_ano; print(coletar_ano(2026))"
```

O retorno esperado tem `registros_processados` preenchido. O total pode variar conforme a CVM publique novos arquivos.

### 6. Verificar cadeia patrimonial

```bash
python -c "from servicos.cvm_fii_service import calcular_pvp_cvm; print(calcular_pvp_cvm('HGLG11'))"
```

Esperado: `status: OK`, `fonte: CVM_INF_MENSAL` e `pvp_cvm` numerico.

## Iniciar o servidor

```bash
uvicorn app:app --host 127.0.0.1 --port 8080 --reload
```

Acessar:

```text
http://localhost:8080/web/index.html
```

`[UVICORN: necessario]` para smoke visual da PWA, chamadas `curl` contra a API local e execucao do radar pela interface.

`[UVICORN: nao necessario]` para `pytest`, `compileall`, bootstrap por CLI e comandos Python diretos.

## Configurar a API key na PWA

No navegador, cole a mesma chave do `.env` quando a interface solicitar. Alternativamente, no console do Chrome:

```js
localStorage.setItem('fiia_api_key', 'SUA_CHAVE_DO_ENV')
location.reload()
```

Use a chave operacional do FIIA, nao uma chave Gemini/OpenRouter.

## Rotina de atualizacao mensal

```bash
git pull
pip install -r requirements.txt
python main.py --setup
python -c "from coleta.cvm_informe_mensal import coletar_ano; print(coletar_ano(2026))"
python -c "from coleta.tabela_mestre_fiis import importar_csv; print(importar_csv('tabela_mestre_fiia_fiis_b3_cvm.csv'))"
```

Se a virada de ano ja ocorreu, rode tambem o ano novo no `coletar_ano`.

## Suite de testes

### Nucleo obrigatorio

```bash
pytest teste_proibicao_sqlite.py teste_regressao_zero_db.py teste_contrato_gates.py teste_contrato_decisao.py teste_auditoria_decisao.py teste_healthcheck.py
```

### Suite ampla

```bash
pytest teste_seguranca_api.py teste_api_decisoes.py teste_replay_decisao.py teste_relatorio_fnet.py teste_analise_qualitativa_cache.py teste_cvm_informe_mensal_parse.py teste_exportacao_relatorios.py teste_relatorios_auditaveis.py teste_frontend_explicabilidade.py teste_frontend_payload.py teste_frontend_replay.py teste_governanca_fontes.py teste_observabilidade_performance.py teste_rate_limit.py teste_score_fontes.py teste_cvm_fnet_documentos.py teste_performance_radar.py teste_api_radar_jobs.py
```

## Endpoints principais

| Endpoint | Metodo | Auth | Descricao |
|---|---|---|---|
| `/web/index.html` | GET | nao | PWA |
| `/api/carteira/posicoes` | GET | sim | Posicoes da carteira |
| `/api/radar/jobs` | POST | sim | Inicia radar assincrono |
| `/api/radar/jobs/{id}` | GET | sim | Consulta progresso do radar |
| `/api/radar/ultimo` | GET | sim | Ultimo resultado do radar na instancia |
| `/api/auditoria/health` | GET | nao | Healthcheck basico |
| `/api/auditoria/health/profundo` | GET | sim | Healthcheck profundo sem radar por padrao |
| `/api/setup/cvm/status` | GET | nao | Cobertura CVM no banco |
| `/api/setup/cvm/completo` | POST | sim | Bootstrap CVM via API |
| `/api/auditoria/cobertura-fnet` | GET | sim | Cobertura documental FNET |

## Diagnostico rapido

### Patrimonio sai como `banco_historico`

O ticker pode nao estar resolvido na tabela mestre ou o informe CVM ainda nao foi coletado. Rode a importacao da tabela mestre e `coletar_ano` do ano corrente.

### IA sempre `INDISPONIVEL`

Verifique `GEMINI_API_KEY` no `.env`. O app deve continuar operando, mas a qualidade da analise qualitativa cai.

### Radar demora muito

Na primeira execucao e normal: o radar varre mercado, consulta fontes externas e pode chamar IA. A PWA usa job assincrono para nao bloquear a interface. A etapa qualitativa possui cache local por fingerprint.

### PWA retorna `401`

A `fiia_api_key` do `localStorage` nao bate com a `FIIA_API_KEY` do `.env`. Reconfigure a chave na PWA.

### Chrome pede `/.well-known/appspecific/com.chrome.devtools.json`

Pode ignorar. E uma requisicao auxiliar do Chrome DevTools e nao indica falha do FIIA.

