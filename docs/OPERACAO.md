# FIIA — Guia de Operação Técnica

Este documento descreve como operar o FIIA em ambiente local/operacional sem quebrar contratos críticos de decisão, auditoria, logs, banco e release.

## 1. Princípio operacional

A arquitetura operacional do FIIA segue a cadeia:

```text
coleta resolve dados
↓
contexto normaliza
↓
motor decide
↓
persistência audita
↓
interface exibe
```

Regra central:

> Se `contexto` for passado ao motor, o caminho decisório testado não pode consultar SQLite, rede ou log de disco.

## 2. Preparação do ambiente

Criar ambiente virtual local sem versionar:

```bash
python -m venv .venv
.venv\Scripts\activate
```

No Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Instalar dependências:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Variáveis de ambiente

Criar `.env` local, nunca versionado:

```env
FIIA_API_KEY=sua_chave_operacional
GEMINI_API_KEY=sua_chave_gemini
FIIA_OBSERVABILIDADE=1
```

Para testes isolados:

```env
FIIA_API_KEY=ci-fiia-key
FIIA_OBSERVABILIDADE=0
```

## 4. Inicialização

Inicializar banco local quando necessário:

```bash
python main.py --setup
```

Rodar radar CLI:

```bash
python main.py --radar
```

Subir API/PWA:

```bash
python app.py
```

Acesso padrão:

```text
http://0.0.0.0:8080
```

## 5. Healthchecks operacionais

### Healthcheck básico

Endpoint:

```text
GET /api/auditoria/health
```

Características:

- não exige API key;
- não aciona scraping;
- não consulta fontes externas;
- não executa Radar;
- não chama motor decisório;
- valida apenas API, configuração e observabilidade.

### Healthcheck profundo

Endpoint protegido:

```text
GET /api/auditoria/health/profundo
```

Características:

- exige `x-api-key`;
- é explícito;
- verifica banco por `SELECT 1`;
- verifica tabelas mínimas;
- verifica sinais locais de fontes críticas sem rede;
- não executa scraping;
- não chama motor decisório;
- não executa Radar por padrão.

Para solicitar verificação operacional do Radar sem executor autorizado:

```text
GET /api/auditoria/health/profundo?incluir_radar=true
```

Esse modo registra que o Radar exige execução explícita/autorizada, mas não chama o pipeline proibido.

## 6. Jobs operacionais

Endpoint protegido:

```text
POST /api/auditoria/jobs/verificacao-operacional
```

Características:

- exige `x-api-key`;
- executa healthcheck profundo seguro;
- registra status estruturado via observabilidade;
- não aciona scraping;
- não executa motor;
- não altera decisão.

Status possíveis:

```text
OK
ALERTA
ERRO
NAO_EXECUTADO
```

## 7. Rotina antes de operar

```bash
git status
git fetch origin
git pull origin main
git status
```

Não operar se:

- houver alterações locais não revisadas;
- CI estiver vermelho;
- banco tiver migração pendente não validada;
- `.env` não estiver configurado;
- `FIIA_API_KEY` não estiver definida para endpoints protegidos.

## 8. Testes mínimos de operação

Antes de usar o radar ou publicar release:

```bash
python -m compileall -q acesso api aprendizado backtest banco cadastro carteira coleta config decisao educacao mercado operacional processamento relatorios servicos sistema validacao app.py main.py
pytest teste_proibicao_sqlite.py teste_regressao_zero_db.py teste_contrato_gates.py teste_contrato_decisao.py teste_auditoria_decisao.py
```

Testes complementares recomendados:

```bash
pytest teste_healthcheck.py
pytest teste_seguranca_api.py
pytest teste_comparacao_motores.py
pytest teste_api_decisoes.py
pytest teste_backtest_snapshot.py
pytest teste_performance_radar.py
pytest teste_observabilidade_performance.py
pytest teste_frontend_payload.py
```

## 9. Operação do radar

O radar pode ser executado por CLI ou API/PWA.

Regras:

- não interpretar saída como recomendação financeira automática;
- sempre considerar decisão como análise operacional auditável;
- conferir `gate_parada`, `trilha_gates`, `gates_detalhes`, `confianca`, `fonte_patrimonial`, `payload_hash` e alertas;
- cards bloqueados são parte correta do sistema, não erro visual;
- se uma fonte externa falhar, o sistema deve degradar para bloqueio/monitoramento, não inventar dado.

## 10. Auditoria de decisões

Toda decisão persistida deve carregar, quando disponível:

- `payload_json`;
- `payload_hash`;
- `contexto_versao`;
- `versao_motor`;
- `gates_detalhes`;
- `trilha_gates`;
- motivo e decisão.

Consulta auditável via API protegida:

```text
GET /api/auditoria/decisoes/auditaveis
GET /api/auditoria/decisoes/{decisao_id}/auditavel?replay=false
GET /api/auditoria/decisoes/{decisao_id}/auditavel?replay=true
```

Regras:

- `replay=true` deve ser explícito;
- consulta auditável não deve disparar scraping;
- consulta auditável não deve chamar motor decisório;
- erro de API não deve expor stacktrace.

## 11. Backtest institucional

Backtest institucional válido exige snapshot histórico suficiente.

Campos obrigatórios em cada resultado:

- `data_referencia`;
- `snapshot_usado`;
- `validade_institucional`;
- `motivo_validade`.

Se não houver snapshot suficiente:

```text
validade_institucional=False
```

O backtest não pode usar preço atual como se fosse histórico.

## 12. Observabilidade e logs

Logs devem ser estruturados em JSON Lines quando habilitados.

Configuração:

```env
FIIA_OBSERVABILIDADE=1
```

Para testes:

```env
FIIA_OBSERVABILIDADE=0
```

Nunca versionar:

- `logs/`;
- `*.jsonl`;
- `*.log`.

## 13. Banco e migração

Regras:

- banco SQLite local nunca deve ser versionado;
- migração deve ser aditiva;
- não usar `DROP` destrutivo sem plano aprovado;
- fazer backup antes de migração;
- validar persistência depois da migração.

Arquivos locais proibidos no Git:

```text
*.db
*.sqlite
*.sqlite3
*.db-wal
*.db-shm
```

## 14. Segurança operacional

- Endpoints sensíveis devem usar `x-api-key`.
- `FIIA_API_KEY` deve existir no ambiente operacional.
- `.env` real não deve ser commitado.
- Logs não devem conter chaves reais.
- Erros de API devem retornar mensagem controlada.
- Stacktrace deve ficar apenas em observabilidade interna, quando habilitada.

## 15. Rollback operacional

Antes de cada release, registrar:

```text
Commit atual:
Último commit estável:
Tag proposta:
Backup do banco:
Responsável:
Data/hora:
```

Rollback de código:

```bash
git fetch origin
git checkout main
git reset --hard <commit_estavel>
```

Rollback de dados:

- parar serviço;
- restaurar backup do banco;
- subir serviço;
- executar smoke test;
- registrar motivo do rollback.

## 16. Smoke test após subir

Executar:

```bash
python -m compileall -q api sistema operacional config
pytest teste_healthcheck.py teste_seguranca_api.py
```

Verificar manualmente:

```text
[ ] API sobe sem erro.
[ ] GET /api/auditoria/health retorna status operacional.
[ ] GET /api/auditoria/health/profundo exige autenticação.
[ ] POST /api/auditoria/jobs/verificacao-operacional exige autenticação.
[ ] PWA carrega.
[ ] Carteira abre.
[ ] Radar executa ou bloqueia com motivo.
[ ] Auditoria mostra hash/contexto/motor quando disponível.
[ ] Logs não são versionados.
[ ] Banco local não aparece no git status.
```

## 17. Encerramento da operação

Após operação local:

```bash
git status --porcelain=v1 -uall
```

Se aparecerem logs, bancos ou caches, não versionar. Conferir `.gitignore` e limpar apenas artefatos locais, sem apagar código.

## 18. Critérios para considerar operação saudável

```text
[ ] CI verde.
[ ] Testes críticos verdes.
[ ] Healthcheck básico saudável.
[ ] Healthcheck profundo autenticado saudável ou com alerta operacional explicado.
[ ] Job operacional registra status estruturado.
[ ] Zero DB preservado.
[ ] Decisões persistidas com hash.
[ ] Replay auditável funcionando.
[ ] Backtest invalida ausência de snapshot.
[ ] PWA renderiza cards bloqueados.
[ ] Logs e bancos fora do Git.
[ ] Rollback documentado.
```