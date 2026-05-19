# FIIA — Segurança e Operação

Este documento define o hardening mínimo de segurança para operar o FIIA em desenvolvimento, CI e produção.

## 1. Princípios

- API sensível deve falhar fechada quando não houver `FIIA_API_KEY`.
- Ambiente de produção não pode aceitar chave padrão, curta ou vazia.
- Erros de autenticação não podem expor segredos, valores de chave ou stacktrace.
- `.env` é permitido apenas em desenvolvimento local e nunca deve ser versionado.
- Logs, bancos, `.venv`, caches e arquivos locais não podem entrar no Git.
- Rate limit deve ser configurável e não deve bloquear testes locais sem ativação explícita.
- Segurança não pode alterar cálculo de decisão, motor, coleta ou schema.

## 2. Variáveis de ambiente

### Desenvolvimento local

```env
FIIA_ENV=dev
FIIA_API_KEY=uma_chave_local_forte_para_teste_manual
FIIA_OBSERVABILIDADE=1
FIIA_RATE_LIMIT_ENABLED=0
GEMINI_API_KEY=sua_chave_quando_ia_estiver_habilitada
```

O uso de `.env` é aceito apenas localmente. O arquivo `.env` real não deve ser commitado.

### CI

```env
FIIA_ENV=ci
FIIA_API_KEY=ci-fiia-key
FIIA_OBSERVABILIDADE=0
FIIA_RATE_LIMIT_ENABLED=0
```

No CI, a observabilidade deve ficar desligada para evitar escrita de logs em disco durante testes que bloqueiam I/O. O rate limit fica desligado salvo em testes dedicados que ativam a configuração explicitamente.

### Produção

```env
FIIA_ENV=prod
FIIA_API_KEY=<chave_forte_com_no_minimo_24_caracteres>
FIIA_OBSERVABILIDADE=1
FIIA_DEBUG=0
FIIA_RATE_LIMIT_ENABLED=1
FIIA_RATE_LIMIT_WINDOW_SECONDS=60
FIIA_RATE_LIMIT_DEFAULT_MAX=120
FIIA_RATE_LIMIT_SENSITIVE_MAX=30
FIIA_RATE_LIMIT_RADAR_MAX=3
```

Em produção, a aplicação deve bloquear configuração com chave vazia, curta ou padrão.

## 3. Chaves proibidas em produção

Não usar em produção:

- vazio;
- `changeme`;
- `change-me`;
- `default`;
- `password`;
- `123456`;
- `fiia-api-key`;
- `fiia-teste`;
- `ci-fiia-key`;
- qualquer chave curta.

## 4. Autenticação

A autenticação sensível deve usar o header:

```text
x-api-key: <FIIA_API_KEY>
```

Regras:

- sem chave configurada: bloquear;
- chave ausente no request: bloquear;
- chave incorreta: bloquear;
- produção com chave insegura: bloquear;
- comparação deve usar `secrets.compare_digest`.

## 5. Rate limit operacional

O rate limit é configurável por ambiente e fica desligado por padrão para não travar desenvolvimento local nem testes automatizados sem configuração explícita.

Variáveis:

```env
FIIA_RATE_LIMIT_ENABLED=1
FIIA_RATE_LIMIT_WINDOW_SECONDS=60
FIIA_RATE_LIMIT_DEFAULT_MAX=120
FIIA_RATE_LIMIT_SENSITIVE_MAX=30
FIIA_RATE_LIMIT_RADAR_MAX=3
```

Escopos previstos:

- `default`: consultas gerais;
- `sensivel`: endpoints protegidos por API key, carteira e auditoria auditável;
- `radar`: chamadas pesadas do radar, quando o endpoint estiver conectado à camada de rate limit.

Regras:

- bloqueios retornam HTTP `429`;
- logs de bloqueio são estruturados;
- logs não armazenam API key nem IP completo;
- identificação usa hash curto do cliente;
- rate limit não deve alterar decisão, motor, coleta ou contrato final da decisão.

## 6. Mensagens de erro

Mensagens de autenticação e bloqueio devem ser genéricas:

```text
API key ausente ou inválida.
Autenticação da API não configurada.
Configuração de autenticação inválida para produção.
Muitas requisições. Tente novamente mais tarde.
```

Não retornar:

- valor da chave;
- IP completo em resposta;
- nome de variável com valor;
- stacktrace;
- exceção crua;
- conteúdo do `.env`.

## 7. Headers defensivos

A camada de segurança fornece headers recomendados:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Cache-Control: no-store
```

Quando o middleware global for habilitado, esses headers devem ser aplicados às respostas HTTP.

## 8. Logs e observabilidade

- Logs devem ser estruturados.
- Logs não devem conter segredos.
- Logs de rate limit devem conter apenas hash do cliente, escopo, limite, janela e tentativas.
- Logs devem poder virar no-op em testes com `FIIA_OBSERVABILIDADE=0`.
- `logs/`, `*.jsonl` e `*.log` nunca devem ser versionados.

## 9. Testes obrigatórios

Antes de homologar segurança:

```bash
python -m compileall -q api acesso config sistema
pytest teste_rate_limit.py teste_seguranca_api.py
pytest teste_proibicao_sqlite.py
```

## 10. Checklist de segurança antes de deploy

```text
[ ] FIIA_ENV=prod em produção.
[ ] FIIA_API_KEY forte configurada no ambiente.
[ ] Nenhuma chave padrão em produção.
[ ] FIIA_DEBUG=0 em produção.
[ ] FIIA_RATE_LIMIT_ENABLED=1 em produção.
[ ] Limites por escopo revisados.
[ ] .env real fora do Git.
[ ] Logs e bancos fora do Git.
[ ] Endpoints sensíveis exigem x-api-key.
[ ] Endpoints sensíveis possuem rate limit configurável.
[ ] Erros de autenticação não expõem segredo.
[ ] Bloqueios 429 não expõem IP completo nem API key.
[ ] Testes de segurança passam.
[ ] Testes de rate limit passam.
[ ] Zero DB Query Mode preservado.
```
