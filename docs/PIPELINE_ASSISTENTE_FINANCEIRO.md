# FIIA — Pipeline até Assistente Financeiro Diário

Este pipeline organiza os blocos que faltavam para o app deixar de ser apenas tecnicamente correto e virar auxiliar financeiro de rotina.

## Bloco 1 — Dados oficiais e cobertura

Objetivo: reduzir decisões com dados ausentes.

Comandos:

```bash
python main.py --setup
python -c "from coleta.tabela_mestre_fiis import importar_csv; print(importar_csv('tabela_mestre_fiia_fiis_b3_cvm.csv'))"
python -c "from coleta.cvm_informe_mensal import coletar_ano; print(coletar_ano(2026))"
python -c "from servicos.cvm_fii_service import calcular_pvp_cvm; print(calcular_pvp_cvm('HGLG11'))"
```

Critério de aceite:

- Tabela mestre importa 513 tickers.
- `calcular_pvp_cvm("HGLG11")` retorna `status: OK`.
- Radar mostra `patrimonial=CVM_INF_MENSAL` quando houver dado oficial.

## Bloco 2 — Vacância real e FNET

Objetivo: enriquecer a leitura operacional.

Comandos:

```bash
pytest teste_cvm_fnet_documentos.py teste_relatorio_fnet.py teste_analise_qualitativa_cache.py
```

Critério de aceite:

- FNET falha de forma controlada quando o documento não é PDF válido.
- IA usa fallback de notícias sem quebrar o radar.
- Vacância trimestral CVM é usada como fallback quando Fundamentus vem vazio/zero.

## Bloco 3 — Loop financeiro diário

Objetivo: transformar vereditos em ações acompanháveis.

Comandos:

```bash
pytest teste_assistente_financeiro.py teste_api_assistente.py
```

Critério de aceite:

- Alertas indicam zona de entrada, dividendo ausente e vacância trimestral ausente.
- Agendador persiste alertas diariamente para a PWA.
- `/api/assistente/alertas/novos` consulta alertas persistidos sem gerar novos registros.
- Evolução mostra se o fundo melhorou, piorou ou ficou estável.
- Rebalanceamento usa a política de carteira existente.
- Exportação offline em texto e PDF funciona por endpoint autenticado.

## Bloco 4 — PWA

Objetivo: deixar os dados acionáveis na interface.

Comandos:

```bash
pytest teste_frontend_payload.py teste_frontend_explicabilidade.py teste_frontend_replay.py
```

Critério de aceite:

- Cards têm ações de detalhe/evolução por fundo.
- Painel "Assistente Diário" carrega alertas e rebalanceamento.
- Badge/toast usa `/alertas/novos` para polling sem persistir alertas.
- Exportação de texto e PDF fica acessível pela tela de detalhe.
- A PWA continua sem recalcular hash/payload auditável.

## Bloco 5 — Smoke local

Objetivo: validar o app rodando.

Comando:

```bash
uvicorn app:app --host 127.0.0.1 --port 8080 --reload
```

Validar no navegador:

- `/web/index.html` abre.
- `Minha Carteira` retorna 200 com API key configurada.
- `Radar FIIA` inicia job assíncrono.
- `Histórico e Replay` consulta sem executar replay por padrão.
- `Assistente Diário` mostra alertas/rebalanceamento.

## Bloco 6 — Gate antes de push

```bash
python -m compileall -q acesso api aprendizado backtest banco cadastro carteira coleta config decisao educacao mercado operacional processamento relatorios servicos sistema validacao app.py main.py
pytest teste_assistente_financeiro.py teste_api_assistente.py teste_frontend_payload.py teste_cvm_fnet_documentos.py teste_relatorio_fnet.py teste_analise_qualitativa_cache.py teste_api_radar_jobs.py
git status
```

Critério de aceite:

- Compile sem saída.
- Testes verdes.
- `git status` mostra apenas arquivos intencionais antes do commit.
