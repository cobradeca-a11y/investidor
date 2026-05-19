# FIIA — Deploy e Operação

Este documento descreve como executar o FIIA em ambiente local, staging ou produção com configuração explícita.

## 1. Princípios de deploy

- O arquivo `.env` nunca deve ser versionado.
- Use `.env.example` apenas como modelo, sem segredos reais.
- Produção deve exigir `FIIA_API_KEY` explícita, longa e não padrão.
- O build não depende de banco SQLite local versionado.
- Dados persistentes do container ficam em volume Docker, não no repositório.
- O deploy não altera motor, gates, coleta, processamento ou regras de decisão.

## 2. Arquivos de deploy

```text
Dockerfile
docker-compose.yml
.env.example
docs/DEPLOY.md
config/settings.py
.github/workflows/ci.yml
```

## 3. Configuração inicial

Copie o exemplo:

```bash
cp .env.example .env
```

Edite `.env` e defina pelo menos:

```bash
FIIA_ENV=prod
FIIA_DEBUG=0
FIIA_API_KEY=<chave-longa-aleatoria-do-ambiente>
CORS_ALLOWED_ORIGINS=https://seu-dominio.example
```

Em produção, o container executa um preflight de segurança por meio de `validar_configuracao_seguranca()`. Se `FIIA_API_KEY` estiver ausente, curta ou padrão, o container deve falhar antes de iniciar a API.

## 4. Execução local sem Docker

Instalar dependências:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Configurar ambiente:

```bash
cp .env.example .env
```

Rodar validação básica:

```bash
python -m compileall -q config api decisao coleta processamento
pytest teste_seguranca_api.py teste_contrato_decisao.py
```

Iniciar API:

```bash
uvicorn app:app --host 0.0.0.0 --port 8080
```

Acessar interface:

```text
http://localhost:8080/web/index.html
```

## 5. Execução com Docker Compose

Validar configuração do Compose:

```bash
docker compose config
```

Subir aplicação:

```bash
docker compose up --build
```

Subir em segundo plano:

```bash
docker compose up --build -d
```

Ver logs do container:

```bash
docker compose logs -f fiia-app
```

Parar:

```bash
docker compose down
```

## 6. Dados e banco

O Docker Compose usa volume nomeado:

```text
fiia_data:/app/data
```

Esse volume permite persistência fora do repositório. Banco SQLite local, caches, `.jsonl`, logs e `.env` não devem ser versionados.

## 7. Migração/setup

Quando houver migração aditiva ou setup do banco, executar de forma explícita dentro do container:

```bash
docker compose run --rm fiia-app python main.py --setup
```

Se o projeto estiver rodando sem Docker:

```bash
python main.py --setup
```

Antes de migrar em staging/prod:

```bash
python -m compileall -q config api decisao coleta processamento
pytest teste_seguranca_api.py teste_contrato_decisao.py
```

## 8. Testes obrigatórios antes de release

```bash
python -m compileall -q config api decisao coleta processamento
pytest teste_seguranca_api.py teste_contrato_decisao.py
docker compose config
```

Recomendado para release completo:

```bash
pytest teste_proibicao_sqlite.py teste_regressao_zero_db.py teste_contrato_gates.py teste_auditoria_decisao.py teste_api_decisoes.py teste_replay_decisao.py
```

## 9. Rollback

Rollback de container:

```bash
docker compose down
git checkout <tag-ou-commit-estavel>
docker compose up --build -d
```

Rollback de configuração:

```bash
cp .env.backup .env
docker compose up -d
```

Rollback de dados deve ser feito a partir de backup do volume/banco antes da migração. Não apague volumes em produção sem backup.

## 10. Staging

Sugestão de `.env` para staging:

```bash
FIIA_ENV=staging
FIIA_DEBUG=0
FIIA_OBSERVABILIDADE=1
FIIA_API_KEY=<chave-staging-longa>
CORS_ALLOWED_ORIGINS=https://staging.seu-dominio.example
```

Staging deve validar:

- API sobe com chave explícita;
- dashboard carrega;
- endpoints sensíveis exigem autenticação;
- histórico/replay não executa scraping por padrão;
- Zero DB Query Mode permanece íntegro.

## 11. Produção

Produção exige:

- `FIIA_ENV=prod`;
- `FIIA_DEBUG=0`;
- `FIIA_API_KEY` longa, exclusiva e não padrão;
- `CORS_ALLOWED_ORIGINS` restrito;
- volume persistente configurado;
- CI verde;
- testes críticos executados;
- backup antes de migração.

## 12. Checklist de release/deploy

```text
[ ] .env não versionado.
[ ] .env.example sem segredos reais.
[ ] FIIA_API_KEY explícita em staging/prod.
[ ] FIIA_DEBUG=0 em produção.
[ ] CORS restrito em produção.
[ ] docker compose config passa.
[ ] compileall passa.
[ ] teste_seguranca_api.py passa.
[ ] teste_contrato_decisao.py passa.
[ ] Banco local não versionado.
[ ] Logs, .jsonl, caches e .venv não versionados.
[ ] Backup criado antes de migração.
[ ] Plano de rollback definido.
```
