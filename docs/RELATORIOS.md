# FIIA — Relatórios Auditáveis

Este documento descreve a camada de relatórios técnicos auditáveis do FIIA.

## 1. Objetivo

Gerar relatórios técnicos exportáveis de:

- carteira;
- decisões;
- histórico;
- bloqueios;
- fontes;
- métricas;
- gates;
- replay/auditoria.

A geração e exportação de relatório é somente leitura.

## 2. Contratos obrigatórios

Relatórios e exportações auditáveis não podem:

- alterar decisão;
- chamar motor decisório;
- acionar scraping;
- alterar banco;
- recalcular decisão;
- exportar segredos;
- quebrar replay/auditoria existente.

Todo relatório deve indicar:

- data de geração;
- versão do relatório;
- versão do motor quando disponível;
- versão do contexto quando disponível;
- hash do payload quando disponível;
- se houve replay;
- se houve divergência no replay quando disponível.

Dados ausentes devem aparecer como:

```text
não disponível
```

## 3. Arquivos principais

```text
relatorios/relatorios_auditaveis.py
relatorios/relatorio_completo.py
relatorios/exportacao_relatorios.py
teste_relatorios_auditaveis.py
teste_exportacao_relatorios.py
docs/RELATORIOS.md
```

## 4. Relatório de decisões auditáveis

Função:

```python
gerar_relatorio_decisoes_auditaveis(limite=50, incluir_replay=False)
```

Características:

- lista decisões persistidas;
- valida hash salvo;
- inclui contexto e versão do motor;
- extrai bloqueios;
- extrai fontes;
- extrai gates;
- gera bloco de replay.

Por padrão:

```python
incluir_replay=False
```

Replay precisa ser solicitado explicitamente:

```python
gerar_relatorio_decisoes_auditaveis(incluir_replay=True)
```

## 5. Relatório de carteira auditável

Função:

```python
gerar_relatorio_carteira_auditavel()
```

Características:

- consulta `carteira_posicoes` localmente;
- não chama motor;
- não aciona coleta;
- trata ausência de tabela/dados como lista vazia;
- exporta posição, quantidade, preço médio, custo total, segmento e data de atualização.

## 6. Relatório completo auditável

Função:

```python
gerar_relatorio_auditavel_completo(limite=50, incluir_replay=False)
```

Inclui:

- bloco de carteira;
- bloco de decisões;
- flags de segurança:
  - `sem_scraping=True`;
  - `executou_motor=False`;
  - `alterou_decisao=False`.

## 7. Exportação Markdown

Função:

```python
gerar_markdown_relatorio_auditavel(relatorio)
```

Exporta:

- cabeçalho técnico;
- decisões em tabela;
- bloqueios/falhas;
- replay.

## 8. Exportação CSV/JSON

Arquivo:

```text
relatorios/exportacao_relatorios.py
```

Funções:

```python
gerar_exportacao_json(secao="decisoes", limite=50, incluir_replay=False)
gerar_exportacao_csv(secao="decisoes", limite=50, incluir_replay=False)
gerar_exportacao(formato="json", secao="decisoes", limite=50, incluir_replay=False)
```

Seções exportáveis:

```text
decisoes
fontes
bloqueios
replay
metricas
```

Formatos suportados:

```text
json
csv
```

Campos estáveis por seção:

- `decisoes`: `id`, `ticker`, `data_decisao`, `decisao`, `motivo`, `confianca`, `risco`, `score_final`, `contexto_versao`, `versao_motor`, `payload_hash`, `hash_valido`.
- `fontes`: `ticker`, `fonte_patrimonial`, `nivel_uso_dados`, `score_confianca_dados`, `contexto_versao`, `versao_motor`, `payload_hash`.
- `bloqueios`: `ticker`, `tipo`, `decisao`, `gate_parada`, `motivo`.
- `replay`: `decisao_id`, `ticker`, `solicitado`, `executado`, `status`, `replay_deterministico`, `divergencia_replay`, `payload_hash_salvo`, `payload_hash_replay`, `fonte_replay`.
- `metricas`: `quantidade_decisoes`, `quantidade_bloqueios`, `quantidade_fontes`, `quantidade_gates`, `quantidade_replays`, `quantidade_posicoes`, `sem_scraping`, `executou_motor`, `alterou_decisao`.

A exportação remove chaves sensíveis como `api_key`, `token`, `secret`, `authorization`, `cookie`, `senha` e equivalentes.

## 9. Endpoints de exportação

Todos os endpoints de relatório em `api/relatorios.py` exigem autenticação por API key.

Endpoint de exportação:

```text
GET /api/relatorios/exportar?formato=json&secao=decisoes&limite=50&incluir_replay=false
GET /api/relatorios/exportar?formato=csv&secao=decisoes&limite=50&incluir_replay=false
```

Regras:

- JSON retorna payload estruturado.
- CSV retorna `Response` com `Content-Disposition: attachment`.
- Replay só é incluído quando `incluir_replay=true`.
- A exportação não aciona motor nem scraping.
- A exportação não altera dados.

## 10. Compatibilidade com API existente

O arquivo `relatorios/relatorio_completo.py` mantém compatibilidade com `api/relatorios.py`, expondo:

```python
gerar_relatorio_completo()
gerar_markdown_relatorio()
gerar_analise_individual()
comparar_ativos()
```

Essas funções agora usam a camada auditável e não chamam motor ou scraping.

## 11. Testes

Executar:

```bash
python -m compileall -q relatorios api decisao banco config
pytest teste_exportacao_relatorios.py teste_seguranca_api.py
```

Para a camada auditável base:

```bash
pytest teste_relatorios_auditaveis.py teste_replay_decisao.py
```

## 12. Checklist de homologação

```text
[ ] Relatório não altera decisão.
[ ] Relatório não aciona scraping.
[ ] Relatório não chama motor.
[ ] Exportação não altera dados.
[ ] Exportação usa campos estáveis.
[ ] Exportação JSON funciona.
[ ] Exportação CSV funciona.
[ ] Endpoints exigem autenticação.
[ ] Dados sensíveis não são exportados.
[ ] Relatório indica data de geração.
[ ] Relatório indica versão do motor quando disponível.
[ ] Relatório indica versão do contexto quando disponível.
[ ] Relatório indica hash quando disponível.
[ ] Dados ausentes viram “não disponível”.
[ ] Replay/auditoria existente permanece preservado.
[ ] Markdown exportável é gerado.
```