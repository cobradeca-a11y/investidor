-- FIIA — Schema v1.0
-- Criar com: python main.py --setup

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─────────────────────────────────────────
-- FIIs cadastrados
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fiis (
    ticker              TEXT PRIMARY KEY,
    nome                TEXT,
    tipo                TEXT,       -- PAPEL, TIJOLO, HIBRIDO, FOF, DESENVOLVIMENTO, OUTRO
    segmento            TEXT,       -- LOGISTICA, LAJES, SHOPPING, PAPEL, FOF, BANCO, etc
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
    confiabilidade      INTEGER,    -- 0 a 100
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
    valor               REAL NOT NULL,
    tipo                TEXT DEFAULT 'INDEFINIDO', -- RECORRENTE, EXTRAORDINARIO, AMORTIZACAO, INDEFINIDO
    fonte               TEXT,
    UNIQUE(ticker, data_pagamento),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
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
-- Carteira pessoal
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

-- ─────────────────────────────────────────
-- Decisões do sistema (paper trading)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data                TEXT NOT NULL,
    preco_na_decisao    REAL,
    status              TEXT NOT NULL,  -- ENTRADA_SEGURA, ENTRADA_PARCIAL, AGUARDAR, etc
    score_qualidade     REAL,
    score_preco         REAL,
    score_risco         REAL,
    score_renda         REAL,
    score_mercado       REAL,
    score_confianca     REAL,
    margem_seguranca    REAL,
    premio_cdi          REAL,
    alertas             TEXT,           -- JSON array
    justificativa       TEXT,
    explicacao_simples  TEXT,           -- módulo educação
    versao_modelo       TEXT DEFAULT '1.0',
    criado_em           TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

-- ─────────────────────────────────────────
-- Resultado das decisões (avaliação futura)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisoes_resultado (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id          INTEGER NOT NULL,
    data_avaliacao      TEXT NOT NULL,
    janela_dias         INTEGER,        -- 90, 180, 365
    preco_avaliacao     REAL,
    retorno_preco       REAL,
    retorno_dividendos  REAL,
    retorno_total       REAL,
    retorno_cdi_periodo REAL,
    retorno_ifix_periodo REAL,
    acerto              INTEGER,        -- 1 ou 0
    tipo_erro           TEXT,           -- MODELO, DADOS, MERCADO, NULL
    observacao          TEXT,
    avaliado_em         TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (decisao_id) REFERENCES decisoes(id)
);

-- ─────────────────────────────────────────
-- Versões do modelo de pesos
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS versoes_modelo (
    versao              TEXT PRIMARY KEY,
    data                TEXT NOT NULL,
    descricao           TEXT,
    pesos_json          TEXT NOT NULL,  -- JSON com todos os pesos
    motivo_mudanca      TEXT,
    aprovado_em         TEXT
);

-- ─────────────────────────────────────────
-- Sugestões de ajuste (aprendizado adaptativo)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sugestoes_ajuste (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    data                TEXT NOT NULL,
    tipo_fundo          TEXT NOT NULL,
    peso_afetado        TEXT NOT NULL,
    valor_atual         REAL NOT NULL,
    valor_sugerido      REAL NOT NULL,
    amostras            INTEGER NOT NULL,
    diferenca_vs_cdi    REAL NOT NULL,
    consistencia_segmentos REAL NOT NULL,
    explicacao          TEXT,
    aprovado            INTEGER DEFAULT NULL,  -- NULL=pendente, 1=sim, 0=não
    aprovado_em         TEXT,
    criado_em           TEXT DEFAULT (datetime('now','localtime'))
);

-- ─────────────────────────────────────────
-- Índices para performance
-- ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_indicadores_ticker_data ON indicadores(ticker, data);
CREATE INDEX IF NOT EXISTS idx_dividendos_ticker ON dividendos(ticker);
CREATE INDEX IF NOT EXISTS idx_decisoes_ticker ON decisoes(ticker);
CREATE INDEX IF NOT EXISTS idx_macro_data ON macro(data);

-- ─────────────────────────────────────────
-- Dados iniciais — versão 1.0 do modelo
-- ─────────────────────────────────────────
INSERT OR IGNORE INTO versoes_modelo (versao, data, descricao, pesos_json, motivo_mudanca, aprovado_em)
VALUES (
    '1.0',
    date('now'),
    'Versão inicial — pesos conservadores para renda de longo prazo',
    '{
        "PAPEL":       {"qualidade":0.15,"renda":0.25,"preco":0.20,"risco":0.25,"liquidez":0.10,"gestao":0.05},
        "TIJOLO":      {"qualidade":0.20,"renda":0.20,"preco":0.20,"risco":0.20,"liquidez":0.10,"gestao":0.10},
        "FOF":         {"qualidade":0.15,"renda":0.20,"preco":0.20,"risco":0.20,"liquidez":0.15,"gestao":0.10},
        "HIBRIDO":     {"qualidade":0.17,"renda":0.22,"preco":0.20,"risco":0.20,"liquidez":0.10,"gestao":0.11},
        "DESENVOLVIMENTO": {"qualidade":0.10,"renda":0.10,"preco":0.15,"risco":0.35,"liquidez":0.15,"gestao":0.15},
        "OUTRO":       {"qualidade":0.17,"renda":0.20,"preco":0.20,"risco":0.23,"liquidez":0.10,"gestao":0.10}
    }',
    'Criação inicial do projeto',
    date('now')
);
