/**
 * app.js - FIIA Intelligence Interface
 * Versão 2.0 - Integração com Motor de Decisão
 */

document.addEventListener('DOMContentLoaded', () => {
    // Mock inicial da carteira com o SNAG11 real do Status Invest
    const mockCarteira = [
        {
            ticker: "SNAG11",
            segmento: "FIAGRO",
            decisao: "COMPRAR",
            confianca: "ALTA",
            preco_atual: 10.61,
            preco_justo: 11.08,
            preco_entrada: 10.50,
            margem: 4.4,
            pvp: 0.95,
            dy_12m_pct: 14.57,
            pct_recorrente: 100,
            trilha_gates: ["G0:APROVADO_DADOS", "G1:APROVADO_ELEG", "G2:APROVADO_ESTR", "G3:APROVADO_RENDA", "G4:APROVADO_PRECO"],
            score_ia: 9,
            motivo: "Excelente FIAGRO sob gestão da SUNO. Com dividendos consistentes de R$ 0,12 mensais, o DY de 14,57% supera confortavelmente o CDI de 14,40%. O ativo está sendo negociado com desconto real de 5% sobre o valor patrimonial (P/VP 0,95). Risco controlado e ótima relação retorno/risco.",
            alertas: []
        }
    ];
    
    // Função para carregar a carteira real do backend
    async function carregarCarteira() {
        const grid = document.getElementById('portfolioGrid');
        grid.innerHTML = '<div class="loading-simple">⌛ Carregando ativos...</div>';
        
        try {
            const response = await fetch('/api/carteira/posicoes');
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
                `;
                const mockContainer = document.createElement('div');
                mockContainer.id = 'demoGrid';
                mockContainer.className = 'results-grid';
                grid.appendChild(mockContainer);
                renderResults(mockCarteira, 'demoGrid', false);
            }
        } catch (error) {
            console.error('Erro ao buscar posições da carteira:', error);
            grid.innerHTML = '<div class="error-simple">❌ Erro ao conectar ao servidor. Exibindo dados de demonstração:</div>';
            const mockContainer = document.createElement('div');
            mockContainer.id = 'demoGrid';
            mockContainer.className = 'results-grid';
            grid.appendChild(mockContainer);
            renderResults(mockCarteira, 'demoGrid', false);
        }
    }
    
    carregarCarteira();

    // Tab Logic
    const btnCarteira = document.getElementById('btnCarteira');
    const btnRadarTab = document.getElementById('btnRadarTab');
    const btnRadarAction = document.getElementById('btnRadar');
    
    const portfolioView = document.getElementById('portfolioView');
    const welcomeView = document.getElementById('welcomeView');
    const resultsView = document.getElementById('results');
    const loadingView = document.getElementById('loading');

    btnCarteira.addEventListener('click', () => {
        btnCarteira.classList.add('active');
        btnRadarTab.classList.remove('active');
        
        portfolioView.classList.remove('hidden');
        welcomeView.classList.add('hidden');
        resultsView.classList.add('hidden');
        loadingView.classList.add('hidden');
        btnRadarAction.classList.add('hidden');
        carregarCarteira();
    });

    btnRadarTab.addEventListener('click', () => {
        btnRadarTab.classList.add('active');
        btnCarteira.classList.remove('active');
        
        portfolioView.classList.add('hidden');
        welcomeView.classList.remove('hidden');
        resultsView.classList.add('hidden');
        btnRadarAction.classList.remove('hidden');
    });

    // Modal Logic
    const btnOpenModal = document.getElementById('btnOpenModal');
    const btnCloseModal = document.getElementById('btnCloseModal');
    const transactionModal = document.getElementById('transactionModal');
    const transactionForm = document.getElementById('transactionForm');

    if (btnOpenModal) {
        btnOpenModal.addEventListener('click', () => {
            transactionModal.classList.remove('hidden');
        });
    }

    if (btnCloseModal) {
        btnCloseModal.addEventListener('click', () => {
            transactionModal.classList.add('hidden');
        });
    }

    window.addEventListener('click', (e) => {
        if (e.target === transactionModal) {
            transactionModal.classList.add('hidden');
        }
    });

    if (transactionForm) {
        transactionForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = transactionForm.querySelector('.btn-submit');
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Gravando...';
            
            const payload = {
                ticker: document.getElementById('txTicker').value.trim().toUpperCase(),
                quantidade: parseFloat(document.getElementById('txQtd').value),
                preco: parseFloat(document.getElementById('txPreco').value),
                segmento: document.getElementById('txSegmento').value || null,
                custos: 0.0,
                origem: "PWA_DASHBOARD"
            };

            try {
                const response = await fetch('/api/carteira/compra', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                
                if (data.status === 'ok') {
                    alert('Transação registrada com sucesso!');
                    transactionForm.reset();
                    transactionModal.classList.add('hidden');
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
});

document.getElementById('btnRadar').addEventListener('click', async () => {
    const welcomeView = document.getElementById('welcomeView');
    const loading = document.getElementById('loading');
    const resultsGrid = document.getElementById('results');
    const btnRadar = document.getElementById('btnRadar');
    
    // UI State: Loading
    welcomeView.classList.add('hidden');
    resultsGrid.classList.add('hidden');
    loading.classList.remove('hidden');
    btnRadar.disabled = true;
    btnRadar.innerHTML = '<span class="icon">⌛</span> Processando...';

    try {
        const response = await fetch('/api/radar');
        const data = await response.json();
        
        loading.classList.add('hidden');
        resultsGrid.classList.remove('hidden');
        renderResults(data.oportunidades, 'results');
    } catch (error) {
        console.error(error);
        alert('Erro ao ligar o radar. Verifique se o servidor está rodando ou se a chave API é válida.');
        loading.classList.add('hidden');
        welcomeView.classList.remove('hidden');
    } finally {
        btnRadar.disabled = false;
        btnRadar.innerHTML = '<span class="icon">🔍</span> Ligar Radar';
    }
});

document.getElementById('btnClear').addEventListener('click', () => {
    window.location.reload();
});

function renderResults(oportunidades, targetId = 'results', isPortfolio = false) {
    const grid = document.getElementById(targetId);
    grid.innerHTML = ''; // Limpa resultados anteriores
    
    oportunidades.forEach((fii, index) => {
        const card = document.createElement('div');
        card.className = 'fii-card';
        
        // Dados do motor de decisão
        const v = fii.veredito || {};
        const qual = fii.qualitativo || {};
        
        // Classes de status
        const statusClass = `status-${fii.decisao?.toLowerCase().replace('_', '-') || 'monitorar'}`;
        
        const fmtReais = (val) => val ? `R$ ${parseFloat(val).toLocaleString('pt-BR', {minimumFractionDigits: 2})}` : 'N/A';
        const fmtPct = (val) => val ? `${val > 0 ? '+' : ''}${parseFloat(val).toFixed(1)}%` : 'N/A';

        card.innerHTML = `
            <div class="card-header">
                <div class="ticker-box">
                    <span class="ticker-symbol">${fii.ticker}</span>
                    <span class="segment-badge">${fii.segmento || 'FII'}</span>
                </div>
                <div class="decision-badge ${fii.decisao.toLowerCase()}">${fii.decisao.replace('_', ' ')}</div>
            </div>

            <div class="confidence-bar">
                <span class="label">Confiança:</span>
                <span class="confidence-value ${fii.confianca.toLowerCase()}">${fii.confianca}</span>
            </div>

            ${isPortfolio ? `
                <div class="holding-details-container glass-card">
                    <div class="holding-metric">
                        <span class="label">Minhas Cotas</span>
                        <span class="value">${fii.quantidade}</span>
                    </div>
                    <div class="holding-metric">
                        <span class="label">Preço Médio</span>
                        <span class="value">R$ ${fii.preco_medio?.toFixed(2)}</span>
                    </div>
                    <div class="holding-metric highlight">
                        <span class="label">Total Aplicado</span>
                        <span class="value">R$ ${fii.custo_total?.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                </div>
            ` : ''}

            <div class="price-grid">
                <div class="price-item">
                    <span class="label">Preço Atual</span>
                    <span class="value">R$ ${fii.preco_atual?.toFixed(2) || '---'}</span>
                </div>
                <div class="price-item highlight">
                    <span class="label">Preço Justo</span>
                    <span class="value">R$ ${fii.preco_justo?.toFixed(2) || '---'}</span>
                </div>
                <div class="price-item">
                    <span class="label">Entrada Ideal</span>
                    <span class="value">R$ ${fii.preco_entrada?.toFixed(2) || '---'}</span>
                </div>
            </div>

            <div class="metrics-grid">
                <div class="metric">
                    <span class="label">Margem</span>
                    <span class="value ${fii.margem > 0 ? 'pos' : 'neg'}">${fii.margem > 0 ? '+' : ''}${fii.margem}%</span>
                </div>
                <div class="metric">
                    <span class="label">P/VP</span>
                    <span class="value">${fii.pvp?.toFixed(2) || '---'}</span>
                </div>
                <div class="metric">
                    <span class="label">DY 12M</span>
                    <span class="value">+${fii.dy_12m_pct?.toFixed(1) || '---'}%</span>
                </div>
                <div class="metric">
                    <span class="label">Recorrência</span>
                    <span class="value">${fii.pct_recorrente || '---'}%</span>
                </div>
            </div>

            <div class="gate-trail">
                <div class="gate-title">Esteira de Qualidade (8 Gates)</div>
                <div class="gates-container">
                    ${fii.trilha_gates.map(gate => `<span class="gate-tag">${gate}</span>`).join('')}
                </div>
            </div>

            <div class="ai-analysis">
                <div class="ai-header">
                    <span class="ai-icon">🧠</span>
                    <span class="ai-label">Inteligência FIIA</span>
                    <span class="ai-score">Score: ${fii.score_ia || '?'}/10</span>
                </div>
                <div class="ai-content">
                    ${fii.motivo || 'Aguardando processamento...'}
                </div>
            </div>

            ${fii.alertas && fii.alertas.length > 0 ? `
                <div class="alerts-box">
                    ${fii.alertas.map(alert => `<div class="alert-item">⚠️ ${alert}</div>`).join('')}
                </div>
            ` : ''}

            <div class="card-footer">
                <span class="footer-info">Próxima Revisão: ${fii.revisao || 'Próximo Radar'}</span>
            </div>
        `;
        
        grid.appendChild(card);
    });
}
