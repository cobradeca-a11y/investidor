# FIIA — Aprendizado Operacional e Ajuste de Pesos

Este documento descreve a camada de aprendizado operacional do FIIA. O objetivo é transformar resultados observados em sugestões controladas de ajuste, sem autoalterar regras críticas.

## 1. Princípio central

O aprendizado do FIIA é supervisionado e auditável.

```text
resultado observado
↓
avaliação temporal
↓
detecção de falso positivo / falso negativo
↓
sugestão controlada de ajuste
↓
aprovação humana obrigatória
↓
registro auditável do feedback humano
```

Nenhum ajuste é aplicado automaticamente.

## 2. Janelas temporais suportadas

A avaliação temporal deve suportar:

```text
30 dias
90 dias
180 dias
365 dias
```

Essas janelas estão configuradas em `config/settings.py` por meio de:

```python
JANELAS_AVALIACAO_DIAS = [30, 90, 180, 365]
```

## 3. Avaliação temporal

O módulo `aprendizado.resultados` avalia o desempenho observado de uma decisão ou simulação.

Campos principais:

- `ticker`;
- `data_decisao`;
- `data_avaliacao`;
- `janela_dias`;
- `acao_original`;
- `preco_entrada`;
- `preco_saida`;
- `retorno_preco_pct`;
- `retorno_dividendos_pct`;
- `retorno_total_pct`;
- `benchmark_pct`;
- `resultado`;
- `falso_positivo`;
- `falso_negativo`;
- `evidencia_json`.

A avaliação não aciona rede. Ela recebe os dados observados como entrada.

## 4. Falso positivo e falso negativo

### Falso positivo

Ocorre quando uma ação ofensiva não supera o benchmark.

Ações ofensivas:

- `COMPRAR`;
- `COMPRAR_PARCIAL`;
- `COMPRAR_PARCIALMENTE`;
- `MANTER`.

### Falso negativo

Ocorre quando uma ação defensiva supera o benchmark.

Ações defensivas:

- `EVITAR`;
- `EVITAR_ENTRADA`;
- `MONITORAR`;
- `AGUARDAR`;
- `REDUZIR`;
- `VENDER`;
- `BLOQUEAR_APORTE`.

## 5. Sugestões controladas de ajuste

O módulo `aprendizado.ajustes_pesos` gera sugestões com base em padrões observados.

Toda sugestão deve conter:

- `regra`;
- `tipo_sugestao`;
- `peso_atual`;
- `peso_sugerido`;
- `evidencia_json`;
- `amostra`;
- `periodo_inicio`;
- `periodo_fim`;
- `impacto_estimado`;
- `motivo`;
- `aplicado=0`;
- `requer_aprovacao_humana=1`.

Tipos de sugestão:

- `REDUZIR_PESO`;
- `AUMENTAR_PESO`;
- `REVISAR_REGRA`;
- `MANTER_SEM_ALTERACAO`.

## 6. Estados de aprovação humana

Toda sugestão possui um estado auditável:

```text
PENDENTE
APROVADA
REJEITADA
EXPIRADA
```

Regras:

- Toda sugestão nasce como `PENDENTE`.
- Apenas sugestões `PENDENTE` podem mudar de estado.
- Aprovar uma sugestão não altera motor, gates, thresholds ou pesos automaticamente.
- Rejeitar uma sugestão apenas registra feedback humano.
- Expirar uma sugestão apenas encerra sua validade operacional.

Cada decisão humana deve registrar:

- `usuario_decisao`;
- `origem_decisao`;
- `decidido_em`;
- `justificativa_decisao`.

## 7. Endpoints de feedback humano

Endpoints protegidos por API key:

```text
GET  /api/aprendizado/ajustes
POST /api/aprendizado/ajustes/{sugestao_id}/aprovar
POST /api/aprendizado/ajustes/{sugestao_id}/rejeitar
POST /api/aprendizado/ajustes/{sugestao_id}/expirar
```

Payload de aprovação/rejeição/expiração:

```json
{
  "usuario": "andre",
  "origem": "API",
  "justificativa": "Amostra suficiente para revisão manual."
}
```

Esses endpoints não disparam scraping e não chamam o motor decisório.

## 8. Bloqueio de aplicação automática

A função `aplicar_sugestao_automaticamente()` existe apenas como bloqueio explícito.

Resposta esperada:

```json
{
  "status": "bloqueado",
  "aplicado": false,
  "motivo": "Ajustes de pesos exigem aprovação humana e não são aplicados automaticamente."
}
```

## 9. Persistência

Tabelas aditivas criadas no `schema.sql`:

- `aprendizado_resultados_operacionais`;
- `aprendizado_sugestoes_ajuste_pesos`.

A tabela de sugestões registra também:

- `estado`;
- `usuario_decisao`;
- `origem_decisao`;
- `decidido_em`;
- `justificativa_decisao`;
- `data_expiracao`.

As migrações são aditivas:

- não alteram `decisoes`;
- não alteram gates;
- não alteram thresholds;
- não alteram motor;
- não alteram contrato final da decisão.

## 10. Contratos preservados

A camada de aprendizado não pode:

- alterar thresholds dos gates;
- alterar decisão final automaticamente;
- alterar motor decisório;
- alterar coleta/contexto;
- aplicar pesos automaticamente;
- esconder regra de ajuste;
- usar rede em teste unitário;
- aceitar feedback humano sem autenticação nos endpoints de aprovação.

## 11. Comandos de verificação

```bash
python -m compileall -q aprendizado api banco config
pytest teste_aprovacao_ajustes.py teste_seguranca_api.py
```

## 12. Checklist de homologação

```text
[ ] Janelas 30, 90, 180 e 365 suportadas.
[ ] Falso positivo detectado.
[ ] Falso negativo detectado.
[ ] Sugestões contêm evidência, amostra, período e impacto estimado.
[ ] Sugestões nascem como PENDENTE.
[ ] Estados APROVADA, REJEITADA e EXPIRADA funcionam.
[ ] Feedback humano registra usuário, origem, data e justificativa.
[ ] Endpoints de aprovação exigem autenticação.
[ ] Aprovação não altera motor automaticamente.
[ ] Nenhum ajuste é aplicado automaticamente.
[ ] Nenhum threshold de gate foi alterado.
[ ] Contrato final da decisão preservado.
[ ] Testes unitários não usam rede.
```
