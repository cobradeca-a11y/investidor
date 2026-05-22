# FIIA - Roadmap Bloqueante do Sistema de Decisao e Aprendizado

Este roadmap registra o estado funcional do app, os gaps conhecidos e um pipeline
de execucao por prioridades. A regra operacional e simples: uma fase so comeca
quando a anterior cumprir seus criterios de aceite.

O objetivo final e transformar o FIIA de radar operacional em sistema de decisao
financeira auditavel, com dados confiaveis, maquina do tempo, aprendizado
supervisionado e UX diaria utilizavel.

## 1. Principio de Execucao

1. Nao avancar fase com pendencia critica aberta.
2. Nao usar dado atual como se fosse dado historico.
3. Nao aplicar ajuste de peso automaticamente.
4. Toda decisao relevante deve ter payload, motivo, fonte e validade.
5. Toda melhoria de regra deve ser comparada contra baseline anterior.
6. Toda etapa deve ter teste automatizado ou smoke test documentado.

## 2. Estado Atual Resumido

### Funciona de forma operacional

- Setup do banco via `python main.py --setup`.
- Importacao da tabela mestre ticker -> CNPJ.
- Coleta de informe mensal CVM.
- Calculo de P/VP CVM para ativos cobertos.
- Radar principal.
- Radar assincrono via API/PWA.
- Carteira basica.
- Historico de decisoes.
- Replay auditavel sem scraping.
- Healthcheck basico e profundo.
- API key para endpoints sensiveis.
- Alertas basicos do assistente.
- Exportacao texto/PDF do detalhe.
- Backtest institucional com snapshot quando ha snapshot historico.
- CLI de maquina do tempo:
  - `python main.py --backtest TICKER --data AAAA-MM-DD --horizonte 365`
  - `python main.py --backtest-radar --data AAAA-MM-DD --top 5 --horizonte 365`

### Funciona parcialmente

- FNET documental e leitura de PDFs.
- Vacancia real por imovel.
- Dividendos oficiais via FNET.
- IA qualitativa dependente de texto/documentos disponiveis.
- Rebalanceamento de carteira.
- Aprendizado operacional conectado a backtest.
- Maquina do tempo para periodos antigos sem snapshots.
- UX de alertas e historico.

### Ainda nao funciona de forma completa

- Backtest reconstrutivo desde 2020.
- Ranking historico top 5 com dados reconstruidos de cada data.
- Aprendizado automatico supervisionado a partir do Radar Temporal.
- Comparacao A/B de parametros do motor.
- Sugestao de ajuste baseada em evidencia historica ampla.
- Tela dedicada de Maquina do Tempo na PWA.

## 3. Pipeline Bloqueante

## Fase 0 - Linha de Base e Higiene Operacional

Objetivo: garantir que a base local esta integra antes de mexer no motor.

### Gaps

- Pode haver diferenca entre banco local e schema atual.
- Historico pode conter decisoes duplicadas de varios radares.
- Ambiente pode estar sem `.env`, `GEMINI_API_KEY` ou `FIIA_API_KEY`.

### Correcoes

- Rodar setup e migracoes.
- Validar tabela mestre e CVM mensal.
- Confirmar que API key funciona na PWA.
- Registrar status local em checklist.

### Comandos

```bash
git pull
python main.py --setup
python -c "from coleta.tabela_mestre_fiis import importar_csv; print(importar_csv('tabela_mestre_fiia_fiis_b3_cvm.csv'))"
python -c "from coleta.cvm_informe_mensal import coletar_ano; print(coletar_ano(2026))"
python -c "from servicos.cvm_fii_service import calcular_pvp_cvm; print(calcular_pvp_cvm('HGLG11'))"
pytest teste_healthcheck.py teste_seguranca_api.py teste_backtest_snapshot.py
```

### Criterios de aceite

- `calcular_pvp_cvm("HGLG11")` retorna `status: OK`.
- Testes acima passam.
- PWA responde com carteira e API key configurada.

### Bloqueia

- Todas as fases seguintes.

## Fase 1 - Cobertura de Dados Prioritarios

Objetivo: reduzir decisoes bloqueadas por falta de dados essenciais.

### Gaps

1. FNET pode retornar PDF invalido, HTML, erro ou documento vazio.
2. Alguns CNPJs nao resolvem corretamente para FNET.
3. Relatorio gerencial pode nao ser localizado por ticker.
4. Dividendos oficiais do mes corrente ainda podem ficar ausentes.
5. Vacancia trimestral CVM aparece ausente para muitos fundos.

### Correcoes

- Separar claramente tipos de retorno FNET:
  - PDF valido;
  - HTML/erro;
  - JSON;
  - vazio;
  - timeout.
- Persistir status documental por ticker/CNPJ.
- Melhorar resolucao ticker -> CNPJ para fundos com classe/fundo diferentes.
- Completar importador de informes trimestrais CVM.
- Persistir vacancia consolidada e por imovel.
- Usar FNET avisos aos cotistas para dividendos oficiais quando disponivel.
- Manter Yahoo como fallback, nunca como fonte preferencial quando FNET oficial existir.

### Entregaveis

- Relatorio de cobertura FNET por ticker.
- Relatorio de cobertura de vacancia trimestral.
- Relatorio de dividendos oficiais vs fallback.
- Reducao dos alertas `VACANCIA_TRIMESTRAL_AUSENTE`.

### Testes

```bash
pytest teste_cvm_fnet_documentos.py teste_relatorio_fnet.py teste_analise_qualitativa_cache.py
pytest teste_score_fontes.py teste_governanca_fontes.py
```

### Criterios de aceite

- HGLG11, KNRI11, XPML11, HGRU11, BTLG11 com CNPJ resolvido.
- FNET nao quebra ao receber arquivo nao PDF.
- Documento invalido vira status controlado, nao traceback.
- Vacancia trimestral deixa de ser ausente para amostra minima de fundos de tijolo.
- Dividendos recentes aparecem para amostra minima de fundos liquidos.

### Bloqueia

- Maquina do Tempo reconstrutiva.
- IA qualitativa mais confiavel.
- Aprendizado historico.

## Fase 2 - Radar Diario e UX de Uso Real

Objetivo: tornar o uso diario legivel e acionavel.

### Gaps

1. Alertas de cobertura podem soterrar oportunidades reais.
2. Historico mostra decisoes repetidas.
3. Card principal mistura auditoria tecnica com decisao operacional.
4. Rebalanceamento ainda nao esta maduro.
5. Tela de detalhe por fundo ainda e limitada.

### Correcoes

- Agrupar alertas em:
  - `OPORTUNIDADE`;
  - `RISCO_ACAO`;
  - `COBERTURA_DADOS`.
- Mostrar oportunidades primeiro.
- Consolidar `VACANCIA_TRIMESTRAL_AUSENTE` em resumo.
- Deduplicar historico por execucao de radar ou mostrar ultima decisao por ticker.
- Criar detalhe do fundo com abas:
  - decisao;
  - dados;
  - riscos;
  - documentos;
  - historico;
  - maquina do tempo.
- Rebalanceamento deve comparar:
  - peso atual;
  - peso sugerido;
  - decisao atual;
  - limite por ativo;
  - caixa disponivel.

### Testes

```bash
pytest teste_frontend_payload.py teste_frontend_explicabilidade.py teste_frontend_replay.py
pytest teste_assistente_financeiro.py teste_api_assistente.py
```

### Smoke test

```bash
uvicorn app:app --host 127.0.0.1 --port 8080 --reload
```

Validar na PWA:

- Carteira carrega.
- Radar inicia por job assincrono.
- Alertas novos aparecem sem chamar endpoint gerador.
- Historico nao fica inutilmente repetitivo.
- Detalhe por fundo abre.

### Criterios de aceite

- Usuario identifica top oportunidades em ate 30 segundos.
- Alertas de dados incompletos nao ocultam alertas de compra/risco.
- Historico mostra decisao recente sem duplicacao excessiva.
- Nenhum endpoint de polling gera novos alertas por efeito colateral.

### Bloqueia

- Uso 24/7 util.
- Validacao diaria consistente.

## Fase 3 - Maquina do Tempo Institucional

Objetivo: validar decisoes futuras a partir de snapshots reais, sem olhar o futuro.

### Estado atual

- `backtest/maquina_tempo.py` existe.
- Backtest por ticker existe.
- Backtest-radar top N existe.
- O sistema invalida corretamente datas sem snapshot.

### Gaps

1. Datas antigas, como 2020-2022, nao funcionam se nao houver snapshot salvo.
2. Nao ha tela PWA para Maquina do Tempo.
3. O resultado ainda nao alimenta automaticamente o modulo de aprendizado.

### Correcoes

- Garantir criacao diaria de snapshots antes do radar.
- Criar endpoint:
  - `POST /api/backtest/radar-temporal`.
- Criar tela PWA:
  - data base;
  - top N;
  - horizonte;
  - resultado;
  - validade institucional.
- Persistir resultados de backtest institucional.

### Testes

```bash
pytest teste_backtest_snapshot.py
```

### Criterios de aceite

- Quando ha snapshot, ranking top 5 e avaliado.
- Quando nao ha snapshot, resultado e invalido de forma explicita.
- Nenhum teste usa preco atual como historico.
- Resultado mostra:
  - decisao;
  - preco entrada;
  - preco saida;
  - dividendos;
  - CDI;
  - acerto/erro;
  - motivo.

### Bloqueia

- Aprendizado institucional futuro.

## Fase 4 - Backtest Reconstrutivo Historico Desde 2020

Objetivo: permitir simulacao de 2020, 2021, 2022, 2023 e 2024 mesmo sem snapshots reais.

### Premissa

Este modo nao deve ser chamado de institucional. Ele deve ser marcado como:

```text
validade_historica = PARCIAL_RECONSTRUTIVA
```

### Gaps

1. Fundamentus historico pode nao estar disponivel dia a dia.
2. CVM pode ter reapresentacoes.
3. FNET pode nao oferecer documento exatamente como estava no dia.
4. Yahoo pode ter ajustes retroativos.
5. Dividendos precisam respeitar data conhecida na epoca.

### Correcoes

- Criar `backtest/reconstrutor_historico.py`.
- Reconstruir por data:
  - preco historico;
  - dividendos conhecidos ate T0;
  - CDI/SELIC/IPCA ate T0;
  - CVM mensal disponivel ate T0;
  - FNET documentos entregues ate T0;
  - liquidez historica estimada.
- Registrar nivel de confianca por campo reconstruido.
- Bloquear ou reduzir peso de campo com validade fraca.

### Entregaveis

- `python main.py --backtest-radar-reconstrutivo --data 2022-05-20 --top 5 --horizonte 365`
- Relatorio por campo:
  - fonte;
  - validade;
  - defasagem;
  - risco de revisao.

### Criterios de aceite

- Resultado nunca se apresenta como snapshot real.
- Todo campo reconstruido possui fonte e validade.
- O ranking de 2022 e gerado com aviso de validade parcial.
- Testes provam que documentos posteriores a T0 nao entram na decisao.

### Bloqueia

- Aprendizado historico desde 2020.

## Fase 5 - Aprendizado Operacional Supervisionado

Objetivo: transformar resultados historicos em sugestoes de ajuste.

### Estado atual

Existem:

- `aprendizado/resultados.py`;
- `aprendizado/tentativa_erro.py`;
- `aprendizado/ajustes_pesos.py`;
- `aprendizado/pesos_fnet.py`;
- endpoints `/api/aprendizado/...`.

### Gaps

1. Backtest temporal ainda nao alimenta automaticamente resultados operacionais.
2. Sugestoes ainda nao comparam baseline contra parametros alternativos.
3. Nao ha diagnostico cirurgico por causa de erro.

### Correcoes

- Conectar `executar_backtest_radar` a `aprendizado.resultados`.
- Classificar erros:
  - falso positivo;
  - falso negativo;
  - bloqueio excessivo;
  - compra ruim por P/VP;
  - perda por falta de FNET;
  - excesso de conservadorismo em premio CDI;
  - historico minimo restritivo;
  - penalidade indevida por vacancia ausente.
- Criar comparador A/B de parametros:
  - baseline atual;
  - alternativa;
  - impacto em acerto;
  - impacto em drawdown;
  - impacto em quantidade de oportunidades.
- Gerar sugestao pendente, nunca aplicar automaticamente.

### Exemplos de parametros a testar

- `HISTORICO_MINIMO_MESES = 24` vs `18`.
- `PREMIO_CDI_MINIMO = 1.5` vs `1.0`.
- Peso de P/VP por segmento.
- Penalidade de FNET ausente.
- Penalidade de vacancia ausente.
- Corte de liquidez.
- Peso da IA qualitativa.

### Criterios de aceite

- Cada sugestao tem:
  - evidencia;
  - amostra;
  - periodo;
  - impacto estimado;
  - risco;
  - status `PENDENTE`.
- Aprovar sugestao nao altera motor automaticamente.
- Rejeitar sugestao registra motivo humano.
- O sistema compara baseline vs alternativa antes de sugerir.

### Testes

```bash
pytest teste_aprendizado_operacional.py teste_aprovacao_ajustes.py
```

## Fase 6 - Governanca de Versoes do Motor

Objetivo: permitir evolucao controlada do algoritmo.

### Gaps

1. Parametros podem mudar sem comparacao formal.
2. Nao ha versao explicita de conjunto de parametros para backtest A/B.
3. Relatorio ainda nao mostra claramente diferenca entre versoes.

### Correcoes

- Criar versao de parametros:
  - `motor_base_v2_1`;
  - `motor_teste_historico_18m_cdi_1_0`;
  - etc.
- Persistir versao usada em cada decisao/backtest.
- Comparar:
  - taxa de acerto;
  - falsos positivos;
  - falsos negativos;
  - retorno medio;
  - retorno vs CDI;
  - max drawdown, quando disponivel;
  - quantidade de oportunidades.

### Criterios de aceite

- Nenhum ajuste entra sem versao.
- Toda decisao sabe qual versao do motor/parametros usou.
- Toda sugestao aponta a versao baseline e a versao alternativa.

## Fase 7 - Uso 24/7 e Deploy Local/Hospedado

Objetivo: manter o sistema rodando com seguranca operacional.

### Gaps

1. SQLite local exige cuidado com backup.
2. Chaves `.env` nao podem ir ao repo.
3. Scraping e fontes externas podem falhar.
4. Rodar 24/7 no PC depende de energia, rede e Windows.

### Correcoes

- Definir modo local 24/7:
  - Windows Task Scheduler;
  - backup diario de `fiia.db`;
  - logs rotacionados;
  - healthcheck periodico.
- Definir modo hospedado:
  - VPS;
  - volume persistente;
  - secrets;
  - HTTPS;
  - autenticacao;
  - backup externo.

### Criterios de aceite

- API sobe apos reboot.
- Banco tem backup.
- Healthcheck alerta falha.
- `.env` nao versionado.
- PWA acessivel de forma controlada.

## 4. Ordem Final de Execucao

```text
Fase 0 - Linha de base
Fase 1 - Cobertura de dados
Fase 2 - UX diaria e radar usavel
Fase 3 - Maquina do Tempo institucional
Fase 4 - Backtest reconstrutivo 2020+
Fase 5 - Aprendizado supervisionado
Fase 6 - Versoes do motor e A/B
Fase 7 - 24/7 e deploy
```

## 5. Definicao de Pronto do App

O app pode ser considerado pronto para uso diario quando:

- radar diario gera oportunidades e bloqueios explicaveis;
- carteira mostra decisao e risco por ativo;
- alertas priorizam oportunidade e risco, nao apenas falta de dado;
- dados CVM/FNET/dividendos tem cobertura rastreavel;
- historico e replay funcionam;
- maquina do tempo valida decisoes futuras por snapshot;
- backtest reconstrutivo permite estudar 2020+ com validade parcial;
- aprendizado gera sugestoes auditaveis, nao automaticas;
- parametros so mudam via versao e comparacao;
- backup e rotina 24/7 estao definidos.

## 6. Proxima Tarefa Recomendada

Comecar pela Fase 1.

Primeiro item concreto:

```text
Robustecer FNET documental e cobertura de vacancia trimestral.
```

Motivo: sem dados documentais e vacancia confiavel, o radar temporal e o
aprendizado vao calibrar em cima de lacunas de dados, nao de desempenho real.
