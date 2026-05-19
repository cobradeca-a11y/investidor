# FIIA — UX de Explicabilidade da Decisão

Este documento descreve a visualização de decisão no dashboard do FIIA.

## 1. Objetivo

Melhorar a leitura da decisão sem alterar motor, payload da API, cálculo, gates, coleta ou contrato decisório.

A interface deve mostrar:

- decisão;
- confiança;
- gates;
- motivos;
- fontes;
- métricas;
- penalidades;
- bloqueios;
- versão de contexto;
- versão do motor;
- hash auditável;
- histórico de decisões;
- replay quando solicitado explicitamente.

## 2. Contrato de frontend

O frontend pode normalizar dados para exibição, mas não pode alterar o payload original recebido da API.

O frontend não pode:

- recalcular hash;
- recalcular decisão;
- alterar gates;
- aplicar regras de motor;
- esconder cards bloqueados;
- disparar replay automaticamente;
- exigir campos obrigatórios inexistentes para renderizar.

## 3. Campos ausentes

Campos ausentes devem ser renderizados com fallback seguro, como:

```text
Não informado
---
Detalhamento de gates não informado
```

O card deve continuar visível mesmo quando:

- `gates_detalhes` não vier no payload;
- `payload_hash` estiver ausente;
- `contexto_versao` estiver ausente;
- `fonte_patrimonial` estiver ausente;
- `permitir_decisao` não vier informado;
- `replay` não estiver presente.

## 4. Cards bloqueados

Cards bloqueados devem continuar visíveis.

Critérios visuais:

- borda avermelhada;
- fundo de cautela;
- resumo operacional informando `Bloqueado / cautela`;
- motivo do bloqueio quando disponível;
- campos de auditoria abertos em painel expansível.

## 5. gates_detalhes

Quando `gates_detalhes` existir, o dashboard deve exibir:

- gate;
- status;
- motivos;
- fontes;
- métricas;
- penalidades.

Quando não existir, deve exibir mensagem de ausência sem quebrar o card.

## 6. Auditoria

O painel de auditoria exibe:

- hash salvo;
- validade do hash, quando informada pela API;
- contexto;
- motor;
- fonte patrimonial;
- confiança dos dados;
- permissão de decisão;
- replay;
- bloqueios/falhas;
- gates detalhados.

O frontend apenas exibe o hash recebido. A integridade não é recalculada no navegador.

## 7. Histórico e replay no dashboard

O dashboard possui um painel `Histórico e Replay` criado em `static/app.js`.

Fluxo:

```text
Carregar histórico
↓
GET /api/auditoria/decisoes/auditaveis?limite=30
↓
Lista decisões salvas com hash auditável
↓
Ver auditoria = consulta detalhe com replay=false
Executar replay = consulta detalhe com replay=true
```

Regras:

- histórico exige `fiia_api_key` no `localStorage`;
- histórico usa endpoints auditáveis autenticados;
- consulta de histórico não executa replay por padrão;
- replay só ocorre quando o usuário clica em `Executar replay`;
- a UI deve tolerar ausência de replay e mostrar `Não executado`;
- o frontend não recalcula hash;
- o frontend não chama motor diretamente;
- o frontend não aciona scraping.

## 8. Endpoints utilizados

```text
GET /api/auditoria/decisoes/auditaveis?limite=30
GET /api/auditoria/decisoes/{decisao_id}/auditavel?incluir_payload=true&replay=false
GET /api/auditoria/decisoes/{decisao_id}/auditavel?incluir_payload=true&replay=true
```

`replay=true` é sempre explícito e acionado por botão dedicado.

## 9. Arquivos envolvidos

- `static/app.js`: normalização segura, renderização de explicabilidade, histórico e replay explícito.
- `static/style.css`: estilos de explicabilidade, cards bloqueados, chips, auditoria e histórico.
- `teste_frontend_explicabilidade.py`: testes estáticos de contrato visual.
- `teste_frontend_replay.py`: testes estáticos do fluxo de histórico/replay.

## 10. Testes

Executar:

```bash
python -m compileall -q api decisao banco config
pytest teste_api_decisoes.py teste_frontend_replay.py teste_replay_decisao.py
```

## 11. Checklist de homologação

```text
[ ] Não alterou motor.
[ ] Não alterou payload da API.
[ ] Não recalcula hash no frontend.
[ ] Renderiza campos ausentes com fallback.
[ ] Cards bloqueados continuam visíveis.
[ ] gates_detalhes é exibível.
[ ] Fontes, motivos, métricas e penalidades aparecem quando disponíveis.
[ ] Hash/payload auditável é apenas exibido.
[ ] Histórico consulta decisões salvas sem replay por padrão.
[ ] Replay só é executado por ação explícita.
[ ] UI tolera ausência de replay.
[ ] Endpoints preservam autenticação.
```