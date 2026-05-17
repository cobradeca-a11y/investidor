# RELATÓRIO ESTRUTURAL — FIIA / INVESTIDOR

Data de consolidação: Maio/2026
Status do projeto: MVP Robusto em transição para Pipeline Institucional Automatizado

---

# 1. VISÃO GERAL

O projeto FIIA (Fundo Inteligente de Investimento em Ativos) evoluiu de um MVP de análise de FIIs para uma arquitetura de motor autônomo de análise quantitativa e qualitativa.

O sistema já possui:

* motor de decisão;
* gate macroeconômico;
* score segmentado;
* margem de segurança;
* scheduler automático;
* persistência SQLite;
* snapshots históricos;
* paper trading;
* tentativa e erro;
* auditoria operacional;
* integração macro oficial BCB;
* integração parcial CVM/FNET.

O foco atual deixou de ser construção de lógica básica e passou a ser:

* consolidação institucional das fontes;
* ingestão automatizada oficial;
* rastreabilidade;
* replay histórico;
* calibração operacional.

---

# 2. ESTADO OPERACIONAL ATUAL

## 2.1 Banco de dados

Banco SQLite operacional.

Estado validado:

* schema consistente;
* migrações P2/P3 aplicadas;
* persistência íntegra;
* inserts funcionando;
* snapshots funcionando;
* paper trading funcionando;
* macro persistindo corretamente.

Tabela macro validada:

* SELIC;
* CDI;
* IPCA;
* timestamps.

---

## 2.2 Gate Macro

Problema estrutural resolvido.

Antes:

* SELIC/CDI estavam sendo interpretados como taxas diárias;
* semáforo macro nunca fechava gate;
* decisões eram enviesadas para COMPRAR.

Correção aplicada:

* troca para séries SGS anualizadas oficiais;
* SELIC → série 1178;
* CDI → série 4389;
* IPCA → série 433.

Resultado:

* Gate Macro operacional;
* spread DY vs CDI funcional;
* semáforo macro coerente.

---

## 2.3 Paper Trading

Funcionando.

Teste validado:

* ativos processados = simulacoes registradas;
* erros = 0.

O sistema já:

* simula decisões;
* grava resultados;
* registra aprendizado;
* mantém histórico operacional.

---

## 2.4 Snapshots

Funcionando.

O sistema já:

* cria snapshots diários;
* grava estado dos ativos;
* prepara replay histórico futuro.

Limitação atual:

* snapshots ainda não são utilizados plenamente pela máquina do tempo.

---

## 2.5 Scheduler

Scheduler operacional.

Rotinas integradas:

* coleta CVM diária;
* coleta trimestral;
* snapshots;
* paper trading;
* radar;
* saúde das fontes;
* avaliador temporal.

---

# 3. FONTES DE DADOS

## 3.1 Banco Central / SGS

Estado:

OPERACIONAL.

Função:

* macroeconomia oficial;
* SELIC;
* CDI;
* IPCA.

Séries utilizadas:

| Indicador        | Série SGS |
| ---------------- | --------- |
| SELIC anualizada | 1178      |
| CDI anualizado   | 4389      |
| IPCA             | 433       |

Uso no sistema:

* Gate Macro;
* spread DY vs CDI;
* cenário macroeconômico;
* filtros hostis.

---

## 3.2 CVM / CKAN

Estado:

PARCIALMENTE IMPLEMENTADO.

Datasets mapeados:

| Dataset        | Objetivo                  |
| -------------- | ------------------------- |
| DFIN           | demonstrações financeiras |
| INF_MENSAL     | patrimônio, VPA, cotistas |
| INF_TRIMESTRAL | inadimplência, composição |
| INF_ANUAL      | estrutura e governança    |

URLs mapeadas:

* [https://dados.cvm.gov.br/dados/FII/DOC/DFIN/DADOS/](https://dados.cvm.gov.br/dados/FII/DOC/DFIN/DADOS/)
* [https://dados.cvm.gov.br/dados/FII/DOC/INF_ANUAL/DADOS/](https://dados.cvm.gov.br/dados/FII/DOC/INF_ANUAL/DADOS/)
* [https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/](https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/)
* [https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/](https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/)

Função no sistema:

* substituir fallback patrimonial;
* gerar P/VP oficial;
* alimentar score institucional;
* alimentar análise contábil.

Limitação atual:

* vínculo ticker ↔ CNPJ ainda não consolidado.

---

## 3.3 FNET / Fundos.NET

Estado:

ESTRUTURA EXISTE, MAS SEM POVOAMENTO.

Tabelas existentes:

* fnet_dividendos_fii;
* fnet_nlp_classificacoes;
* cvm_fnet_documentos_fii.

Problema atual:

* tabela cvm_fnet_documentos_fii está vazia.

Consequência:

* radar retorna SEM_FNET.

Objetivo:

* importar documentos;
* indexar IDs;
* vincular documentos aos ativos;
* alimentar NLP.

Campos já preparados:

* ticker;
* cnpj_fundo;
* categoria;
* tipo_documento;
* url_documento;
* protocolo;
* assunto;
* payload_json.

---

## 3.4 Yahoo Finance / yfinance

Estado:

OPERACIONAL.

Função:

* preço;
* liquidez;
* histórico;
* timestamps.

Uso:

* preço atual;
* paper trading;
* snapshots;
* auditoria temporal.

Limitação:

* não é fonte contábil oficial.

---

## 3.5 Gemini

Estado:

ESTRUTURA PRONTA.

Função:

* leitura de PDFs;
* classificação qualitativa;
* risco documental;
* interpretação de fatos relevantes.

Problema atual:

* IA_INDISPONIVEL sem chave ativa.

---

# 4. MÓDULOS IMPLEMENTADOS

## Implementados e funcionais

* estrategia.py;
* margem_seguranca.py;
* score_segmentado.py;
* confiabilidade.py;
* maquina_tempo.py;
* snapshots.py;
* paper_trading.py;
* saude_fontes.py;
* api_bcb.py;
* cvm_informe_mensal.py;
* informe_trimestral.py;
* nlp_fnet.py;
* persistencia_decisao.py;
* autoupdater.py.

---

# 5. GAPS ATUAIS

## 5.1 Vínculo estrutural ticker ↔ CNPJ

Maior gap atual.

Necário consolidar:

* ticker B3;
* CNPJ fundo;
* CNPJ classe;
* CVM;
* FNET.

Sem isso:

* CVM e FNET não se encaixam automaticamente.

---

## 5.2 FNET operacional

Necessário:

* coletor incremental;
* indexador documental;
* download automático;
* parser;
* persistência.

---

## 5.3 Replay histórico verdadeiro

Hoje:

* snapshots existem;
* máquina do tempo ainda usa banco atual.

Falta:

* replay temporal real;
* prevenção total de look-ahead bias.

---

## 5.4 NLP documental real

Estrutura existe.

Falta:

* PDFs reais;
* classificação operacional;
* vínculo com score.

---

## 5.5 Dados patrimoniais oficiais completos

Hoje ainda existem casos de:

* fallback patrimonial;
* ausência de timestamp;
* ausência de validação CVM.

---

# 6. INPUTS AINDA NECESSÁRIOS DO USUÁRIO

## Estruturais

* lista oficial de FIIs-alvo;
* política de fallback;
* estratégia operacional.

## Operacionais

* chave Gemini;
* valor de carteira;
* perfil de risco;
* política de entradas.

## Institucionais

* fonte definitiva ticker ↔ CNPJ;
* priorização de cobertura.

---

# 7. ARQUITETURA FINAL PRETENDIDA

O projeto está caminhando para:

* pipeline institucional automatizado;
* ingestão oficial CVM/FNET;
* motor quantitativo;
* camada qualitativa IA;
* replay histórico;
* aprendizado adaptativo;
* rastreabilidade;
* auditoria completa.

Arquitetura-alvo:

| Camada      | Fonte                     |
| ----------- | ------------------------- |
| Macro       | BCB/SGS                   |
| Contábil    | CVM                       |
| Eventos     | FNET                      |
| Mercado     | Yahoo Finance             |
| IA          | Gemini                    |
| Aprendizado | snapshots + paper trading |

---

# 8. FASE ATUAL DO PROJETO

Classificação atual:

```txt
MVP ROBUSTO FUNCIONAL
EM TRANSIÇÃO PARA PIPELINE INSTITUCIONAL
```

O sistema já:

* decide;
* aprende;
* registra;
* simula;
* agenda;
* persiste;
* audita.

O foco agora é:

```txt
ALIMENTAÇÃO OFICIAL E CONSOLIDAÇÃO INSTITUCIONAL
```

---

# 9. PRIORIDADE OPERACIONAL IMEDIATA

Ordem recomendada:

1. ticker ↔ CNPJ;
2. ingestão CVM mensal;
3. ingestão FNET;
4. NLP documental;
5. replay histórico;
6. calibração quantitativa.

---

# 10. ESTADO FINAL RESUMIDO

| Área                   | Estado           |
| ---------------------- | ---------------- |
| Banco                  | ESTÁVEL          |
| Macro                  | ESTÁVEL          |
| Scheduler              | ESTÁVEL          |
| Paper Trading          | FUNCIONANDO      |
| Snapshots              | FUNCIONANDO      |
| Score                  | FUNCIONANDO      |
| CVM                    | PARCIAL          |
| FNET                   | ESTRUTURA PRONTA |
| Gemini                 | PRONTO SEM CHAVE |
| Replay Histórico       | PARCIAL          |
| Aprendizado            | FUNCIONANDO      |
| Pipeline Institucional | EM CONSOLIDAÇÃO  |
