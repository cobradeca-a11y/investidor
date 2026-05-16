# FIIA — PIPELINE DE AUDITORIA E EVOLUÇÃO PARA NÍVEL INSTITUCIONAL

Documento registrado no projeto Investidor/FIIA a partir da auditoria consolidada fornecida pelo usuário.

## CONTEXTO
Sistema de análise de FIIs brasileiros com arquitetura de 8 gates eliminatórios, CVM-first patrimonial, confiança por fonte/campo, FNET documental, aprendizado operacional 90/365d e motor de decisão auditável.

Stack: Python, FastAPI, SQLite, BeautifulSoup, APScheduler. Fontes: CVM Dados Abertos, BCB SGS, Fundamentus (fallback), FNET.

## MISSÃO
Identificar o que impede este sistema de operar como consultor autônomo institucional de altíssimo desempenho e gerar plano de execução preciso.

## BLOCO 5 — PLANO DE EVOLUÇÃO

### Prioridade 1 — Fecha gaps que invalidam o sistema
1. Agendar coleta CVM automaticamente — informes mensais, trimestrais e diários.
2. Reescrever `maquina_tempo.py` com motor real e CDI histórico.
3. Gordon com crescimento `g` por segmento.
4. Inverter `autoupdater` para notificar sem atualizar automaticamente.

### Prioridade 2 — Eleva qualidade analítica
5. Dividendos via FNET avisos aos cotistas como fonte primária.
6. Versionamento de reapresentações CVM.
7. Score fundamentalista com DRE/balanço CVM.
8. Pesos segmentados por tipo de fundo.
9. Spread médio filtrado para 30 dias.
10. Calibração IA com correlação score/retorno.

### Prioridade 3 — Completa o produto
11. Preço com timestamp rastreável via yfinance.
12. `dimensionamento.py` com valor de carteira real.
13. `explicador.py` integrado ao endpoint de relatório.
14. NLP real sobre PDFs FNET com Gemini.
15. `confiabilidade.py` com teto para preço desatualizado > 2 dias.

## O que NÃO fazer
- Não migrar tudo para CVM de uma vez — migrar campo a campo com fallback validado.
- Não aplicar pesos calibrados por IA antes de ter 50+ amostras por segmento.
- Não remover Fundamentus enquanto campos sem substituto CVM ainda existirem.
- Não usar score IA como critério eliminatório até calibração histórica comprovada.

## Observação operacional
Este documento é o registro-base de execução dos gaps por prioridade. O conteúdo completo da auditoria permanece no arquivo de origem enviado pelo usuário e este registro consolida a fila operacional dentro do repositório.