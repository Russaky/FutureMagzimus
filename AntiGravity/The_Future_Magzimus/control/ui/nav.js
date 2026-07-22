/* Shared sidebar navigation — injected into all pages */
(function () {
  const pages = [
    { href: '/',             icon: '◎', label: 'Control',  title: 'Live Control' },
    { href: '/dashboard.html',icon: '🖥️', label: 'Dashboard', title: 'Status & Traffic' },
    { href: '/measure.html', icon: '📐', label: 'Measure',   title: 'Measurement Campaign' },
    { href: '/onboarding.html', icon: '🧭', label: 'Guide',  title: 'Measurement Onboarding' },
    { href: '/bank.html',    icon: '🗃️', label: 'Banks',   title: 'Bank Manager' },
    { href: '/effects.html', icon: '🎨', label: 'Effects', title: 'Effects Lab' },
  ];

  const cur = window.location.pathname.replace(/\/$/, '') || '/';

  const nav = document.createElement('nav');
  nav.className = 'sidebar';
  nav.innerHTML =
    '<div class="sidebar-logo">THE·FUTURE<br>MAGZIMUS</div>' +
    pages.map(p => {
      const href = p.href === '/' ? '/' : p.href;
      const isActive = cur === href || (href !== '/' && cur.endsWith(href.replace(/^\//, '')));
      return `<a href="${href}" class="nav-item${isActive ? ' active' : ''}" title="${p.title}">
        <span class="nav-icon">${p.icon}</span>
        <span class="nav-label">${p.label}</span>
      </a>`;
    }).join('');

  document.body.insertBefore(nav, document.body.firstChild);
  document.body.classList.add('has-sidebar');

  // ─── Hub connection widget ─────────────────────────────────────────────────
  // ה-Hub מתחבר/מתנתק פיזית הרבה, גם באמצע הפעלה — הווידג'ט הזה חייב להיות
  // בולט ותמיד נכון, בלי תלות בזה שהדף טוען socket.io. פולינג עצמאי על
  // /api/hub/status, לא מבוסס WebSocket.
  const style = document.createElement('style');
  style.textContent = `
    #hub-widget { margin-top: auto; width: 100%; display: flex; flex-direction: column;
      align-items: center; padding-top: 10px; border-top: 1px solid rgba(128,128,128,0.25); }
    #hub-dot-btn { display: flex; flex-direction: column; align-items: center; gap: 3px;
      background: none; border: none; cursor: pointer; padding: 6px 2px; border-radius: 12px;
      font-family: inherit; width: 60px; }
    #hub-dot-btn:hover { background: rgba(128,128,128,0.15); }
    #hub-dot { width: 10px; height: 10px; border-radius: 50%; background: #999; flex-shrink: 0; }
    #hub-dot.on { background: #3ddc84; box-shadow: 0 0 6px #3ddc84; }
    #hub-dot.off { background: #ff5c7a; animation: hub-pulse 1.4s infinite; }
    #hub-dot.pending { background: #ffb454; }
    @keyframes hub-pulse { 0%,100%{opacity:1} 50%{opacity:.35} }
    #hub-label { font-size: 0.55rem; font-weight: 600; letter-spacing: .3px; color: inherit; opacity: .8; }

    #hub-panel { position: fixed; left: 82px; bottom: 12px; z-index: 10001;
      width: 260px; background: #14161f; color: #e8ecf4; border: 1px solid rgba(255,255,255,0.15);
      border-radius: 10px; padding: 14px; box-shadow: 0 8px 28px rgba(0,0,0,0.45);
      font-family: 'Segoe UI', system-ui, sans-serif; display: none; }
    #hub-panel.open { display: block; }
    #hub-panel h4 { font-size: 0.8rem; margin: 0 0 8px; letter-spacing: .3px; }
    #hub-panel .hub-status-line { font-size: 0.72rem; color: #b8c0d4; margin-bottom: 10px; line-height: 1.5; word-break: break-all; }
    #hub-panel .hub-status-line b { color: #fff; }
    #hub-panel .hub-btn-row { display: flex; gap: 6px; margin-bottom: 8px; }
    #hub-panel button.hub-action { flex: 1; background: #232637; border: 1px solid rgba(255,255,255,0.15);
      color: #e8ecf4; padding: 7px 4px; border-radius: 6px; cursor: pointer; font-size: 0.68rem; }
    #hub-panel button.hub-action:hover { background: #2d3148; }
    #hub-panel button.hub-action.danger:hover { background: #3a1c26; border-color: #ff5c7a; }
    #hub-ports { max-height: 140px; overflow-y: auto; margin-top: 4px; }
    .hub-port-row { display: flex; justify-content: space-between; align-items: center;
      font-size: 0.68rem; padding: 5px 6px; border-radius: 5px; margin-bottom: 3px; background: rgba(255,255,255,0.04); }
    .hub-port-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-left: 6px; }
    .hub-port-row button { background: #3ddc84; border: none; color: #06180d; font-weight: 700;
      padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 0.65rem; flex-shrink: 0; }

    #hub-banner { position: fixed; top: 0; left: 0; right: 0; z-index: 99999;
      background: #ff5c7a; color: #2a0812; font-family: 'Segoe UI', system-ui, sans-serif;
      font-size: 0.8rem; font-weight: 700; padding: 8px 16px; display: none;
      align-items: center; justify-content: center; gap: 14px; box-shadow: 0 2px 10px rgba(0,0,0,.3); }
    #hub-banner.show { display: flex; }
    #hub-banner button { background: #2a0812; color: #ff5c7a; border: none; padding: 4px 12px;
      border-radius: 5px; cursor: pointer; font-weight: 700; font-size: 0.75rem; }
  `;
  document.head.appendChild(style);

  const widget = document.createElement('div');
  widget.id = 'hub-widget';
  widget.innerHTML = `
    <button id="hub-dot-btn" title="חיבור ה-Hub">
      <span id="hub-dot" class="pending"></span>
      <span id="hub-label">Hub</span>
    </button>`;
  nav.appendChild(widget);

  const panel = document.createElement('div');
  panel.id = 'hub-panel';
  panel.innerHTML = `
    <h4>חיבור ה-Hub</h4>
    <div class="hub-status-line" id="hub-status-line">בודק…</div>
    <div class="hub-btn-row">
      <button class="hub-action" id="hub-scan-btn">🔍 חפש</button>
      <button class="hub-action" id="hub-connect-btn">🔌 התחבר</button>
      <button class="hub-action danger" id="hub-disconnect-btn">⛔ נתק</button>
    </div>
    <div id="hub-ports"></div>
  `;
  document.body.appendChild(panel);

  const banner = document.createElement('div');
  banner.id = 'hub-banner';
  banner.innerHTML = `<span id="hub-banner-text">⚠️ ה-Hub לא מחובר</span><button id="hub-banner-connect">התחבר</button>`;
  document.body.appendChild(banner);

  const dot        = document.getElementById('hub-dot');
  const statusLine = document.getElementById('hub-status-line');
  const portsBox   = document.getElementById('hub-ports');
  const bannerText = document.getElementById('hub-banner-text');

  function post(path, body) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }).then(r => r.json()).catch(() => ({ ok: false, error: 'שגיאת רשת' }));
  }

  function applyStatus(s) {
    if (s.connected) {
      dot.className = 'on';
      statusLine.innerHTML = `<b>מחובר</b><br>${s.port || ''}`;
      banner.classList.remove('show');
    } else {
      dot.className = 'off';
      statusLine.innerHTML = `<b>לא מחובר</b>${s.error ? '<br>' + s.error : ''}`;
      bannerText.textContent = '⚠️ ה-Hub לא מחובר' + (s.error ? ' — ' + s.error : '');
      banner.classList.add('show');
    }
  }

  function refreshStatus() {
    fetch('/api/hub/status').then(r => r.json()).then(applyStatus)
      .catch(() => { dot.className = 'off'; statusLine.textContent = 'אין קשר לשרת'; });
  }

  function renderPorts(ports, guess) {
    if (!ports.length) { portsBox.innerHTML = '<div class="hub-status-line">לא נמצאו פורטים</div>'; return; }
    portsBox.innerHTML = ports.map(p => `
      <div class="hub-port-row">
        <span title="${p.description}">${p.device}${p.device === guess ? ' ⭐' : ''}</span>
        <button data-port="${p.device}">התחבר</button>
      </div>`).join('');
    portsBox.querySelectorAll('button[data-port]').forEach(btn => {
      btn.onclick = () => { dot.className = 'pending'; post('/api/hub/connect', { port: btn.dataset.port }).then(applyStatus); };
    });
  }

  document.getElementById('hub-dot-btn').onclick = () => {
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) refreshStatus();
  };
  document.addEventListener('click', (e) => {
    if (!panel.contains(e.target) && e.target.id !== 'hub-dot-btn' && !document.getElementById('hub-dot-btn').contains(e.target)) {
      panel.classList.remove('open');
    }
  });

  document.getElementById('hub-scan-btn').onclick = () => {
    portsBox.innerHTML = '<div class="hub-status-line">סורק…</div>';
    fetch('/api/hub/scan').then(r => r.json()).then(d => renderPorts(d.ports || [], d.guess));
  };
  document.getElementById('hub-connect-btn').onclick = () => {
    dot.className = 'pending';
    post('/api/hub/connect', {}).then(applyStatus);
  };
  document.getElementById('hub-disconnect-btn').onclick = () => {
    post('/api/hub/disconnect', {}).then(applyStatus);
  };
  document.getElementById('hub-banner-connect').onclick = () => {
    dot.className = 'pending';
    post('/api/hub/connect', {}).then(applyStatus);
  };

  refreshStatus();
  setInterval(refreshStatus, 2000);
})();
