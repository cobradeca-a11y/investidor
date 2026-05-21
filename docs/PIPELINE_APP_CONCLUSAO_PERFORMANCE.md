# Pipeline final - App concluido e performando

Objetivo: fechar os residuos operacionais que ainda impedem o FIIA de rodar como app local confiavel, auditavel e rapido.

## Bloco P1 - FNET/PDF robusto

Problema:
- A FNET pode devolver HTML, erro, JSON ou arquivo vazio no endpoint de download.
- O app tentava abrir qualquer resposta com `pdfplumber`, gerando `No /Root object`.

Execucao:
- Validar `Content-Type`, assinatura `%PDF` e tamanho minimo antes do parser.
- Registrar falha controlada e retornar fallback seguro.
- Nao quebrar o radar quando o documento nao for PDF.

Verificacao:
- `[UVICORN: nao necessario]` `python -m compileall -q coleta processamento`
- `[UVICORN: nao necessario]` `pytest teste_relatorio_fnet.py`

Status:
- Implementado neste ciclo.

## Bloco P2 - CNPJ canonico por tabela mestre

Problema:
- O resolvedor legado de CNPJ ainda dependia de CSV em cwd e de tabela `fiis`.
- Tickers ausentes na tabela mestre precisam falhar de forma controlada.

Execucao:
- Consultar primeiro `fiia_tabela_mestre_fiis`.
- Depois consultar `fiis`.
- Depois CSV local com caminho absoluto a partir da raiz do projeto.
- Por ultimo, fallback CVM remoto.

Verificacao:
- `[UVICORN: nao necessario]` `pytest teste_relatorio_fnet.py`
- `[UVICORN: nao necessario]` `python bootstrap_cvm.py --so-tabela`
- `[UVICORN: nao necessario]` `python -c "from coleta.cnpj_fundo import obter_cnpj; print(obter_cnpj('KORE11'))"`

Status:
- Implementado neste ciclo.

## Bloco P3 - Estabilidade da IA qualitativa

Problema:
- Quando FNET falha e a analise cai em noticias/fallback, duas execucoes proximas podem gerar scores diferentes.
- Isso pode mudar `COMPRAR_PARCIAL` para `MONITORAR` sem mudanca fundamentalista.

Execucao:
- Criar cache auditavel de analise qualitativa por ticker e fingerprint dos dados fundamentais.
- Reutilizar resultado OK por 24h quando os dados fundamentais nao mudaram.
- Nao cachear bloqueios por dados insuficientes nem ausencia de chave.

Verificacao:
- `[UVICORN: nao necessario]` `python -m compileall -q processamento coleta`
- `[UVICORN: nao necessario]` `pytest teste_analise_qualitativa_cache.py`

Status:
- Implementado neste ciclo.

## Bloco P4 - Radar assincrono na PWA

Problema:
- `/api/radar` ainda executa de forma sincrona.
- Em mobile ou rede lenta, pode parecer travado.

Execucao futura:
- Criar `POST /api/radar/jobs`.
- Criar `GET /api/radar/jobs/{id}`.
- Criar cache de ultimo resultado completo.
- PWA deve fazer polling e nunca bloquear a tela indefinidamente.

Verificacao:
- `[UVICORN: nao necessario]` `pytest teste_api_radar_jobs.py`
- `[UVICORN: necessario]` smoke visual PWA.

Status:
- Implementado neste ciclo como API paralela. O endpoint sincrono `/api/radar` foi preservado.
- PWA migrada para `POST /api/radar/jobs` + polling em `GET /api/radar/jobs/{id}`, com fallback para `/api/radar`.

## Bloco P5 - Cobertura documental FNET operacional

Problema:
- FNET em tempo real e scraping PDF sao instaveis.
- A fonte mais robusta e importar metadados/documentos para tabelas locais.

Execucao futura:
- Rodar carga CVM/FNET documental.
- Medir cobertura por `/api/auditoria/cobertura/fnet`.
- Usar documentos persistidos como fonte preferencial.

Verificacao:
- `[UVICORN: necessario]` `curl -H "x-api-key: ..." http://127.0.0.1:8080/api/auditoria/cobertura/fnet`

Status:
- Implementado parcialmente neste ciclo: metadados FNET consultados ao vivo passam a ser persistidos localmente, e consultas futuras tentam usar documento local antes do download/busca ao vivo.
- Busca FNET ao vivo ampliada para prioridade `INFORME_MENSAL` -> `INFORME_TRIMESTRAL` -> `INFORME_ANUAL`.
- Continua pendente a rotina operacional de carga ampla para elevar cobertura historica.

## Bloco P6 - Homologacao final

Execucao:
- `[UVICORN: nao necessario]` `python -m compileall -q acesso api aprendizado backtest banco cadastro carteira coleta config decisao educacao mercado operacional processamento relatorios servicos sistema validacao app.py main.py`
- `[UVICORN: nao necessario]` `pytest teste_proibicao_sqlite.py teste_regressao_zero_db.py teste_contrato_gates.py teste_contrato_decisao.py teste_auditoria_decisao.py`
- `[UVICORN: nao necessario]` `pytest teste_healthcheck.py teste_seguranca_api.py teste_api_decisoes.py teste_replay_decisao.py`
- `[UVICORN: nao necessario]` `pytest teste_relatorio_fnet.py teste_analise_qualitativa_cache.py teste_cvm_informe_mensal_parse.py`
- `[UVICORN: necessario]` validar PWA com `uvicorn app:app --host 127.0.0.1 --port 8080 --reload`

Status:
- Parcialmente executado neste ciclo.
