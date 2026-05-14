# FIIA — Inventário de Dependências de Dados

Este documento registra o passivo técnico central do FIIA: quais campos ainda dependem de fontes frágeis, especialmente Fundamentus/Yahoo, e quais precisam migrar para CVM/FNET/BCB como núcleo oficial.

Objetivo imediato: expor onde o motor analítico ainda está apoiado em dados sem versionamento oficial, sem timestamp confiável ou sem reapresentação formal.

---

## 1. Princípio de classificação

As fontes são classificadas assim:

| Classe | Fonte | Papel correto |
|---|---|---|
| Oficial | CVM Dados Abertos | Núcleo estrutural para dados de fundos |
| Oficial macro | Banco Central | Núcleo macroeconômico |
| Documental | B3/Fundos.NET | Validação documental, regulamentos, fatos relevantes |
| Mercado | Yahoo, brapi, Investing | Cotação, OHLC, volume, histórico de mercado |
| Auxiliar | Fundamentus, Status Invest, Funds Explorer, InfoMoney | Bootstrap, conferência, enriquecimento, fallback |
| IA | Gemini/LLM | Interpretação, não fonte primária |

---

## 2. Campos críticos atuais do motor

| Campo | Uso no FIIA | Fonte atual provável | Fallback oficial desejado | Criticidade | Risco atual | Ação recomendada |
|---|---|---|---|---|---|---|
| ticker | identidade do ativo | Fundamentus/Yahoo/base local | B3 + CVM/FNET | Alta | Médio | consolidar tabela mestre B3/CVM |
| CNPJ fundo | identidade canônica | tabela mestre/CVM em progresso | CVM | Altíssima | Médio | tornar obrigatório no pipeline |
| CNPJ classe | identidade canônica | CVM em progresso | CVM | Altíssima | Médio | normalizar em tabela própria |
| preço atual | Gate 0, Gate 4, margem | Fundamentus/Yahoo | B3/brapi/Yahoo como mercado | Alta | Médio | manter mercado, mas com timestamp e fonte |
| liquidez diária | Gate 1 | Fundamentus | B3/brapi/Yahoo | Alta | Alto | criar fallback de mercado e média própria |
| P/VP | Gate 0, Gate 4 | Fundamentus | CVM VP/cota + preço mercado | Alta | Alto | recalcular internamente |
| VPA/VP cota | Gate 0, margem | Fundamentus | CVM informe mensal | Altíssima | Alto | CVM deve virar fonte primária |
| patrimônio líquido | Gate 1 | Fundamentus | CVM informe mensal/trimestral | Alta | Alto | migrar para CVM |
| DY 12m | Gate 0, renda | Fundamentus/Yahoo | rendimentos próprios + preço mercado | Alta | Alto | recalcular internamente |
| dividendos | Gate 3, avaliador | Yahoo | FNET/documentos + base própria | Alta | Alto | criar histórico próprio versionado |
| data pagamento dividendos | Gate 3, avaliador | Yahoo | FNET/avisos aos cotistas | Alta | Alto | validar com FNET |
| data base/data com | renda/carteira | Yahoo/auxiliares | FNET/B3/documentos | Alta | Alto | capturar via documentos oficiais |
| vacância física | Gate 2 | Fundamentus/CVM trimestral | CVM informe trimestral/relatórios | Alta | Médio | priorizar CVM trimestral |
| quantidade de ativos | Gate 2 | Fundamentus/relatórios | CVM/FNET/relatórios | Média | Médio | consolidar via FNET/relatório gerencial |
| segmento | Gates, setorial | base local/Fundamentus | classificação própria + B3/CVM | Alta | Médio | criar taxonomia interna versionada |
| tipo do fundo | Gate 2 | base local/Fundamentus | regulamento/FNET | Alta | Médio | validar em FNET/regulamento |
| inadimplência | saúde operacional | ausente/parcial | relatório gerencial/FNET/CVM | Alta | Alto | estruturar extração documental |
| concentração por inquilino | saúde operacional | ausente/parcial | relatório gerencial/FNET | Média/Alta | Alto | extrair de relatórios |
| taxa de administração/gestão | governança | ausente/parcial | regulamento/FNET/informe anual | Média | Alto | criar ingestão documental |
| política de distribuição | governança/renda | ausente/parcial | regulamento/FNET | Alta | Alto | extrair de regulamento/informe anual |
| fatos relevantes | qualitativo/risco | FNET/InfoMoney | FNET | Alta | Médio | FNET como fonte documental primária |
| notícias | qualitativo | InfoMoney/DuckDuckGo | fontes auxiliares | Média | Médio | usar apenas como contexto |
| Selic/CDI/IPCA/IGP-M | macro | BCB | BCB | Alta | Baixo | manter BCB como fonte oficial |

---

## 3. Campos que não devem depender de Fundamentus como núcleo

Prioridade máxima de migração:

1. VP/cota / VPA
2. Patrimônio líquido
3. P/VP
4. DY 12m
5. Dividendos/rendimentos
6. Liquidez diária
7. Vacância física
8. Segmento/tipo do fundo
9. Quantidade de ativos
10. Política de distribuição

---

## 4. Estratégia de substituição por fonte oficial

### 4.1 CVM como fonte primária

Usar CVM para:

- patrimônio líquido;
- VP/cota;
- número de cotistas;
- informes mensais;
- informes trimestrais;
- demonstrações financeiras;
- reapresentações;
- dados de imóveis quando disponíveis.

### 4.2 FNET como fonte documental

Usar FNET para:

- fatos relevantes;
- relatórios gerenciais;
- regulamentos;
- avisos aos cotistas;
- documentos de distribuição;
- comunicados de rendimentos.

### 4.3 Mercado como fonte de preço

Usar Yahoo/brapi/Investing apenas para:

- preço;
- OHLC;
- volume;
- liquidez;
- volatilidade;
- drawdown.

Esses dados precisam carregar timestamp e fonte.

---

## 5. Critérios de criticidade

### Altíssima

Campo sem o qual a identidade ou análise fica estruturalmente inválida.

Exemplos:

- CNPJ fundo;
- CNPJ classe;
- VP/cota;
- patrimônio líquido.

### Alta

Campo que altera decisão, gate ou risco.

Exemplos:

- liquidez;
- DY;
- dividendos;
- vacância;
- segmento.

### Média

Campo que melhora qualidade da análise, mas não deveria sozinho gerar compra/venda.

Exemplos:

- notícias;
- tom do gestor;
- quantidade de ativos quando não crítica.

---

## 6. Regras operacionais até a migração

Enquanto CVM/FNET não substituírem a fonte frágil:

1. O campo deve ser marcado como auxiliar.
2. A decisão forte deve ser rebaixada se o campo for crítico.
3. O relatório deve expor a fonte usada.
4. O gate deve registrar se o dado veio de fonte frágil.
5. Nenhum dado auxiliar deve ser tratado como verdade oficial.

---

## 7. Próxima entrega técnica

Criar módulo programático:

```text
validacao/inventario_dependencias.py
```

Função esperada:

```python
listar_dependencias_criticas()
```

Saída esperada:

```python
[
    {
        "campo": "vpa",
        "fonte_atual": "Fundamentus",
        "fallback_oficial": "CVM informe mensal",
        "criticidade": "ALTISSIMA",
        "risco": "ALTO",
        "acao": "migrar para CVM como fonte primária"
    }
]
```

---

## 8. Decisão arquitetural

A partir deste inventário, a ordem correta é:

```text
CVM/FNET como núcleo
↓
Confiança dentro dos Gates
↓
Decisão com confiança
↓
Avaliador temporal agendado
↓
API de auditoria
↓
Gestão de carteira
↓
Carteira no banco
```
