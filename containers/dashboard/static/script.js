// Dashboard JavaScript
let pnlChart = null;
let currentTab = 'trades';

// Tab switching
function switchTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Show/hide sections
    if (tabName === 'trades') {
        document.getElementById('filters').style.display = 'flex';
        document.getElementById('pnlChartCard').style.display = 'block';
        document.getElementById('tradesCard').style.display = 'block';
        document.getElementById('learningCard').style.display = 'none';
        document.getElementById('marketCard').style.display = 'none';
        fetchTrades();
        fetchPNL();
    } else if (tabName === 'learning') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('pnlChartCard').style.display = 'none';
        document.getElementById('tradesCard').style.display = 'none';
        document.getElementById('learningCard').style.display = 'block';
        document.getElementById('marketCard').style.display = 'none';
        fetchLearningPatterns();
    } else if (tabName === 'market') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('pnlChartCard').style.display = 'none';
        document.getElementById('tradesCard').style.display = 'none';
        document.getElementById('learningCard').style.display = 'none';
        document.getElementById('marketCard').style.display = 'block';
        fetchMarketState();
    }
}

// Fetch bot status
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        document.getElementById('positions').textContent = data.active_positions || 0;
        
        const pnlValue = data.today_pnl || 0;
        const pnlElement = document.getElementById('pnl');
        pnlElement.innerHTML = pnlValue >= 0 ? `+₹${pnlValue.toFixed(2)}` : `-₹${Math.abs(pnlValue).toFixed(2)}`;
        pnlElement.className = pnlValue >= 0 ? 'stat-value positive' : 'stat-value negative';
        
        document.getElementById('winrate').textContent = `${(data.win_rate || 0).toFixed(1)}%`;
        
        const statusHtml = `<span class="status-badge status-${data.status}">${data.status}</span>`;
        document.getElementById('status').innerHTML = statusHtml;
    } catch(e) {
        console.error('Status fetch failed:', e);
    }
}

// Fetch recent trades
async function fetchTrades() {
    if (currentTab !== 'trades') return;
    
    try {
        const stock = document.getElementById('stockFilter').value;
        const days = document.getElementById('daysFilter').value;
        
        let url = `/api/trades?limit=50&days=${days}`;
        if (stock) url += `&stock=${stock}`;
        
        const res = await fetch(url);
        const data = await res.json();
        
        const tbody = document.querySelector('#tradesTable tbody');
        
        if (!data.trades || data.trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No trades found</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.trades.map(trade => `
            <tr>
                <td>${new Date(trade.timestamp).toLocaleString()}</td>
                <td><strong>${trade.stock_symbol || 'N/A'}</strong></td>
                <td class="${(trade.action || '').toLowerCase()}">${trade.action || 'HOLD'}</td>
                <td>₹${(trade.price || 0).toFixed(2)}</td>
                <td>${trade.quantity || 0}</td>
                <td class="${(trade.pnl || 0) >= 0 ? 'positive' : 'negative'}">
                    ${(trade.pnl || 0) >= 0 ? '+' : ''}₹${(trade.pnl || 0).toFixed(2)}
                </td>
            </tr>
        `).join('');
    } catch(e) {
        console.error('Trades fetch failed:', e);
    }
}

// Fetch P&L data and update chart
async function fetchPNL() {
    if (currentTab !== 'trades') return;
    
    try {
        const days = document.getElementById('daysFilter').value;
        const res = await fetch(`/api/pnl?days=${days}`);
        const data = await res.json();
        
        if (pnlChart) pnlChart.destroy();
        
        const ctx = document.getElementById('pnlChart').getContext('2d');
        pnlChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.dates || [],
                datasets: [
                    {
                        label: 'Cumulative P&L',
                        data: data.cumulative_pnl || [],
                        borderColor: '#38bdf8',
                        backgroundColor: 'rgba(56, 189, 248, 0.1)',
                        fill: true,
                        tension: 0.1
                    },
                    {
                        label: 'Daily P&L',
                        data: data.daily_pnl || [],
                        borderColor: '#eab308',
                        backgroundColor: 'transparent',
                        borderDash: [5, 5],
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: { position: 'top', labels: { color: '#e2e8f0' } },
                    tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ₹${ctx.raw.toFixed(2)}` } }
                },
                scales: { y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                          x: { ticks: { color: '#94a3b8', maxRotation: 45 }, grid: { color: '#334155' } } }
            }
        });
    } catch(e) {
        console.error('PNL fetch failed:', e);
    }
}

// Fetch learning patterns
async function fetchLearningPatterns() {
    try {
        const res = await fetch('/api/learning?limit=20');
        const data = await res.json();
        
        const tbody = document.querySelector('#learningTable tbody');
        
        if (!data.patterns || data.patterns.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No learning patterns yet</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.patterns.map(pattern => `
            <tr>
                <td>${pattern.date || '-'}</td>
                <td>${pattern.pattern_type || '-'}</td>
                <td>${pattern.rsi_range || '-'}</td>
                <td>${pattern.sentiment_threshold || '-'}</td>
                <td class="${(pattern.win_rate || 0) >= 50 ? 'positive' : 'negative'}">${(pattern.win_rate || 0).toFixed(1)}%</td>
                <td>${pattern.sample_size || 0}</td>
            </tr>
        `).join('');
    } catch(e) {
        console.error('Learning patterns fetch failed:', e);
    }
}

// Fetch market state
async function fetchMarketState() {
    try {
        const res = await fetch('/api/market-state?days=7');
        const data = await res.json();
        
        const tbody = document.querySelector('#marketTable tbody');
        
        if (!data.market_states || data.market_states.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">No market state data yet</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.market_states.map(state => `
            <tr>
                <td>${state.date || '-'}</td>
                <td class="${state.global_sentiment === 'positive' ? 'positive' : (state.global_sentiment === 'negative' ? 'negative' : '')}">
                    ${state.global_sentiment || 'neutral'}
                </td>
                <td>${state.india_vix || '-'}</td>
                <td>${(state.watchlist || []).join(', ') || '-'}</td>
                <td>${(state.key_news || []).slice(0, 2).join(', ') || '-'}</td>
            </tr>
        `).join('');
    } catch(e) {
        console.error('Market state fetch failed:', e);
    }
}

// Fetch all data based on current tab
async function fetchAllData() {
    const now = new Date();
    document.getElementById('lastUpdated').textContent = `Last updated: ${now.toLocaleTimeString()}`;
    
    await fetchStatus();
    
    if (currentTab === 'trades') {
        await fetchTrades();
        await fetchPNL();
    } else if (currentTab === 'learning') {
        await fetchLearningPatterns();
    } else if (currentTab === 'market') {
        await fetchMarketState();
    }
}

// Auto-refresh every 30 seconds
fetchAllData();
setInterval(fetchAllData, 30000);