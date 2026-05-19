# FIIA — Checklist Técnico de Release

Este checklist deve ser executado antes de qualquer tag, deploy, entrega para uso operacional ou integração de bloco crítico.

## 1. Premissa de release

Uma release do FIIA só pode ser considerada pronta quando:

- o branch local está sincronizado com `origin/main`;
- não há alterações locais não commitadas;
- o CI do GitHub Actions está verde;
- os testes críticos foram executados e aprovados;
- nenhum log, banco, `.venv`, cache ou arquivo local foi versionado;
- não houve alteração de regra de decisão fora de bloco aprovado;
- não houve quebra do Zero DB Query Mode.

## 2. Sincronização antes da validação

```bash
git status
git fetch origin
git checkout main
git pull origin main
git status
```

Resultado esperado:

```text
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

Se houver alterações locais, não iniciar release até decidir se serão descartadas, commitadas em bloco próprio ou guardadas em `stash`.

## 3. Arquivos que nunca podem entrar em release

Verificar antes de tag/deploy:

```bash
git status --porcelain=v1 -uall
git ls-files | grep -E '(^logs/|\.jsonl$|\.db$|\.sqlite$|\.sqlite3$|\.db-wal$|\.db-shm$|^\.venv/|^venv/|__pycache__/)' || true
```

A segunda linha não deve retornar arquivos versionados.

Proibido versionar:

- `logs/`;
- `*.jsonl`;
- `*.db`, `*.sqlite`, `*.sqlite3`, `*.db-wal`, `*.db-shm`;
- `.venv/`, `venv/`, `env/`;
- `__pycache__/`, `.pytest_cache/`, caches de ferramentas;
- `.env` real com chaves privadas.

## 4. Variáveis de ambiente obrigatórias

Para uso operacional:

```env
FIIA_API_KEY=chave_operacional_forte
GEMINI_API_KEY=chave_gemini_quando_ia_estiver_habilitada
FIIA_OBSERVABILIDADE=1
```

Para CI/testes:

```env
FIIA_API_KEY=ci-fiia-key
FIIA_OBSERVABILIDADE=0
```

Regras:

- `FIIA_API_KEY` deve proteger endpoints sensíveis.
- `GEMINI_API_KEY` não deve ser exigida em testes determinísticos.
- `FIIA_OBSERVABILIDADE=0` deve tornar logs no-op em testes que bloqueiam I/O.
- `.env` real nunca deve ser commitado.

## 5. Comandos obrigatórios antes da release

Executar exatamente:

```bash
python -m compileall -q acesso api aprendizado backtest banco cadastro carteira coleta config decisao educacao mercado operacional processamento relatorios servicos sistema validacao app.py main.py
pytest teste_proibicao_sqlite.py teste_regressao_zero_db.py teste_contrato_gates.py teste_contrato_decisao.py teste_auditoria_decisao.py
```

Também executar, quando presentes no branch:

```bash
pytest teste_comparacao_motores.py
pytest teste_api_decisoes.py
pytest teste_backtest_snapshot.py
pytest teste_performance_radar.py
pytest teste_observabilidade_performance.py
pytest teste_frontend_payload.py
```

Observação: o comando de planejamento cita `teste_replay_decisao.py`; no estado atual, esse arquivo não existe. A cobertura de replay está em `teste_auditoria_decisao.py` e `teste_api_decisoes.py`. Não criar ou renomear teste fora de bloco autorizado.

## 6. Zero DB Query Mode

Antes de release, confirmar:

- se `contexto` é passado ao motor, o caminho decisório testado não acessa SQLite;
- se `contexto` é passado ao motor, o caminho decisório testado não acessa rede;
- se `contexto` é passado ao motor, o caminho decisório testado não escreve log em disco;
- falha de observabilidade não pode quebrar decisão, radar ou testes;
- logs devem ser estruturados e desativáveis por `FIIA_OBSERVABILIDADE=0`.

Teste obrigatório:

```bash
pytest teste_proibicao_sqlite.py teste_regressao_zero_db.py
```

## 7. Contrato decisório e gates

Antes de release, confirmar:

- `DecisaoFIIA` ou payload equivalente continua sendo contrato final;
- todos os gates preservam estrutura auditável;
- `gates_detalhes` não perde campos essenciais;
- cards bloqueados continuam visíveis;
- `normalizar_contrato_decisao` continua sendo o ponto de normalização do payload final.

Testes obrigatórios:

```bash
pytest teste_contrato_gates.py teste_contrato_decisao.py teste_comparacao_motores.py
```

## 8. Auditoria, replay e hash

Antes de release, confirmar:

- toda decisão persistida contém `payload_json`;
- toda decisão persistida contém `payload_hash`;
- `payload_hash` é SHA-256 do `payload_json` normalizado;
- toda decisão contém `contexto_versao` quando disponível;
- toda decisão contém `versao_motor` quando disponível;
- replay auditável é opcional e explícito;
- endpoint de consulta não dispara scraping nem motor;
- API não expõe stacktrace.

Testes obrigatórios:

```bash
pytest teste_auditoria_decisao.py teste_api_decisoes.py
```

## 9. Backtest institucional

Antes de release, confirmar:

- backtest não usa preço atual como se fosse histórico;
- decisão de backtest usa snapshot histórico quando disponível;
- cada resultado informa `data_referencia`;
- cada resultado informa `snapshot_usado`;
- cada resultado informa `validade_institucional`;
- cada resultado informa `motivo_validade`;
- se não houver snapshot suficiente, `validade_institucional=False`.

Teste obrigatório:

```bash
pytest teste_backtest_snapshot.py
```

## 10. Migração e banco

Antes de release:

- não alterar `schema.sql` sem bloco autorizado;
- toda migração deve ser aditiva;
- proibido `DROP` destrutivo em release operacional;
- fazer backup do banco local/operacional antes de rodar migração;
- validar que `_garantir_tabela()` ou equivalente não apaga histórico.

Checklist de migração:

```text
[ ] Backup do banco realizado.
[ ] Migração aditiva revisada.
[ ] Sem DROP destrutivo.
[ ] Sem recriação destrutiva de tabela.
[ ] Testes de auditoria/persistência aprovados.
```

## 11. Segurança

Antes de release:

- confirmar que endpoints sensíveis exigem `x-api-key`;
- confirmar que `FIIA_API_KEY` está configurada no ambiente operacional;
- confirmar que erros de API não expõem stacktrace;
- confirmar que `.env` não foi versionado;
- confirmar que chaves reais não aparecem em commits, logs ou testes.

## 12. CI obrigatório

A release só pode seguir com GitHub Actions verde.

O CI deve validar:

- clone limpo;
- instalação explícita de dependências;
- ausência de artefatos locais versionados;
- `compileall` no escopo institucional;
- Zero DB Query Mode;
- contratos decisórios;
- gates auditáveis;
- auditoria/hash/replay;
- backtest com snapshot;
- testes estáticos de frontend quando aplicável.

## 13. Rollback

Antes de deploy/tag, registrar:

```text
Versão anterior estável:
Commit atual:
Tag proposta:
Banco usado:
Backup do banco:
Responsável pela validação:
Data/hora:
```

Procedimento de rollback Git:

```bash
git fetch origin
git checkout main
git reset --hard <commit_estavel>
```

Atenção: `git reset --hard` só deve ser usado em procedimento explícito de rollback, nunca como rotina de desenvolvimento sem aprovação.

Rollback operacional:

- parar serviço;
- restaurar commit/tag estável;
- restaurar backup do banco se houve migração;
- subir serviço;
- executar smoke test;
- registrar incidente e motivo.

## 14. Checklist final de aprovação

```text
[ ] Branch sincronizado com origin/main.
[ ] Working tree limpo.
[ ] Nenhum artefato local versionado.
[ ] Variáveis de ambiente revisadas.
[ ] Compileall aprovado.
[ ] Testes Zero DB aprovados.
[ ] Testes de contrato decisório aprovados.
[ ] Testes de gates aprovados.
[ ] Testes de auditoria/hash/replay aprovados.
[ ] Teste de backtest snapshot aprovado.
[ ] CI GitHub Actions verde.
[ ] Backup do banco realizado quando aplicável.
[ ] Rollback definido.
[ ] Tag/release documentada.
```

## 15. Critério de bloqueio

Bloquear release se qualquer item abaixo ocorrer:

- CI vermelho;
- teste Zero DB falhando;
- contrato final da decisão quebrado;
- `gates_detalhes` sem estrutura auditável;
- hash de auditoria inválido;
- backtest usando dado atual como histórico;
- logs/bancos/caches versionados;
- alteração de motor/coleta/schema fora de bloco autorizado;
- endpoint sensível sem autenticação;
- stacktrace exposto em resposta de API.
