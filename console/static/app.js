// Attach Gateway MCP Console - Client-side JavaScript

const AUTH_TOKEN_KEY = 'attach_mcp_token';

// Token management
function getToken() {
    return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
}

function clearToken() {
    localStorage.removeItem(AUTH_TOKEN_KEY);
}

// API helpers
async function fetchAPI(path, options = {}) {
    const token = getToken();
    if (!token) {
        throw new Error('No authentication token');
    }

    const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers,
    };

    const response = await fetch(path, {
        ...options,
        headers,
    });

    if (response.status === 401) {
        clearToken();
        showLoginPrompt();
        throw new Error('Authentication failed');
    }

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }

    return response.json();
}

// UI state management
function showLoginPrompt() {
    document.getElementById('login-prompt').style.display = 'block';
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('auth-status').textContent = '';
}

function showDashboard() {
    document.getElementById('login-prompt').style.display = 'none';
    document.getElementById('dashboard').style.display = 'block';
    document.getElementById('auth-status').textContent = 'Authenticated';
    loadOverview();
}

function switchView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.style.display = 'none');
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    const viewElement = document.getElementById(`${viewName}-view`);
    if (viewElement) {
        viewElement.style.display = 'block';
    }

    const navButton = document.querySelector(`.nav-btn[data-view="${viewName}"]`);
    if (navButton) {
        navButton.classList.add('active');
    }

    if (viewName === 'overview') {
        loadOverview();
    } else if (viewName === 'events') {
        loadEvents();
    } else if (viewName === 'servers') {
        loadServers();
    }
}

// Data loaders
async function loadOverview() {
    try {
        const data = await fetchAPI('/console/api/overview');

        document.getElementById('calls-today').textContent = data.calls_today || 0;
        document.getElementById('denies-today').textContent = data.denies_today || 0;

        const topToolsList = document.getElementById('top-tools');
        topToolsList.innerHTML = '';
        (data.top_tools || []).forEach(([tool, count]) => {
            const li = document.createElement('li');
            li.textContent = `${tool}: ${count}`;
            topToolsList.appendChild(li);
        });

        const topUsersList = document.getElementById('top-users');
        topUsersList.innerHTML = '';
        (data.top_users || []).forEach(([user, count]) => {
            const li = document.createElement('li');
            li.textContent = `${user.substring(0, 16)}...: ${count}`;
            topUsersList.appendChild(li);
        });
    } catch (error) {
        console.error('Failed to load overview:', error);
    }
}

async function loadEvents() {
    try {
        const limit = document.getElementById('events-limit').value;
        const data = await fetchAPI(`/console/api/events?limit=${limit}`);

        const tbody = document.getElementById('events-tbody');
        tbody.innerHTML = '';

        (data.events || []).forEach(event => {
            const row = tbody.insertRow();
            row.insertCell().textContent = new Date(event.ts * 1000).toLocaleString();
            row.insertCell().textContent = event.user.substring(0, 16) + '...';
            row.insertCell().textContent = event.server || '-';
            row.insertCell().textContent = event.method || '-';
            row.insertCell().textContent = event.tool || '-';

            const allowedCell = row.insertCell();
            allowedCell.textContent = event.allowed ? 'Yes' : 'No';
            allowedCell.className = event.allowed ? 'allowed-yes' : 'allowed-no';

            row.insertCell().textContent = event.latency_ms ? event.latency_ms.toFixed(2) : '-';
            row.insertCell().textContent = event.error || '-';
        });
    } catch (error) {
        console.error('Failed to load events:', error);
    }
}

async function loadServers() {
    try {
        const data = await fetchAPI('/console/api/servers');

        const serversList = document.getElementById('servers-list');
        serversList.innerHTML = '';

        const servers = data.servers || {};
        if (Object.keys(servers).length === 0) {
            serversList.innerHTML = '<p>No MCP servers configured.</p>';
            return;
        }

        Object.entries(servers).forEach(([name, config]) => {
            const card = document.createElement('div');
            card.className = 'server-card';

            const header = document.createElement('h3');
            header.textContent = name;
            card.appendChild(header);

            const status = document.createElement('div');
            status.className = `server-status ${config.enabled ? 'enabled' : 'disabled'}`;
            status.textContent = config.enabled ? 'Enabled' : 'Disabled';
            card.appendChild(status);

            const url = document.createElement('div');
            url.className = 'server-url';
            url.textContent = config.url;
            card.appendChild(url);

            serversList.appendChild(card);
        });
    } catch (error) {
        console.error('Failed to load servers:', error);
    }
}

// Event handlers
document.addEventListener('DOMContentLoaded', () => {
    // Check if token exists
    const token = getToken();
    if (token) {
        showDashboard();
    } else {
        showLoginPrompt();
    }

    // Save token button
    document.getElementById('save-token-btn').addEventListener('click', () => {
        const tokenInput = document.getElementById('token-input');
        const token = tokenInput.value.trim();
        if (token) {
            setToken(token);
            tokenInput.value = '';
            showDashboard();
        }
    });

    // Logout button
    document.getElementById('logout-btn').addEventListener('click', () => {
        clearToken();
        showLoginPrompt();
    });

    // Navigation buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const viewName = e.target.dataset.view;
            if (viewName) {
                switchView(viewName);
            }
        });
    });

    // Refresh events button
    document.getElementById('refresh-events-btn').addEventListener('click', () => {
        loadEvents();
    });
});
