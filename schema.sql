-- FIIA — Schema v1.1
-- Criar com: python main.py --setup
-- Sincronizado com implementações P2/P3 e ciclo operacional de aprendizado.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─────────────────────────────────────────
-- FIIs cadastrados
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fiis (
    ticker              TEXT PRIMARY KEY,
    nome                TEXT,
    tipo                TEXT,
    segmento            TEXT,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (datetime('now','localtime'))
);

-- ─────────────────────────────────────────
-- Snapshot diário de indicadores
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS indicadores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data                TEXT NOT NULL,
    preco               REAL,
    preco_timestamp     TEXT,
    preco_fonte         TEXT,
    preco_moeda         TEXT,
    pvp                 REAL,
    liquidez_diaria     REAL,
    ultimo_dividendo    REAL,
    dy_3m               REAL,
    dy_6m               REAL,
    dy_12m              REAL,
    dy_patrimonial      REAL,
    vacancia_fisica     REAL,
    vacancia_financeira REAL,
    patrimonio_liquido  REAL,
    vpa                 REAL,
    qtd_ativos          INTEGER,
    fonte               TEXT,
    confiabilidade      INTEGER,
    coletado_em         TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(ticker, data),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

-- ─────────────────────────────────────────
-- Histórico mensal de dividendos
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dividendos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data_pagamento      TEXT NOT NULL,
    data_base           TEXT,
    data_com            TEXT,
    valor               REAL NOT NULL,
    tipo                TEXT DEFAULT 'INDEFINIDO',
    fonte               TEXT,
    protocolo           TEXT,
    url_documento       TEXT,
    UNIQUE(ticker, data_pagamento),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

-- ─────────────────────────────────────────
-- CVM — Informes mensais FII versionados
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cvm_informes_mensais_fii (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_fundo                 TEXT NOT NULL,
    competencia                TEXT NOT NULL,
    versao                     INTEGER NOT NULL DEFAULT 1,
    reapresentacao             INTEGER NOT NULL DEFAULT 0,
    patrimonio_liquido         REAL,
    valor_patrimonial_cota     REAL,
    num_cotistas               INTEGER,
    num_cotas                  REAL,
    fonte                      TEXT NOT NULL DEFAULT 'CVM_INF_MENSAL',
    ano                        INTEGER,
    arquivo_origem             TEXT,
    coletado_em                TEXT NOT NULL,
    payload_json               TEXT,
    UNIQUE(cnpj_fundo, competencia, versao)
);

-- ─────────────────────────────────────────
-- FNET — Dividendos oficiais de avisos aos cotistas
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fnet_dividendos_fii (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    cnpj_fundo          TEXT,
    data_base           TEXT,
    data_com            TEXT,
    data_pagamento      TEXT NOT NULL,
    valor               REAL NOT NULL,
    tipo                TEXT DEFAULT 'INDEFINIDO',
    fonte               TEXT NOT NULL DEFAULT 'FNET_AVISO_COTISTAS',
    protocolo           TEXT,
    url_documento       TEXT,
    assunto             TEXT,
    arquivo_origem      TEXT,
    coletado_em         TEXT NOT NULL,
    payload_json        TEXT,
    dedupe_key          TEXT UNIQUE
);

-- ─────────────────────────────────────────
-- FNET — Classificações NLP/Gemini
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fnet_nlp_classificacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_hash      TEXT NOT NULL UNIQUE,
    documento_id        TEXT,
    ticker              TEXT,
    nivel               TEXT NOT NULL,
    motivo              TEXT,
    termos_detectados   TEXT,
    modelo              TEXT,
    criado_em           TEXT NOT NULL,
    payload_json        TEXT
);

-- ─────────────────────────────────────────
-- CVM — Informes trimestrais operacionais
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inf_trimestral_imoveis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    cnpj                TEXT NOT NULL,
    data_referencia     TEXT NOT NULL,
    nome_imovel         TEXT,
    classe              TEXT,
    area                REAL,
    vacancia_pct        REAL,
    inadimplencia_pct   REAL,
    receita_pct         REAL,
    locado_pct          REAL,
    UNIQUE(cnpj, data_referencia, nome_imovel)
);

CREATE TABLE IF NOT EXISTS inf_trimestral_contratos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    cnpj                TEXT NOT NULL,
    data_referencia     TEXT NOT NULL,
    venc_ate_3m         REAL,
    venc_3a6m           REAL,
    venc_6a12m          REAL,
    venc_acima_36m      REAL,
    indexador_igpm      REAL,
    indexador_ipca      REAL,
    UNIQUE(cnpj, data_referencia)
);

-- ─────────────────────────────────────────
-- Dados macroeconômicos diários
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS macro (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    data                TEXT NOT NULL UNIQUE,
    selic               REAL,
    cdi                 REAL,
    ipca                REAL,
    ifix                REAL,
    coletado_em         TEXT DEFAULT (datetime('now','localtime'))
);

-- ─────────────────────────────────────────
-- Carteira pessoal e de operações do FIIA
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS carteira (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data_compra         TEXT NOT NULL,
    preco_entrada       REAL NOT NULL,
    qtd_cotas           INTEGER NOT NULL,
    motivo              TEXT,
    tese                TEXT,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

CREATE TABLE IF NOT EXISTS carteira_posicoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL UNIQUE,
    quantidade          REAL NOT NULL DEFAULT 0,
    preco_medio         REAL NOT NULL DEFAULT 0,
    custo_total         REAL NOT NULL DEFAULT 0,
    segmento            TEXT,
    atualizado_em       TEXT NOT NULL,
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

CREATE TABLE IF NOT EXISTS carteira_operacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    tipo                TEXT NOT NULL,
    quantidade          REAL NOT NULL,
    preco               REAL NOT NULL,
    custos              REAL NOT NULL DEFAULT 0,
    valor_total         REAL NOT NULL,
    data_operacao       TEXT NOT NULL,
    origem              TEXT DEFAULT 'MANUAL',
    observacao          TEXT,
    criado_em           TEXT NOT NULL,
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

-- ─────────────────────────────────────────
-- Decisões do sistema
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisoes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    data_decisao      TEXT NOT NULL,
    decisao           TEXT NOT NULL,
    motivo            TEXT,
    confianca         TEXT,
    preco_na_decisao  REAL,
    preco_justo       REAL,
    preco_entrada     REAL,
    margem            REAL,
    score_ia          REAL,
    ia_status         TEXT,
    tom_gestor        TEXT,
    travas            TEXT,
    riscos_ia         TEXT,
    versao_modelo     TEXT DEFAULT '2.0',
    avaliada          INTEGER DEFAULT 0,
    criado_em         TEXT DEFAULT (datetime('now','localtime')),
    risco             TEXT,
    score_final       REAL,
    preco_teto        REAL,
    payload_json      TEXT,
    payload_hash      TEXT,
    contexto_versao   TEXT,
    versao_motor      TEXT,
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

CREATE TABLE IF NOT EXISTS decisoes_resultado (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id           INTEGER NOT NULL,
    data_avaliacao       TEXT NOT NULL,
    janela_dias          INTEGER,
    preco_avaliacao      REAL,
    retorno_preco        REAL,
    retorno_dividendos   REAL,
    retorno_total        REAL,
    retorno_cdi_periodo  REAL,
    retorno_ifix_periodo REAL,
    acerto               INTEGER,
    tipo_erro            TEXT,
    observacao           TEXT,
    avaliado_em          TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (decisao_id) REFERENCES decisoes(id)
);

-- ─────────────────────────────────────────
-- Governança de fontes de dados
-- Migração aditiva: não altera tabelas existentes nem contratos decisórios.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS governanca_fontes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte                   TEXT NOT NULL,
    ticker                  TEXT,
    data_referencia         TEXT NOT NULL,
    status                  TEXT NOT NULL CHECK(status IN ('OK', 'VENCIDA', 'DIVERGENTE', 'INDISPONIVEL', 'SUSPEITA')),
    motivo                  TEXT,
    idade_dias              INTEGER,
    max_idade_dias          INTEGER,
    divergencia_pct         REAL,
    disponibilidade_pct     REAL,
    score_confianca_fonte   REAL,
    payload_json            TEXT,
    criado_em               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_governanca_fontes_fonte_data ON governanca_fontes(fonte, data_referencia);
CREATE INDEX IF NOT EXISTS idx_governanca_fontes_ticker ON governanca_fontes(ticker);

-- ─────────────────────────────────────────
-- Score histórico de fontes
-- Migração aditiva: insumo auditável, sem efeito automático na decisão.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS governanca_fontes_score_historico (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte                   TEXT NOT NULL,
    ticker                  TEXT,
    data_referencia         TEXT NOT NULL,
    status                  TEXT NOT NULL CHECK(status IN ('OK', 'VENCIDA', 'DIVERGENTE', 'INDISPONIVEL', 'SUSPEITA')),
    score_confianca_fonte   REAL NOT NULL,
    motivo                  TEXT,
    payload_json            TEXT,
    criado_em               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_governanca_fontes_score_historico_fonte_data ON governanca_fontes_score_historico(fonte, data_referencia);
CREATE INDEX IF NOT EXISTS idx_governanca_fontes_score_historico_ticker_data ON governanca_fontes_score_historico(ticker, data_referencia);
