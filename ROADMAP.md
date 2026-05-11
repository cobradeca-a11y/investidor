# Roadmap do FIIA 🚀

## Fase 1 — Confiabilidade da Coleta ✅
**Objetivo**: Garantir que o algoritmo só analise quando os dados estão bons.

- [x] **Validação obrigatória**: Preço, P/VP, DY, Liquidez, Segmento e Data.
- [x] **Bloqueio por dados insuficientes**: Sistema não gera recomendação sem dados mínimos.
- [x] **Status claro**: BLOQUEADO_DADOS_INSUFICIENTES implementado na análise qualitativa.
- [x] **Log de falhas**: Integrado ao fluxo de coleta.

## Fase 2 — Motor de Decisão e Independência ✅
**Objetivo**: Separar o ranking técnico da análise de IA e entregar vereditos "mastigados".

- [x] **Ranking Quantitativo**: Funciona independente da disponibilidade da IA.
- [x] **Motor de Decisão**: Lógica centralizada em `motor_decisao.py` (COMPRAR, AGUARDAR, EVITAR, etc).
- [x] **IA no Top 3**: Análise qualitativa escalada para os 3 melhores do ranking.
- [x] **Tradutor de Decisao**: Linguagem simples e direta para o usuário final em `tradutor_decisao.py`.
- [x] **Fallback de IA**: Sistema continua operando mesmo se o Gemini estiver indisponível.

## Fase 3 — Memória e Evolução 🏗️
**Objetivo**: Aprender com as decisões passadas e rastrear o histórico.

- [x] **Gravação de Decisões**: Todas as decisões do radar são salvas na tabela `decisoes`.
- [ ] **Avaliação de Resultado**: Novo módulo para comparar o preço da decisão com o preço atual (X meses depois).
- [ ] **Feedback Loop**: IA analisa por que uma recomendação de COMPRA subiu ou caiu.
- [ ] **Versão do Modelo**: Rastreamento de qual versão do motor gerou cada decisão.

## Fase 4 — Carteira e Rebalanceamento 📅
**Objetivo**: Gerenciar os ativos que o usuário já possui.

- [ ] **Tabela de Carteira**: Registro de preço médio e quantidade.
- [ ] **Sugestão de Rebalanceamento**: "Venda X para comprar Y" baseado no novo ranking.
- [ ] **Avisos de Alocação**: Alerta se um segmento (ex: Logística) estiver muito pesado na carteira.

## Fase 5 — Automação e Notificações 📡
**Objetivo**: O FIIA trabalhando enquanto você dorme.

- [ ] **Execução Agendada**: Radar roda automaticamente todo dia às 18h.
- [ ] **Notificações**: Envio do Top 3 via Telegram ou E-mail.
- [ ] **Dashboard Web**: Visualização rica das decisões e evolução da carteira (FastAPI/PWA).

---
*Atualizado em: 10 de maio de 2026*
