document.getElementById('btnRadar').addEventListener('click', async () => {
    const mainContent = document.getElementById('mainContent');
    const loading = document.getElementById('loading');
    const resultsGrid = document.getElementById('results');
    
    // UI State
    mainContent.querySelector('.welcome-card')?.classList.add('hidden');
    loading.classList.remove('hidden');
    resultsGrid.innerHTML = '';

    try {
        const response = await fetch('/api/radar');
        const data = await response.json();
        
        loading.classList.add('hidden');
        renderResults(data.oportunidades);
    } catch (error) {
        alert('Erro ao ligar o radar. Verifique se o servidor está rodando.');
        loading.classList.add('hidden');
    }
});

document.getElementById('btnClear').addEventListener('click', () => {
    if(confirm('Deseja limpar os resultados e recomeçar?')) {
        window.location.reload();
    }
});

function renderResults(oportunidades) {
    const grid = document.getElementById('results');
    
    oportunidades.forEach((fii, index) => {
        const card = document.createElement('div');
        card.className = 'fii-card';
        
        const qual = fii.qualitativo || {};
        const riscosHtml = (qual.riscos || []).map(r => `<span class="risco-tag">${r}</span>`).join('');
        
        card.innerHTML = `
            <div class="fii-header">
                <div>
                    <span class="ticker-badge">${fii.ticker}</span>
                    <span style="font-size: 0.8rem; color: #94a3b8; margin-left: 10px;">#${index + 1} no Ranking</span>
                </div>
                <div class="margem-badge positive">+${fii.margem.toFixed(1)}%</div>
            </div>
            
            <div class="ia-section">
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                    <span style="font-weight: 600; color: #38bdf8;">🧠 Inteligência FIIA</span>
                    <span style="font-weight: 700;">Score: ${qual.score || '?'}/10</span>
                </div>
                <p class="ia-resumo">${qual.resumo || 'Sem análise qualitativa disponível.'}</p>
                <div class="riscos-container">
                    ${riscosHtml}
                </div>
            </div>
        `;
        
        grid.appendChild(card);
    });
}
