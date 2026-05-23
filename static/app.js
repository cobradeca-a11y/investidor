/**
 * app.js - FIIA Intelligence Interface
 * Versão 2.3 - Histórico e Replay no Dashboard
 *
 * Regras:
 * - não recalcula hash no frontend;
 * - não altera payload da API;
 * - replay é explícito e só roda quando o usuário solicita;
 * - histórico não chama motor nem scraping por padrão;
 * - renderiza campos ausentes sem quebrar;
 * - mantém cards bloqueados visíveis.
 */

document.addEventListener('DOMContentLoaded', () => {
    inicializarNavegacao();
    inicializarTransacoes();
    inicializarPlayground();
    criarPainelMaquinaTempo();
    criarPainelHistorico();
    criarPainelAssistente();
    iniciarMonitorAlertasAssistente();
    carregarCarteira();

    // Sincronizar chave de API no header
    const headerApiKeyInput = document.getElementById('headerApiKey');
    if (headerApiKeyInput) {
        headerApiKeyInput.value = obterApiKey();
        headerApiKeyInput.addEventListener('input', (e) => {
            salvarApiKey(e.target.value);
        });
    }
});

document.getElementById('btnRadar')?.addEventListener('click', async () => {
    const apiKey = obterOuSolicitarApiKey('ligar o radar');
    if (!apiKey) return;

    const welcomeView = document.getElementById('welcomeView');
    const loading = document.getElementById('loading');
    const resultsGrid = document.getElementById('results');
    const btnRadar = document.getElementById('btnRadar');
    welcomeView?.classList.add('hidden');
    resultsGrid?.classList.add('hidden');
    loading?.classList.remove('hidden');
    btnRadar.disabled = true;
    btnRadar.innerHTML = '<span class="icon">⌛</span> Processando...';

    try {
        const data = await executarRadarAssincrono();
        loading?.classList.add('hidden');
        resultsGrid?.classList.remove('hidden');
        renderResults(data.oportunidades || [], 'results');
    } catch (error) {
        console.error(error);
        alert(`Erro ao ligar o radar: ${error.message || 'verifique se o servidor está rodando.'}`);
        loading?.classList.add('hidden');
        welcomeView?.classList.remove('hidden');
    } finally {
        btnRadar.disabled = false;
        btnRadar.innerHTML = '<span class="icon">🔍</span> Ligar Radar';
    }
});

document.getElementById('btnClear')?.addEventListener('click', () => window.location.reload());

function obterApiKey() {
    return localStorage.getItem('fiia_api_key') || '';
}

function salvarApiKey(valor) {
    const apiKey = (valor || '').trim();
    if (!apiKey) return '';
    localStorage.setItem('fiia_api_key', apiKey);
    return apiKey;
}

function obterOuSolicitarApiKey(acao = 'continuar') {
    const apiKey = obterApiKey();
    if (apiKey) return apiKey;
    const headerInput = document.getElementById('headerApiKey');
    if (headerInput) {
        headerInput.focus();
    }
    const informada = window.prompt(`Configure sua chave de API (fiia_api_key) para ${acao}.\n\nCole a FIIA_API_KEY do seu .env (ou digite no campo "Key" no topo da página):`);
    const salva = salvarApiKey(informada);
    if (headerInput && salva) {
        headerInput.value = salva;
    }
    return salva;
}

function headersAutenticados(extra = {}) {
    const apiKey = obterApiKey();
    return apiKey ? { ...extra, 'X-API-Key': apiKey } : extra;
}

const RADAR_POLL_MS = 2000;
const RADAR_TIMEOUT_MS = 900000;

function esperar(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function atualizarStatusRadar(texto) {
    const loading = document.getElementById('loading');
    const subtitulo = loading?.querySelector('p');
    if (subtitulo && texto) subtitulo.textContent = texto;
}

async function fetchRadarSincronoFallback() {
    // Compatibilidade: o contrato antigo permanece fetch('/api/radar') para ambientes sem job async.
    const response = await fetch('/api/radar', { headers: headersAutenticados() });
    if (!response.ok) {
        throw new Error(`Radar retornou HTTP ${response.status}`);
    }
    return response.json();
}

async function executarRadarAssincrono() {
    atualizarStatusRadar('Iniciando job do Radar...');

    let inicio;
    try {
        inicio = await fetch('/api/radar/jobs', {
            method: 'POST',
            headers: headersAutenticados()
        });
    } catch (error) {
        atualizarStatusRadar('Job assíncrono indisponível. Usando execução direta...');
        return fetchRadarSincronoFallback();
    }

    if (inicio.status === 404 || inicio.status === 405) {
        atualizarStatusRadar('Job assíncrono indisponível. Usando execução direta...');
        return fetchRadarSincronoFallback();
    }

    if (!inicio.ok) {
        throw new Error(`Radar job retornou HTTP ${inicio.status}`);
    }

    const payload = await inicio.json();
    const jobId = payload.job_id;
    if (!jobId) {
        throw new Error('Radar job sem identificador.');
    }

    const inicioTempo = Date.now();
    while (Date.now() - inicioTempo < RADAR_TIMEOUT_MS) {
        await esperar(RADAR_POLL_MS);
        atualizarStatusRadar('Radar em execução. Consultando progresso...');

        const consulta = await fetch(`/api/radar/jobs/${encodeURIComponent(jobId)}`, {
            headers: headersAutenticados()
        });
        if (!consulta.ok) {
            throw new Error(`Consulta do Radar job retornou HTTP ${consulta.status}`);
        }

        const statusPayload = await consulta.json();
        const job = statusPayload.job || {};
        if (job.status === 'concluido') {
            atualizarStatusRadar('Radar concluído. Renderizando oportunidades...');
            return job.resultado || { status: 'ok', oportunidades: [], quantidade: 0 };
        }
        if (job.status === 'erro') {
            const detalhe = job.detalhe ? `: ${job.detalhe}` : '';
            throw new Error(`${job.mensagem || 'Radar job falhou.'}${detalhe}`);
        }
    }

    throw new Error('Tempo limite ao aguardar Radar job.');
}

function inicializarNavegacao() {
    const tabs = {
        'btnTabHome': 'homeView',
        'btnCarteira': 'portfolioView',
        'btnRadarTab': 'radarView',
        'btnTabAssistente': 'assistenteDiario',
        'btnTabMaquinaTempo': 'maquinaTempo',
        'btnTabHistorico': 'historicoDecisoes'
    };

    const btnRadarAction = document.getElementById('btnRadar');

    // Suporte para clique no logo para voltar para home
    document.getElementById('btnHomeLogo')?.addEventListener('click', () => {
        Object.keys(tabs).forEach(id => {
            document.getElementById(id)?.classList.remove('active');
            document.getElementById(tabs[id])?.classList.add('hidden');
        });
        document.getElementById('homeView')?.classList.remove('hidden');
        btnRadarAction?.classList.add('hidden');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    document.getElementById('btnExploreDashboard')?.addEventListener('click', () => {
        Object.keys(tabs).forEach(id => {
            document.getElementById(id)?.classList.remove('active');
            document.getElementById(tabs[id])?.classList.add('hidden');
        });
        document.getElementById('portfolioView')?.classList.remove('hidden');
        btnRadarAction?.classList.add('hidden');
        carregarCarteira();
    });

    document.getElementById('btnExploreTools')?.addEventListener('click', () => {
        Object.keys(tabs).forEach(id => {
            document.getElementById(id)?.classList.remove('active');
            document.getElementById(tabs[id])?.classList.add('hidden');
        });
        document.getElementById('assistenteDiario')?.classList.remove('hidden');
        btnRadarAction?.classList.add('hidden');
        carregarAlertasAssistente();
    });

    Object.keys(tabs).forEach(tabId => {
        const btn = document.getElementById(tabId);
        const viewId = tabs[tabId];
        const view = document.getElementById(viewId);

        btn?.addEventListener('click', () => {
            // Remove a classe active de todas as abas e oculta as views
            Object.keys(tabs).forEach(id => {
                document.getElementById(id)?.classList.remove('active');
                document.getElementById(tabs[id])?.classList.add('hidden');
            });

            // Ativa a aba e a view correspondente
            btn.classList.add('active');
            view?.classList.remove('hidden');

            // Mostra ou esconde o botão de ligar radar do cabeçalho
            if (tabId === 'btnRadarTab') {
                btnRadarAction?.classList.remove('hidden');
                // Se o radar estiver carregado, mantemos como está, caso contrário mostramos o welcome
                const results = document.getElementById('results');
                const loading = document.getElementById('loading');
                if (results?.classList.contains('hidden') && loading?.classList.contains('hidden')) {
                    document.getElementById('welcomeView')?.classList.remove('hidden');
                }
            } else {
                btnRadarAction?.classList.add('hidden');
            }

            // Ações específicas de carregamento
            if (tabId === 'btnCarteira') {
                carregarCarteira();
            } else if (tabId === 'btnTabAssistente') {
                carregarAlertasAssistente();
            }
        });
    });
}

function inicializarTransacoes() {
    const btnOpenModal = document.getElementById('btnOpenModal');
    const btnCloseModal = document.getElementById('btnCloseModal');
    const transactionModal = document.getElementById('transactionModal');
    const transactionForm = document.getElementById('transactionForm');

    btnOpenModal?.addEventListener('click', () => transactionModal?.classList.remove('hidden'));
    btnCloseModal?.addEventListener('click', () => transactionModal?.classList.add('hidden'));
    window.addEventListener('click', (e) => {
        if (e.target === transactionModal) transactionModal.classList.add('hidden');
    });

    transactionForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const apiKey = obterOuSolicitarApiKey('registrar operacoes');
        if (!apiKey) {
            alert('Configure sua chave de API (fiia_api_key) no localStorage antes de registrar operações.');
            return;
        }
        const submitBtn = transactionForm.querySelector('.btn-submit');
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Gravando...';
        const payload = {
            ticker: document.getElementById('txTicker').value.trim().toUpperCase(),
            quantidade: parseFloat(document.getElementById('txQtd').value),
            preco: parseFloat(document.getElementById('txPreco').value),
            segmento: document.getElementById('txSegmento').value || null,
            custos: 0.0,
            origem: 'PWA_DASHBOARD'
        };
        try {
            const response = await fetch('/api/carteira/compra', {
                method: 'POST',
                headers: headersAutenticados({ 'Content-Type': 'application/json' }),
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (data.status === 'ok') {
                alert('Transação registrada com sucesso!');
                transactionForm.reset();
                transactionModal?.classList.add('hidden');
                carregarCarteira();
            } else {
                alert('Erro ao registrar transação: ' + (data.mensagem || 'Erro desconhecido'));
            }
        } catch (error) {
            console.error('Erro de envio:', error);
            alert('Falha ao conectar com a API para registrar a compra.');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Registrar Compra';
        }
    });
}

async function carregarCarteira() {
    const grid = document.getElementById('portfolioGrid');
    if (!grid) return;
    if (!obterApiKey()) {
        grid.innerHTML = `
            <div class="empty-state-container glass-card">
                <h3>Chave de API necessaria</h3>
                <p>Informe sua <strong>fiia_api_key</strong> para carregar carteira, Radar e historico.</p>
                <button id="btnConfigApiKeyCarteira" class="btn-transaction">Configurar chave</button>
            </div>
            <div id="demoGrid" class="results-grid"></div>
        `;
        document.getElementById('btnConfigApiKeyCarteira')?.addEventListener('click', () => {
            if (obterOuSolicitarApiKey('carregar a carteira')) carregarCarteira();
        });
        renderResults([mockAtivo()], 'demoGrid', false);
        return;
    }
    grid.innerHTML = '<div class="loading-simple">⌛ Carregando ativos...</div>';

    try {
        const response = await fetch('/api/carteira/posicoes', { headers: headersAutenticados() });
        const data = await response.json();
        if (data.status === 'ok' && data.posicoes && data.posicoes.length > 0) {
            renderResults(data.posicoes, 'portfolioGrid', true);
        } else {
            grid.innerHTML = `
                <div class="empty-state-container glass-card">
                    <h3>Sua carteira está vazia!</h3>
                    <p>Registre suas operações clicando no botão <strong>+ Registrar Transação</strong> acima.</p>
                    <span class="demo-badge">Abaixo você vê um exemplo de como seus ativos serão analisados:</span>
                </div>
                <div id="demoGrid" class="results-grid"></div>
            `;
            renderResults([mockAtivo()], 'demoGrid', false);
        }
    } catch (error) {
        console.error('Erro ao buscar posições da carteira:', error);
        grid.innerHTML = '<div class="error-simple">❌ Erro ao conectar ao servidor. Exibindo dados de demonstração:</div><div id="demoGrid" class="results-grid"></div>';
        renderResults([mockAtivo()], 'demoGrid', false);
    }
}

function criarPainelHistorico() {
    // Se o painel já existe no HTML estático, apenas registrar os listeners
    if (document.getElementById('historicoDecisoes')) {
        document.getElementById('btnHistoricoDecisoes')?.addEventListener('click', carregarHistoricoDecisoes);
        return;
    }

    const container = document.querySelector('.app-container') || document.body;
    const section = document.createElement('section');
    section.id = 'historicoDecisoes';
    section.className = 'history-panel glass-card';
    section.innerHTML = `
        <div class="history-header">
            <div>
                <h2>Histórico e Replay</h2>
                <p>Consulta auditável de decisões salvas. Replay só é executado por ação explícita.</p>
            </div>
            <button id="btnHistoricoDecisoes" class="btn-transaction">Carregar histórico</button>
        </div>
        <div id="historicoLista" class="history-list">
            <div class="audit-empty">Histórico ainda não carregado.</div>
        </div>
        <div id="historicoDetalhe" class="history-detail hidden"></div>
    `;
    container.appendChild(section);
    document.getElementById('btnHistoricoDecisoes')?.addEventListener('click', carregarHistoricoDecisoes);
}

function criarPainelAssistente() {
    // Se o painel já existe no HTML estático, apenas registrar os listeners
    if (document.getElementById('assistenteDiario')) {
        document.getElementById('btnAssistenteAlertas')?.addEventListener('click', carregarAlertasAssistente);
        document.getElementById('btnAssistenteAlertas2')?.addEventListener('click', carregarAlertasAssistente);
        document.getElementById('btnAssistenteRebalance2')?.addEventListener('click', carregarRebalanceamento);
        document.getElementById('btnAssistenteRebalance')?.addEventListener('click', carregarRebalanceamento);
        return;
    }

    const container = document.querySelector('.app-container') || document.body;
    const section = document.createElement('section');
    section.id = 'assistenteDiario';
    section.className = 'history-panel glass-card';
    section.innerHTML = `
        <div class="history-header">
            <div>
                <h2>Assistente Diario</h2>
                <p>Alertas, evolucao, rebalanceamento e detalhe por fundo sem acionar scraping.</p>
            </div>
            <div class="assist-actions">
                <span id="alertasNovosBadge" class="assist-badge hidden">0</span>
                <button id="btnAssistenteAlertas" class="btn-transaction">Ver alertas <span id="assistenteAlertasBadge" class="alert-badge hidden">0</span></button>
                <button id="btnAssistenteRebalance" class="btn-transaction secondary">Rebalancear</button>
            </div>
        </div>
        <div id="assistenteResumo" class="history-list">
            <div class="audit-empty">Assistente ainda nao carregado.</div>
        </div>
        <div id="assistenteDetalhe" class="history-detail hidden"></div>
    `;
    container.appendChild(section);
    document.getElementById('btnAssistenteAlertas')?.addEventListener('click', carregarAlertasAssistente);
    document.getElementById('btnAssistenteRebalance')?.addEventListener('click', carregarRebalanceamento);
}

const ASSISTENTE_ALERTAS_POLL_MS = 60000;

function ultimoAlertaAssistenteId() {
    return parseInt(localStorage.getItem('fiia_alertas_ultimo_id') || localStorage.getItem('fiia_ultimo_alerta_id') || '0', 10) || 0;
}

function criarPainelMaquinaTempo() {
    // Se o painel já existe no HTML estático, apenas registrar os listeners
    if (document.getElementById('maquinaTempo')) {
        document.getElementById('btnMaquinaSnapshot')?.addEventListener('click', gerarBaseMaquinaTempo);
        document.getElementById('btnMaquinaTicker')?.addEventListener('click', executarMaquinaTempoTicker);
        document.getElementById('btnMaquinaRadar')?.addEventListener('click', executarMaquinaTempoRadar);
        return;
    }

    const container = document.querySelector('.app-container') || document.body;
    const section = document.createElement('section');
    section.id = 'maquinaTempo';
    section.className = 'history-panel glass-card machine-panel';
    section.innerHTML = `
        <div class="history-header">
            <div>
                <h2>Maquina do Tempo</h2>
                <p>Simula uma decisao em data historica usando apenas snapshots validos daquela epoca.</p>
            </div>
        </div>
        <div class="machine-form">
            <label>Ticker <input id="mtTicker" type="text" value="HGLG11" maxlength="12" autocomplete="off"></label>
            <label>Data <input id="mtData" type="date" value="2021-05-20"></label>
            <label>Horizonte <input id="mtHorizonte" type="number" value="365" min="30" max="3650" step="30"></label>
            <label>Top radar <input id="mtTop" type="number" value="5" min="1" max="30" step="1"></label>
            <div class="machine-actions">
                <button id="btnMaquinaSnapshot" class="btn-transaction secondary">Gerar base da data</button>
                <button id="btnMaquinaTicker" class="btn-transaction">Rodar ativo</button>
                <button id="btnMaquinaRadar" class="btn-transaction secondary">Rodar top 5</button>
            </div>
        </div>
        <div id="maquinaResultado" class="machine-result">
            <div class="audit-empty">Escolha ativo/data para verificar cobertura, decisao historica e resultado futuro.</div>
        </div>
    `;
    container.appendChild(section);
    document.getElementById('btnMaquinaSnapshot')?.addEventListener('click', gerarBaseMaquinaTempo);
    document.getElementById('btnMaquinaTicker')?.addEventListener('click', executarMaquinaTempoTicker);
    document.getElementById('btnMaquinaRadar')?.addEventListener('click', executarMaquinaTempoRadar);
}

function obterParametrosMaquinaTempo() {
    return {
        ticker: (document.getElementById('mtTicker')?.value || '').toUpperCase().replace('.SA', '').trim(),
        data: document.getElementById('mtData')?.value || '',
        horizonte: parseInt(document.getElementById('mtHorizonte')?.value || '365', 10) || 365,
        top: parseInt(document.getElementById('mtTop')?.value || '5', 10) || 5
    };
}

async function executarMaquinaTempoTicker() {
    const apiKey = obterOuSolicitarApiKey('rodar a Maquina do Tempo');
    if (!apiKey) return;

    const alvo = document.getElementById('maquinaResultado');
    const params = obterParametrosMaquinaTempo();
    if (!params.ticker || !params.data) {
        alvo.innerHTML = '<div class="error-simple">Informe ticker e data para rodar a Maquina do Tempo.</div>';
        return;
    }
    alvo.innerHTML = '<div class="loading-simple">Consultando snapshot e executando backtest temporal...</div>';

    try {
        const response = await fetch('/api/maquina-tempo/backtest', {
            method: 'POST',
            headers: headersAutenticados({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ ticker: params.ticker, data: params.data, horizonte: params.horizonte })
        });
        const data = await response.json();
        alvo.innerHTML = renderMaquinaTempoTicker(data);
    } catch (error) {
        console.error('Erro na Maquina do Tempo:', error);
        alvo.innerHTML = '<div class="error-simple">Falha controlada ao executar Maquina do Tempo.</div>';
    }
}

async function gerarBaseMaquinaTempo() {
    const apiKey = obterOuSolicitarApiKey('gerar base temporal');
    if (!apiKey) return;

    const alvo = document.getElementById('maquinaResultado');
    const params = obterParametrosMaquinaTempo();
    if (!params.ticker || !params.data) {
        alvo.innerHTML = '<div class="error-simple">Informe ticker e data para gerar a base temporal.</div>';
        return;
    }
    alvo.innerHTML = '<div class="loading-simple">Gerando snapshot local com COTAHIST, CVM mensal, dividendos e macro...</div>';

    try {
        const response = await fetch('/api/maquina-tempo/snapshots', {
            method: 'POST',
            headers: headersAutenticados({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
                ticker: params.ticker,
                data_inicio: params.data,
                data_fim: params.data,
                passo_dias: 30
            })
        });
        const data = await response.json();
        alvo.innerHTML = renderSnapshotTemporal(data);
    } catch (error) {
        console.error('Erro ao gerar base temporal:', error);
        alvo.innerHTML = '<div class="error-simple">Falha controlada ao gerar base temporal.</div>';
    }
}

function renderSnapshotTemporal(data) {
    const ok = Number(data.ok || 0);
    const insuficientes = Number(data.insuficientes || 0);
    const primeiro = (data.resultados || [])[0] || {};
    return `
        <details class="audit-panel machine-detail" open>
            <summary>Base temporal - ${escapeHtml(data.ticker || 'ativo')}</summary>
            <div class="audit-grid">
                <div><span>Snapshots OK</span><strong>${escapeHtml(String(ok))}</strong></div>
                <div><span>Insuficientes</span><strong>${escapeHtml(String(insuficientes))}</strong></div>
                <div><span>Inicio</span><strong>${escapeHtml(textoSeguro(data.data_inicio))}</strong></div>
                <div><span>Fim</span><strong>${escapeHtml(textoSeguro(data.data_fim))}</strong></div>
            </div>
            <div class="audit-blocks"><strong>Status:</strong> ${escapeHtml(primeiro.status || data.status || 'Nao informado')} ${primeiro.faltantes ? `- faltantes: ${escapeHtml(primeiro.faltantes.join(', '))}` : ''}</div>
        </details>
    `;
}

async function executarMaquinaTempoRadar() {
    const apiKey = obterOuSolicitarApiKey('rodar o radar temporal');
    if (!apiKey) return;

    const alvo = document.getElementById('maquinaResultado');
    const params = obterParametrosMaquinaTempo();
    if (!params.data) {
        alvo.innerHTML = '<div class="error-simple">Informe a data para rodar o radar temporal.</div>';
        return;
    }
    alvo.innerHTML = '<div class="loading-simple">Montando ranking temporal com snapshots historicos...</div>';

    try {
        const response = await fetch('/api/maquina-tempo/radar', {
            method: 'POST',
            headers: headersAutenticados({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ data: params.data, top: params.top, horizonte: params.horizonte })
        });
        const data = await response.json();
        alvo.innerHTML = renderMaquinaTempoRadar(data);
    } catch (error) {
        console.error('Erro no radar temporal:', error);
        alvo.innerHTML = '<div class="error-simple">Falha controlada ao executar radar temporal.</div>';
    }
}

function renderValuationModelos(modelos) {
    const lista = modelos?.modelos || [];
    if (!lista.length) return '<div class="audit-empty">Modelos de valuation nao disponiveis.</div>';
    return lista.map(modelo => `
        <div class="machine-model-row">
            <strong>${escapeHtml(modelo.modelo || 'MODELO')}</strong>
            <span>Preco justo: ${moeda(modelo.preco_justo)}</span>
            <span>Margem: ${percentual(modelo.margem_pct, 1)}</span>
            <small>${escapeHtml(modelo.motivo || '')}</small>
        </div>
    `).join('');
}

function renderMaquinaTempoTicker(data) {
    const resultado = data.resultado || {};
    const avaliacao = resultado.avaliacao || {};
    const modelos = resultado.valuation_modelos || {};
    const valido = data.validade_institucional === true;
    return `
        <details class="audit-panel machine-detail" open>
            <summary>${escapeHtml(data.ticker || 'Ativo')} em ${escapeHtml(data.data_referencia || 'data historica')}</summary>
            <div class="audit-note">${escapeHtml(data.look_ahead_bias || 'Sem leitura de look-ahead informada.')}</div>
            <div class="audit-grid">
                <div><span>Status</span><strong>${escapeHtml(resultado.status || data.status || 'Nao informado')}</strong></div>
                <div><span>Snapshot valido</span><strong>${valido ? 'Sim' : 'Nao'}</strong></div>
                <div><span>Snapshot usado</span><strong>${escapeHtml(textoSeguro(resultado.snapshot_usado))}</strong></div>
                <div><span>Decisao historica</span><strong>${escapeHtml(textoSeguro(resultado.decisao))}</strong></div>
                <div><span>Preco entrada</span><strong>${moeda(resultado.preco_entrada)}</strong></div>
                <div><span>Preco avaliacao</span><strong>${moeda(resultado.preco_saida)}</strong></div>
                <div><span>Retorno total</span><strong>${percentual(resultado.rentabilidade_total_pct, 2)}</strong></div>
                <div><span>Acerto</span><strong>${avaliacao.acerto === undefined ? 'Nao avaliado' : avaliacao.acerto ? 'Sim' : 'Nao'}</strong></div>
            </div>
            <div class="audit-blocks"><strong>Motivo:</strong> ${escapeHtml(resultado.motivo || resultado.motivo_validade || data.mensagem || 'Nao informado')}</div>
            <div class="machine-models">${renderValuationModelos(modelos)}</div>
        </details>
    `;
}

function renderMaquinaTempoRadar(data) {
    const ranking = data.ranking || [];
    const avaliacoes = data.avaliacoes || [];
    return `
        <details class="audit-panel machine-detail" open>
            <summary>Radar temporal ${escapeHtml(data.data_referencia || '')} - Top ${escapeHtml(textoSeguro(data.top, 5))}</summary>
            <div class="audit-note">${escapeHtml(data.look_ahead_bias || 'Ranking temporal usa snapshots historicos.')}</div>
            <div class="machine-scoreline">
                <div><span>Avaliaveis</span><strong>${escapeHtml(textoSeguro(data.avaliaveis, 0))}</strong></div>
                <div><span>Acertos</span><strong>${escapeHtml(textoSeguro(data.acertos, 0))}</strong></div>
                <div><span>Taxa de acerto</span><strong>${percentual(data.taxa_acerto_pct, 2)}</strong></div>
                <div><span>Candidatos validos</span><strong>${escapeHtml(textoSeguro(data.candidatos_validos, 0))}</strong></div>
            </div>
            <div class="history-list">
                ${ranking.length ? ranking.map((item, idx) => `
                    <article class="history-row">
                        <div class="history-row-main">
                            <strong>${idx + 1}. ${escapeHtml(item.ticker)}</strong>
                            <span>${escapeHtml(item.decisao || 'INDEFINIDA')}</span>
                            <small>Margem composta: ${percentual((item.margem_composta_conservadora || 0) * 100, 2)}</small>
                        </div>
                        <div class="history-row-audit">
                            <span>${escapeHtml(item.motivo || 'Sem motivo informado')}</span>
                            <span>Snapshot: ${escapeHtml(textoSeguro(item.snapshot_usado))}</span>
                        </div>
                        <div class="history-actions"><button class="btn-mini" data-mt-ativo="${escapeHtml(item.ticker)}">Ver ativo</button></div>
                    </article>
                `).join('') : '<div class="audit-empty">Sem ranking temporal. Gere snapshots historicos para essa data.</div>'}
            </div>
            <div class="audit-blocks"><strong>Avaliacoes:</strong> ${escapeHtml(String(avaliacoes.length))} resultado(s) calculado(s).</div>
        </details>
    `;
}

function salvarUltimoAlertaAssistenteId(id) {
    if (!id) return;
    localStorage.setItem('fiia_alertas_ultimo_id', String(id));
    localStorage.setItem('fiia_ultimo_alerta_id', String(id));
}

function atualizarBadgeAlertas(qtd) {
    const badges = [document.getElementById('assistenteAlertasBadge'), document.getElementById('alertasNovosBadge')].filter(Boolean);
    if (!badges.length) return;
    const atual = parseInt(badges[0].textContent || '0', 10) || 0;
    const total = Math.min(99, atual + Math.max(0, qtd || 0));
    badges.forEach((badge) => {
        badge.textContent = String(total);
        badge.classList.toggle('hidden', total === 0);
    });
}

function mostrarToastAlerta(alerta) {
    let container = document.getElementById('toastAlertasAssistente');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastAlertasAssistente';
        container.className = 'toast-stack';
        document.body.appendChild(container);
    }
    const toast = document.createElement('button');
    toast.type = 'button';
    toast.className = 'alert-toast';
    toast.innerHTML = `<strong>${escapeHtml(alerta.ticker || 'FIIA')}</strong><span>${escapeHtml(alerta.mensagem || alerta.tipo || 'Novo alerta')}</span>`;
    toast.addEventListener('click', () => {
        carregarAlertasAssistente();
        toast.remove();
    });
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 9000);
}

async function consultarAlertasNovos() {
    if (!obterApiKey()) return;
    try {
        const desdeId = ultimoAlertaAssistenteId();
        const response = await fetch(`/api/assistente/alertas/novos?desde_id=${encodeURIComponent(desdeId)}`, { headers: headersAutenticados() });
        if (!response.ok) return;
        const data = await response.json();
        const alertas = data.alertas || [];
        if (!alertas.length) {
            salvarUltimoAlertaAssistenteId(data.ultimo_id || desdeId);
            return;
        }
        alertas.slice(-3).forEach(mostrarToastAlerta);
        atualizarBadgeAlertas(alertas.length);
        salvarUltimoAlertaAssistenteId(data.ultimo_id || alertas[alertas.length - 1]?.id);
    } catch (error) {
        console.error('Erro ao consultar novos alertas:', error);
    }
}

async function consultarNovosAlertasAssistente() {
    return consultarAlertasNovos();
}

async function marcarAlertasAssistenteComoVistos() {
    if (!obterApiKey()) return;
    try {
        const desdeId = ultimoAlertaAssistenteId();
        const response = await fetch(`/api/assistente/alertas/novos?desde_id=${encodeURIComponent(desdeId)}&limite=100`, { headers: headersAutenticados() });
        if (!response.ok) return;
        const data = await response.json();
        salvarUltimoAlertaAssistenteId(data.ultimo_id || desdeId);
    } catch (error) {
        console.error('Erro ao marcar alertas como vistos:', error);
    }
}

function iniciarMonitorAlertasAssistente() {
    consultarAlertasNovos();
    window.setInterval(consultarAlertasNovos, ASSISTENTE_ALERTAS_POLL_MS);
}

function iniciarPollingAlertasNovos() {
    iniciarMonitorAlertasAssistente();
}

async function carregarAlertasAssistente() {
    const alvo = document.getElementById('assistenteResumo');
    if (!alvo) return;
    if (!obterApiKey()) {
        alvo.innerHTML = '<div class="audit-blocks">Configure fiia_api_key para consultar alertas.</div>';
        return;
    }
    alvo.innerHTML = '<div class="loading-simple">Consultando alertas...</div>';
    try {
        const response = await fetch('/api/assistente/alertas', { headers: headersAutenticados() });
        const data = await response.json();
        const alertas = data.alertas || [];
        const badge = document.getElementById('assistenteAlertasBadge');
        if (badge) {
            badge.textContent = '0';
            badge.classList.add('hidden');
        }
        marcarAlertasAssistenteComoVistos();
        if (!alertas.length) {
            alvo.innerHTML = '<div class="audit-empty">Sem alertas operacionais agora.</div>';
            return;
        }
        alvo.innerHTML = alertas.map(alerta => `
            <article class="history-row">
                <div class="history-row-main">
                    <strong>${escapeHtml(alerta.ticker)}</strong>
                    <span>${escapeHtml(alerta.tipo)}</span>
                    <small>${escapeHtml(alerta.severidade)}</small>
                </div>
                <div class="history-row-audit"><span>${escapeHtml(alerta.mensagem)}</span></div>
            </article>
        `).join('');
    } catch (error) {
        console.error('Erro ao consultar alertas:', error);
        alvo.innerHTML = '<div class="error-simple">Falha controlada ao consultar alertas.</div>';
    }
}

async function carregarRebalanceamento() {
    const alvo = document.getElementById('assistenteResumo');
    if (!alvo) return;
    if (!obterApiKey()) {
        alvo.innerHTML = '<div class="audit-blocks">Configure fiia_api_key para consultar rebalanceamento.</div>';
        return;
    }
    alvo.innerHTML = '<div class="loading-simple">Calculando rebalanceamento...</div>';
    try {
        const response = await fetch('/api/assistente/rebalanceamento', { headers: headersAutenticados() });
        const data = await response.json();
        const sugestoes = data.sugestoes || [];
        if (!sugestoes.length) {
            alvo.innerHTML = '<div class="audit-empty">Sem posicoes para rebalancear.</div>';
            return;
        }
        alvo.innerHTML = sugestoes.map(item => `
            <article class="history-row">
                <div class="history-row-main">
                    <strong>${escapeHtml(item.ticker)}</strong>
                    <span>${escapeHtml(item.politica?.acao_carteira || 'MANTER')}</span>
                    <small>${percentual((item.percentual_atual || 0) * 100, 1)} da carteira</small>
                </div>
                <div class="history-row-audit">
                    <span>Valor: ${moeda(item.valor_atual)}</span>
                    <span>Sugerido: ${percentual((item.politica?.percentual_sugerido || 0) * 100, 1)}</span>
                </div>
            </article>
        `).join('');
    } catch (error) {
        console.error('Erro ao consultar rebalanceamento:', error);
        alvo.innerHTML = '<div class="error-simple">Falha controlada ao consultar rebalanceamento.</div>';
    }
}

function obterAlvoDetalheFundo(anchorEl) {
    const card = anchorEl?.closest?.('.fii-card');
    if (!card) {
        const detalheGlobal = document.getElementById('assistenteDetalhe');
        detalheGlobal?.classList.remove('hidden');
        return detalheGlobal;
    }

    document.querySelectorAll('.inline-fund-detail').forEach((painel) => {
        if (!card.contains(painel)) painel.remove();
    });

    let detalhe = card.querySelector('.inline-fund-detail');
    if (!detalhe) {
        detalhe = document.createElement('div');
        detalhe.className = 'inline-fund-detail history-detail';
        const actions = card.querySelector('.card-actions');
        if (actions?.nextSibling) {
            card.insertBefore(detalhe, actions.nextSibling);
        } else {
            card.appendChild(detalhe);
        }
    }
    detalhe.classList.remove('hidden');
    return detalhe;
}

async function consultarDetalheFundo(ticker, anchorEl = null) {
    const detalhe = obterAlvoDetalheFundo(anchorEl);
    if (!detalhe) return;
    detalhe.classList.remove('hidden');
    detalhe.innerHTML = `<div class="loading-simple">Consultando detalhe de ${escapeHtml(ticker)}...</div>`;
    try {
        const [detalheResp, evolucaoResp] = await Promise.all([
            fetch(`/api/assistente/fundos/${encodeURIComponent(ticker)}`, { headers: headersAutenticados() }),
            fetch(`/api/assistente/fundos/${encodeURIComponent(ticker)}/evolucao`, { headers: headersAutenticados() })
        ]);
        const data = await detalheResp.json();
        const evolucao = await evolucaoResp.json();
        detalhe.innerHTML = renderDetalheFundo(data, evolucao);
        inicializarExportacoesDetalhe(detalhe, data.ticker || ticker);
    } catch (error) {
        console.error('Erro ao consultar detalhe do fundo:', error);
        detalhe.innerHTML = '<div class="error-simple">Falha controlada ao consultar detalhe do fundo.</div>';
    }
}

function inicializarExportacoesDetalhe(container, ticker) {
    container.querySelectorAll('[data-export-fundo]').forEach((btn) => {
        btn.addEventListener('click', () => baixarRelatorioFundo(ticker, btn.dataset.exportFundo || 'txt'));
    });
}

async function baixarRelatorioFundo(ticker, formato) {
    const apiKey = obterOuSolicitarApiKey('exportar relatorio');
    if (!apiKey) return;

    try {
        const response = await fetch(`/api/assistente/fundos/${encodeURIComponent(ticker)}/exportar?formato=${encodeURIComponent(formato)}`, {
            headers: headersAutenticados()
        });
        if (!response.ok) {
            throw new Error(`Exportacao retornou HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `fiia_${ticker}.${formato === 'pdf' ? 'pdf' : 'txt'}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Erro ao exportar relatorio:', error);
        alert(`Erro ao exportar relatorio: ${error.message || 'falha controlada.'}`);
    }
}

function renderDetalheFundo(data, evolucao) {
    const ind = data.indicador || {};
    const tri = data.trimestral || {};
    const div = data.ultimo_dividendo || {};
    const fnet = data.fnet || {};
    const dec = data.decisao || {};
    const ticker = data.ticker || ind.ticker || dec.ticker || '---';
    return `
        <details class="audit-panel history-detail-panel" open>
            <summary>Detalhe diario - ${escapeHtml(ticker)}</summary>
            <div class="audit-grid">
                <div><span>Decisao</span><strong>${escapeHtml(dec.decisao || 'Nao informado')}</strong></div>
                <div><span>Evolucao</span><strong>${escapeHtml(evolucao.leitura || 'Nao informado')}</strong></div>
                <div><span>Preco</span><strong>${moeda(ind.preco)}</strong></div>
                <div><span>P/VP</span><strong>${escapeHtml(textoSeguro(ind.pvp))}</strong></div>
                <div><span>Ultimo dividendo</span><strong>${escapeHtml(textoSeguro(div.valor))} em ${escapeHtml(textoSeguro(div.data_pagamento, 'N/D'))}</strong></div>
                <div><span>Vacancia CVM</span><strong>${escapeHtml(textoSeguro(tri.vacancia_media_ponderada))}</strong></div>
                <div><span>Imoveis</span><strong>${escapeHtml(textoSeguro(tri.quantidade_imoveis))}</strong></div>
                <div><span>FNET docs</span><strong>${escapeHtml(textoSeguro(fnet.quantidade_documentos, 0))}</strong></div>
            </div>
            <div class="audit-blocks"><strong>FNET tipos:</strong> ${renderListaRotulos(fnet.tipos || [])}</div>
            <div class="audit-blocks"><strong>Motivo:</strong> ${escapeHtml(dec.motivo || 'Nao informado')}</div>
            <div class="history-actions">
                <button class="btn-mini" data-export-fundo="txt">Exportar texto</button>
                <button class="btn-mini" data-export-fundo="pdf">Exportar PDF</button>
            </div>
        </details>
    `;
}

async function carregarHistoricoDecisoes() {
    const lista = document.getElementById('historicoLista');
    if (!lista) return;
    const apiKey = obterApiKey();
    if (!apiKey) {
        lista.innerHTML = `
            <div class="audit-blocks">
                Configure <strong>fiia_api_key</strong> no localStorage para consultar historico auditavel.
                <button id="btnConfigApiKeyHistorico" class="btn-mini">Configurar chave</button>
            </div>
        `;
        document.getElementById('btnConfigApiKeyHistorico')?.addEventListener('click', () => {
            if (obterOuSolicitarApiKey('consultar historico auditavel')) carregarHistoricoDecisoes();
        });
        return;
    }
    lista.innerHTML = '<div class="loading-simple">⌛ Consultando histórico sem replay...</div>';
    try {
        const response = await fetch('/api/auditoria/decisoes/auditaveis?limite=30', { headers: headersAutenticados() });
        const data = await response.json();
        const decisoes = data.decisoes || [];
        if (!decisoes.length) {
            lista.innerHTML = '<div class="audit-empty">Nenhuma decisão auditável encontrada.</div>';
            return;
        }
        lista.innerHTML = decisoes.map(renderLinhaHistorico).join('');
        lista.querySelectorAll('[data-decisao-detalhe]').forEach((btn) => {
            btn.addEventListener('click', () => consultarDetalheHistorico(btn.dataset.decisaoDetalhe, false, btn));
        });
        lista.querySelectorAll('[data-decisao-replay]').forEach((btn) => {
            btn.addEventListener('click', () => consultarDetalheHistorico(btn.dataset.decisaoReplay, true, btn));
        });
    } catch (error) {
        console.error('Erro ao consultar histórico:', error);
        lista.innerHTML = '<div class="error-simple">❌ Falha controlada ao consultar histórico.</div>';
    }
}

function renderLinhaHistorico(item) {
    const id = item.id || item.decisao_id;
    return `
        <article class="history-row-wrap" data-decisao-id="${escapeHtml(id)}">
            <div class="history-row">
                <div class="history-row-main">
                    <strong>${escapeHtml(item.ticker || '---')}</strong>
                    <span>${escapeHtml(item.decisao || '---')}</span>
                    <small>${escapeHtml(item.data_decisao || item.criado_em || 'Data não informada')}</small>
                </div>
                <div class="history-row-audit">
                    <span title="${escapeHtml(item.payload_hash || '')}">Hash: ${escapeHtml(resumirHash(item.payload_hash))}</span>
                    <span>Hash válido: ${item.hash_valido === true ? 'Sim' : item.hash_valido === false ? 'Não' : 'Não informado'}</span>
                </div>
                <div class="history-actions">
                    <button class="btn-mini" data-decisao-detalhe="${escapeHtml(id)}">Ver auditoria</button>
                    <button class="btn-mini replay" data-decisao-replay="${escapeHtml(id)}">Executar replay</button>
                </div>
            </div>
            <div class="history-row-inline-detail hidden"></div>
        </article>
    `;
}

async function consultarDetalheHistorico(decisaoId, replayExplicito, triggerBtn) {
    // Encontra o article pai do botão clicado
    const wrap = triggerBtn?.closest('[data-decisao-id]');
    const inlineDetalhe = wrap?.querySelector('.history-row-inline-detail');

    // Se tem painel inline, fecha qualquer outro aberto antes
    document.querySelectorAll('.history-row-inline-detail').forEach(el => {
        if (el !== inlineDetalhe) {
            el.classList.add('hidden');
            el.innerHTML = '';
        }
    });

    // Toggle: se já está aberto e é o mesmo detalhe (sem ser replay), fecha
    if (inlineDetalhe && !inlineDetalhe.classList.contains('hidden') && !replayExplicito) {
        inlineDetalhe.classList.add('hidden');
        inlineDetalhe.innerHTML = '';
        return;
    }

    const alvo = inlineDetalhe || document.getElementById('historicoDetalhe');
    if (!alvo) return;
    alvo.classList.remove('hidden');
    alvo.innerHTML = `<div class="loading-simple">⌛ ${replayExplicito ? 'Executando replay explícito' : 'Consultando auditoria'}...</div>`;

    // Scroll suave para o detalhe
    alvo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    try {
        const url = `/api/auditoria/decisoes/${encodeURIComponent(decisaoId)}/auditavel?incluir_payload=true&replay=${replayExplicito ? 'true' : 'false'}`;
        const response = await fetch(url, { headers: headersAutenticados() });
        const data = await response.json();
        alvo.innerHTML = renderDetalheHistorico(data, replayExplicito);
    } catch (error) {
        console.error('Erro ao consultar detalhe/replay:', error);
        alvo.innerHTML = '<div class="error-simple">❌ Falha controlada ao consultar detalhe da decisão.</div>';
    }
}

function renderDetalheHistorico(data, replayExplicito) {
    const decisao = data.decisao || {};
    const auditoria = data.auditoria || {};
    const replay = data.replay || { executado: false };
    const payload = data.payload || {};
    const gates = normalizarGatesDetalhes(payload.gates_detalhes || decisao.gates_detalhes || {});
    return `
        <details class="audit-panel history-detail-panel" open>
            <summary>Detalhe auditável da decisão #${escapeHtml(decisao.id || data.decisao_id || '---')}</summary>
            <div class="audit-note">Replay solicitado: <strong>${replayExplicito ? 'Sim' : 'Não'}</strong>. Consulta padrão não reexecuta motor nem scraping.</div>
            <div class="audit-grid">
                <div><span>Ticker</span><strong>${escapeHtml(decisao.ticker || payload.ticker || '---')}</strong></div>
                <div><span>Decisão</span><strong>${escapeHtml(decisao.decisao || payload.decisao || '---')}</strong></div>
                <div><span>Hash salvo</span><strong title="${escapeHtml(auditoria.payload_hash_salvo || decisao.payload_hash || '')}">${escapeHtml(resumirHash(auditoria.payload_hash_salvo || decisao.payload_hash))}</strong></div>
                <div><span>Hash calculado</span><strong title="${escapeHtml(auditoria.payload_hash_calculado || '')}">${escapeHtml(resumirHash(auditoria.payload_hash_calculado))}</strong></div>
                <div><span>Hash válido</span><strong>${auditoria.hash_valido === true ? 'Sim' : auditoria.hash_valido === false ? 'Não' : 'Não informado'}</strong></div>
                <div><span>Contexto</span><strong>${escapeHtml(auditoria.contexto_versao || decisao.contexto_versao || 'Não informado')}</strong></div>
                <div><span>Motor</span><strong>${escapeHtml(auditoria.versao_motor || decisao.versao_motor || 'Não informado')}</strong></div>
                <div><span>Replay</span><strong>${replay.executado ? (replay.divergencia_replay ? 'Divergente' : 'Conferido') : 'Não executado'}</strong></div>
                <div><span>Fonte replay</span><strong>${escapeHtml(replay.fonte_replay || 'Não informado')}</strong></div>
            </div>
            <div class="audit-gates-title">gates_detalhes do payload salvo</div>
            <div class="audit-gates-list">${renderGateDetalhes(gates)}</div>
        </details>
    `;
}

function mockAtivo() {
    return {
        ticker: 'SNAG11', segmento: 'FIAGRO', decisao: 'COMPRAR', confianca: 'ALTA',
        preco_atual: 10.61, preco_justo: 11.08, preco_entrada: 10.50, margem: 4.4,
        pvp: 0.95, dy_12m_pct: 14.57, pct_recorrente: 100,
        trilha_gates: ['G0:APROVADO_DADOS', 'G1:APROVADO_ELEG', 'G2:APROVADO_ESTR'],
        gates_detalhes: { '0': { gate: 0, status: 'APROVADO_DADOS', aprovado: true, fontes: ['contexto'], metricas: { semaforo: 'VERDE' }, motivos: ['Dados mínimos presentes.'], penalidades: [] } },
        payload_hash: 'demo-hash', contexto_versao: 'asset-context-v1.3', versao_motor: 'demo', score_ia: 9,
        motivo: 'Exemplo de card com explicabilidade e auditoria.', alertas: []
    };
}

function escapeHtml(valor) {
    return textoSeguro(valor, '').replace(/[&<>"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
}

function asArray(valor) {
    if (!valor) return [];
    if (Array.isArray(valor)) return valor;
    if (typeof valor === 'string') {
        try {
            const parsed = JSON.parse(valor);
            return Array.isArray(parsed) ? parsed : [parsed];
        } catch (e) { return [valor]; }
    }
    return [valor];
}

function asObject(valor) {
    if (!valor) return {};
    if (typeof valor === 'object' && !Array.isArray(valor)) return valor;
    if (typeof valor === 'string') {
        try {
            const parsed = JSON.parse(valor);
            return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
        } catch (e) { return {}; }
    }
    return {};
}

function textoSeguro(valor, fallback = 'Não informado') {
    if (valor === null || valor === undefined || valor === '') return fallback;
    return String(valor);
}

function numeroSeguro(valor, fallback = 0) {
    const n = Number(valor);
    return Number.isFinite(n) ? n : fallback;
}

function moeda(valor) {
    const n = Number(valor);
    if (!Number.isFinite(n) || n <= 0) return '---';
    return `R$ ${n.toFixed(2)}`;
}

function percentual(valor, casas = 1) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return '---';
    return `${n > 0 ? '+' : ''}${n.toFixed(casas)}%`;
}

function normalizarClasse(valor) {
    return textoSeguro(valor, 'indefinido').toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '_');
}

function resumirHash(hash) {
    const h = textoSeguro(hash, 'Não informado');
    return h.length > 18 ? `${h.slice(0, 12)}…${h.slice(-6)}` : h;
}

function renderListaRotulos(itens, classe = 'audit-chip') {
    const lista = asArray(itens).filter(Boolean).map(item => escapeHtml(textoSeguro(item)));
    if (!lista.length) return '<span class="audit-muted">Não informado</span>';
    return lista.map(item => `<span class="${classe}">${item}</span>`).join('');
}

function normalizarGatesDetalhes(raw) {
    const obj = asObject(raw);
    return Object.keys(obj).sort((a, b) => Number(a) - Number(b)).map((chave) => {
        const gate = obj[chave] || {};
        const metricas = asObject(gate.metricas);
        const status = textoSeguro(gate.status, 'SEM_STATUS');
        const aprovado = gate.aprovado === true || status.toUpperCase().includes('APROVADO');
        const eliminado = gate.eliminado === true || status.toUpperCase().includes('ELIMINADO') || status.toUpperCase().includes('BLOQUE');
        return {
            gate: gate.gate ?? chave,
            status,
            aprovado,
            eliminado,
            motivos: asArray(gate.motivos || gate.motivo).map(item => textoSeguro(item)),
            fontes: asArray(gate.fontes).map(item => textoSeguro(item)),
            penalidades: asArray(gate.penalidades).map(item => textoSeguro(item)),
            metricas
        };
    });
}

function normalizarAuditoria(fii, v) {
    const auditoria = asObject(fii.auditoria || v.auditoria);
    const replay = asObject(fii.replay || v.replay);
    const payload = asObject(fii.payload || v.payload);
    return {
        payload_hash: fii.payload_hash || v.payload_hash || auditoria.payload_hash_salvo || payload.payload_hash,
        hash_valido: auditoria.hash_valido,
        contexto_versao: fii.contexto_versao || v.contexto_versao || auditoria.contexto_versao || payload.contexto_versao,
        versao_motor: fii.versao_motor || v.versao_motor || auditoria.versao_motor || payload.versao_motor || payload.versao_modelo || v.versao_modelo,
        fonte_patrimonial: fii.fonte_patrimonial || v.fonte_patrimonial || payload.fonte_patrimonial,
        score_confianca_dados: fii.score_confianca_dados ?? v.score_confianca_dados ?? payload.score_confianca_dados,
        nivel_uso_dados: fii.nivel_uso_dados || v.nivel_uso_dados || payload.nivel_uso_dados,
        permitir_decisao: fii.permitir_decisao ?? v.permitir_decisao ?? payload.permitir_decisao,
        gate_parada: fii.gate_parada ?? v.gate_parada ?? payload.gate_parada,
        motivo_bloqueio: fii.motivo_bloqueio || v.motivo_bloqueio || payload.motivo_bloqueio,
        campos_ausentes: asArray(fii.campos_ausentes || v.campos_ausentes || payload.campos_ausentes),
        campos_vencidos: asArray(fii.campos_vencidos || v.campos_vencidos || payload.campos_vencidos),
        fontes_falharam: asArray(fii.fontes_falharam || v.fontes_falharam || payload.fontes_falharam),
        gates_detalhes: normalizarGatesDetalhes(fii.gates_detalhes || v.gates_detalhes || payload.gates_detalhes),
        replay
    };
}

function normalizarFii(fii) {
    const v = fii.veredito || {};
    const ind = fii.indicadores || {};
    let trilha_gates = asArray(fii.trilha_gates || v.trilha_gates || []);
    let dy_12m_pct = fii.dy_12m_pct ?? v.dy_12m_pct ?? ((v.dy_12m || ind.dy_12m || 0) * 100);
    if (dy_12m_pct > 0 && dy_12m_pct < 1.0) dy_12m_pct *= 100;
    const auditoria = normalizarAuditoria(fii, v);
    return {
        ticker: fii.ticker || v.ticker || '---', segmento: fii.segmento || v.segmento || 'FII',
        decisao: fii.decisao || v.decisao || 'MONITORAR', confianca: fii.confianca || v.confianca || 'MEDIA',
        preco_atual: fii.preco_atual ?? v.preco_atual ?? v.preco_na_decisao ?? 0.0,
        preco_justo: fii.preco_justo ?? v.preco_justo ?? 0.0,
        preco_entrada: fii.preco_entrada ?? v.preco_entrada ?? v.preco_teto ?? 0.0,
        margem: fii.margem ?? v.margem ?? v.margem_seguranca ?? 0.0,
        pvp: fii.pvp ?? v.pvp ?? ind.pvp ?? 1.0,
        dy_12m_pct, pct_recorrente: fii.pct_recorrente ?? v.pct_recorrente ?? 100.0,
        trilha_gates: trilha_gates.length ? trilha_gates : ['G0:DADOS_OK', 'G1:ELEGIVEL'],
        score_ia: fii.score_ia ?? v.score_ia ?? 7.0, motivo: fii.motivo || v.motivo || 'Ativo em monitoramento.',
        alertas: asArray(fii.alertas || v.alertas || []), quantidade: fii.quantidade ?? 0,
        preco_medio: fii.preco_medio ?? 0.0, custo_total: fii.custo_total ?? 0.0,
        revisao: fii.revisao || v.revisao || 'Próximo Radar', auditoria,
        zonas_entrada: asObject(fii.zonas_entrada || v.zonas_entrada || null),
        dimensionamento: asObject(fii.dimensionamento || v.dimensionamento || null),
    };
}

function renderResumoExplicabilidade(fii) {
    const auditoria = fii.auditoria;
    const bloqueado = auditoria.permitir_decisao === false || normalizarClasse(fii.decisao).includes('bloqueado');
    return `
        <section class="explain-summary ${bloqueado ? 'explain-blocked' : ''}">
            <div class="explain-item"><span>Status operacional</span><strong>${bloqueado ? 'Bloqueado / cautela' : 'Exibível'}</strong></div>
            <div class="explain-item"><span>Gate de parada</span><strong>${escapeHtml(textoSeguro(auditoria.gate_parada))}</strong></div>
            <div class="explain-item"><span>Fonte principal</span><strong>${escapeHtml(textoSeguro(auditoria.fonte_patrimonial, 'Não informada'))}</strong></div>
            <div class="explain-item"><span>Score dados</span><strong>${escapeHtml(textoSeguro(auditoria.score_confianca_dados))}</strong></div>
            ${bloqueado ? `<div class="explain-reason"><strong>Motivo:</strong> ${escapeHtml(textoSeguro(auditoria.motivo_bloqueio, 'Sem motivo específico informado.'))}</div>` : ''}
        </section>
    `;
}

function renderGateDetalhes(gates) {
    if (!gates || gates.length === 0) {
        return '<div class="audit-empty">Detalhamento de gates não informado. O card permanece visível para auditoria.</div>';
    }
    return gates.map(gate => {
        const metricas = Object.keys(gate.metricas || {}).slice(0, 6).map(k => `<span class="audit-metric"><b>${escapeHtml(k)}</b>: ${escapeHtml(gate.metricas[k])}</span>`).join('');
        const estadoClasse = gate.eliminado ? 'gate-eliminado' : gate.aprovado ? 'gate-aprovado' : 'gate-neutro';
        return `
            <div class="audit-gate ${estadoClasse}">
                <div class="audit-gate-head"><strong>Gate ${escapeHtml(gate.gate)}</strong><span>${escapeHtml(gate.status)}</span></div>
                <div class="audit-gate-body">
                    <div><em>Motivos</em>${renderListaRotulos(gate.motivos)}</div>
                    <div><em>Fontes</em>${renderListaRotulos(gate.fontes)}</div>
                    ${metricas ? `<div class="audit-metrics"><em>Métricas</em>${metricas}</div>` : '<div><em>Métricas</em><span class="audit-muted">Não informado</span></div>'}
                    <div><em>Penalidades</em>${renderListaRotulos(gate.penalidades, 'audit-chip penalty')}</div>
                </div>
            </div>
        `;
    }).join('');
}

function renderAuditoria(auditoria) {
    const bloqueios = [...auditoria.campos_ausentes, ...auditoria.campos_vencidos, ...auditoria.fontes_falharam];
    const replay = auditoria.replay || {};
    return `
        <details class="audit-panel">
            <summary>Auditoria e explicabilidade</summary>
            <div class="audit-note">Hash e payload auditável são apenas exibidos. O frontend não recalcula integridade.</div>
            <div class="audit-grid">
                <div><span>Hash salvo</span><strong title="${escapeHtml(textoSeguro(auditoria.payload_hash))}">${escapeHtml(resumirHash(auditoria.payload_hash))}</strong></div>
                <div><span>Hash válido</span><strong>${auditoria.hash_valido === undefined ? 'Não informado' : auditoria.hash_valido ? 'Sim' : 'Não'}</strong></div>
                <div><span>Contexto</span><strong>${escapeHtml(textoSeguro(auditoria.contexto_versao))}</strong></div>
                <div><span>Motor</span><strong>${escapeHtml(textoSeguro(auditoria.versao_motor))}</strong></div>
                <div><span>Fonte patrimonial</span><strong>${escapeHtml(textoSeguro(auditoria.fonte_patrimonial))}</strong></div>
                <div><span>Confiança dados</span><strong>${escapeHtml(textoSeguro(auditoria.score_confianca_dados))} / ${escapeHtml(textoSeguro(auditoria.nivel_uso_dados))}</strong></div>
                <div><span>Permitir decisão</span><strong>${auditoria.permitir_decisao === false ? 'Não' : auditoria.permitir_decisao === true ? 'Sim' : 'Não informado'}</strong></div>
                <div><span>Replay</span><strong>${replay.executado ? (replay.divergencia_replay ? 'Divergente' : 'Conferido') : 'Não executado'}</strong></div>
            </div>
            ${bloqueios.length ? `<div class="audit-blocks"><strong>Bloqueios/falhas:</strong><div class="audit-chip-row">${renderListaRotulos(bloqueios, 'audit-chip danger')}</div></div>` : ''}
            <div class="audit-gates-title">gates_detalhes</div>
            <div class="audit-gates-list">${renderGateDetalhes(auditoria.gates_detalhes)}</div>
        </details>
    `;
}

function renderZonasEntrada(zonas) {
    if (!zonas || !zonas.calculavel) return '';
    const zona = zonas.zona_atual || 'ESPERA';
    const classeZona = { 'FORTE': 'zona-forte', 'PARCIAL': 'zona-parcial', 'ESPERA': 'zona-espera' }[zona] || 'zona-espera';
    return `
        <div class="zonas-card">
            <div class="zonas-title">Zonas de Entrada</div>
            <div class="zonas-grid">
                <div class="zona-item zona-forte-ref"><span>Forte</span><strong>${moeda(zonas.zona_forte)}</strong></div>
                <div class="zona-item zona-parcial-ref"><span>Parcial</span><strong>${moeda(zonas.zona_parcial)}</strong></div>
                <div class="zona-item zona-espera-ref"><span>Espera</span><strong>${moeda(zonas.zona_espera)}</strong></div>
            </div>
            <div class="zona-badge ${classeZona}">Zona atual: ${escapeHtml(zona)}</div>
        </div>
    `;
}

function renderDimensionamento(dim) {
    if (!dim || dim.pct_carteira === undefined) return '';
    return `
        <div class="dim-card">
            <div class="dim-title">Dimensionamento Sugerido</div>
            <div class="dim-grid">
                <div><span>% carteira</span><strong>${numeroSeguro(dim.pct_carteira).toFixed(1)}%</strong></div>
                <div><span>Ref. R$ 10k</span><strong>${moeda(dim.valor_ref_10k)}</strong></div>
                <div><span>Lote mínimo</span><strong>${escapeHtml(textoSeguro(dim.lote_minimo, '---'))} cotas</strong></div>
            </div>
        </div>
    `;
}

function renderResults(oportunidades, targetId = 'results', isPortfolio = false) {
    const grid = document.getElementById(targetId);
    if (!grid) return;
    grid.innerHTML = '';
    if (!oportunidades || oportunidades.length === 0) {
        grid.innerHTML = '<div class="empty-state-container glass-card"><h3>Nenhum ativo encontrado</h3><p>Não há cards para exibir neste momento.</p></div>';
        return;
    }
    oportunidades.forEach((raw) => {
        const fii = normalizarFii(raw || {});
        const bloqueado = fii.auditoria.permitir_decisao === false || normalizarClasse(fii.decisao).includes('bloqueado');
        const card = document.createElement('div');
        card.className = `fii-card ${bloqueado ? 'card-bloqueado' : ''}`;
        card.innerHTML = `
            <div class="card-header"><div class="ticker-box"><span class="ticker-symbol">${escapeHtml(fii.ticker)}</span><span class="segment-badge">${escapeHtml(fii.segmento)}</span></div><div class="decision-badge ${normalizarClasse(fii.decisao)}">${escapeHtml(fii.decisao.replace('_', ' '))}</div></div>
            <div class="confidence-bar"><span class="label">Confiança:</span><span class="confidence-value ${normalizarClasse(fii.confianca)}">${escapeHtml(fii.confianca)}</span></div>
            ${renderResumoExplicabilidade(fii)}
            ${isPortfolio ? `<div class="holding-details-container glass-card"><div class="holding-metric"><span class="label">Minhas Cotas</span><span class="value">${escapeHtml(fii.quantidade)}</span></div><div class="holding-metric"><span class="label">Preço Médio</span><span class="value">${moeda(fii.preco_medio)}</span></div><div class="holding-metric highlight"><span class="label">Total Aplicado</span><span class="value">R$ ${numeroSeguro(fii.custo_total).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span></div></div>` : ''}
            <div class="price-grid"><div class="price-item"><span class="label">Preço Atual</span><span class="value">${moeda(fii.preco_atual)}</span></div><div class="price-item highlight"><span class="label">Preço Justo</span><span class="value">${moeda(fii.preco_justo)}</span></div><div class="price-item"><span class="label">Entrada Ideal</span><span class="value">${moeda(fii.preco_entrada)}</span></div></div>
            ${renderZonasEntrada(fii.zonas_entrada)}
            ${renderDimensionamento(fii.dimensionamento)}
            <div class="metrics-grid"><div class="metric"><span class="label">Margem</span><span class="value ${numeroSeguro(fii.margem) > 0 ? 'pos' : 'neg'}">${percentual(fii.margem)}</span></div><div class="metric"><span class="label">P/VP</span><span class="value">${numeroSeguro(fii.pvp).toFixed(2)}</span></div><div class="metric"><span class="label">DY 12M</span><span class="value">${percentual(fii.dy_12m_pct)}</span></div><div class="metric"><span class="label">Recorrência</span><span class="value">${escapeHtml(textoSeguro(fii.pct_recorrente, '---'))}%</span></div></div>
            <div class="gate-trail"><div class="gate-title">Esteira de Qualidade (8 Gates)</div><div class="gates-container">${fii.trilha_gates.map(gate => `<span class="gate-tag">${escapeHtml(gate)}</span>`).join('')}</div></div>
            <div class="ai-analysis"><div class="ai-header"><span class="ai-icon">🧠</span><span class="ai-label">Inteligência FIIA</span><span class="ai-score">Score: ${escapeHtml(fii.score_ia || '?')}/10</span></div><div class="ai-content">${escapeHtml(fii.motivo || 'Aguardando processamento...')}</div></div>
            ${fii.alertas.length ? `<div class="alerts-box">${fii.alertas.map(alert => `<div class="alert-item">⚠️ ${escapeHtml(alert)}</div>`).join('')}</div>` : ''}
            ${renderAuditoria(fii.auditoria)}
            <div class="card-actions">
                <button class="btn-mini" data-fundo-detalhe="${escapeHtml(fii.ticker)}">Detalhar</button>
                <button class="btn-mini" data-fundo-evolucao="${escapeHtml(fii.ticker)}">Evolucao</button>
            </div>
            <div class="card-footer"><span class="footer-info">Próxima Revisão: ${escapeHtml(fii.revisao)}</span></div>
        `;
        grid.appendChild(card);
    });
    grid.querySelectorAll('[data-fundo-detalhe], [data-fundo-evolucao]').forEach((btn) => {
        btn.addEventListener('click', () => consultarDetalheFundo(btn.dataset.fundoDetalhe || btn.dataset.fundoEvolucao, btn));
    });
}

function inicializarPlayground() {
    const playTabs = document.querySelectorAll('.playground-tab');
    const playUrlInput = document.getElementById('playgroundUrl');
    const sendBtn = document.getElementById('btnSendPlayground');
    const resultBlock = document.getElementById('playgroundResult');
    const statusSpan = document.getElementById('playgroundStatus');
    const timeSpan = document.getElementById('playgroundTime');
    const copyBtn = document.getElementById('btnCopyPlayground');

    // Mapear cliques nas abas do playground
    playTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            playTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            if (playUrlInput) {
                playUrlInput.value = tab.dataset.path;
            }
        });
    });

    // Enviar requisição
    sendBtn?.addEventListener('click', async () => {
        if (!playUrlInput || !resultBlock) return;
        const path = playUrlInput.value.trim();
        if (!path) return;

        resultBlock.innerHTML = '<span class="syntax-comment">// Processando requisição...</span>';
        if (statusSpan) statusSpan.textContent = 'Enviando...';
        if (timeSpan) timeSpan.textContent = '';

        const tStart = performance.now();
        try {
            const response = await fetch(path, {
                headers: headersAutenticados()
            });
            const tEnd = performance.now();
            const elapsed = Math.round(tEnd - tStart);

            if (statusSpan) statusSpan.textContent = `${response.status} ${response.statusText}`;
            if (timeSpan) timeSpan.textContent = `${elapsed}ms`;

            let data;
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                data = await response.json();
                resultBlock.innerHTML = formatarJsonParaPlayground(data);
            } else {
                const text = await response.text();
                try {
                    data = JSON.parse(text);
                    resultBlock.innerHTML = formatarJsonParaPlayground(data);
                } catch {
                    resultBlock.textContent = text;
                }
            }
        } catch (error) {
            const tEnd = performance.now();
            const elapsed = Math.round(tEnd - tStart);
            if (statusSpan) statusSpan.textContent = 'Erro';
            if (timeSpan) timeSpan.textContent = `${elapsed}ms`;
            resultBlock.innerHTML = `<span class="syntax-comment">// Falha ao conectar: ${escapeHtml(error.message)}</span>`;
        }
    });

    // Copiar resposta
    copyBtn?.addEventListener('click', () => {
        if (!resultBlock) return;
        const text = resultBlock.innerText;
        navigator.clipboard.writeText(text).then(() => {
            copyBtn.textContent = 'Copiado!';
            copyBtn.classList.add('copied');
            setTimeout(() => {
                copyBtn.textContent = 'Copiar';
                copyBtn.classList.remove('copied');
            }, 2000);
        });
    });
}

function formatarJsonParaPlayground(jsonObj) {
    const jsonStr = JSON.stringify(jsonObj, null, 2);
    let escaped = jsonStr
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
        
    return escaped.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g, function (match) {
        let cls = 'syntax-num';
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = 'syntax-key';
            } else {
                cls = 'syntax-string';
            }
        } else if (/true|false/.test(match)) {
            cls = 'syntax-accent';
        } else if (/null/.test(match)) {
            cls = 'syntax-comment';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}
