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
- replay quando informado.

## 2. Contrato de frontend

O frontend pode normalizar dados para exibição, mas não pode alterar o payload original recebido da API.

O frontend não pode:

- recalcular hash;
- recalcular decisão;
- alterar gates;
- aplicar regras de motor;
- esconder cards bloqueados;
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
- `permitir_decisao` não vier informado.

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

## 7. Arquivos envolvidos

- `static/app.js`: normalização segura e renderização de explicabilidade.
- `static/style.css`: estilos de explicabilidade, cards bloqueados, chips e auditoria.
- `teste_frontend_explicabilidade.py`: testes estáticos de contrato visual.

## 8. Testes

Executar:

```bash
python -m compileall -q api decisao processamento coleta
pytest teste_contrato_decisao.py teste_frontend_explicabilidade.py
```

## 9. Checklist de homologação

```text
[ ] Não alterou motor.
[ ] Não alterou payload da API.
[ ] Não recalcula hash no frontend.
[ ] Renderiza campos ausentes com fallback.
[ ] Cards bloqueados continuam visíveis.
[ ] gates_detalhes é exibível.
[ ] Fontes, motivos, métricas e penalidades aparecem quando disponíveis.
[ ] Hash/payload auditável é apenas exibido.
```
