(function () {
  const LEGACY_TOKEN_KEY = 'productshot_access_token';
  const USER_KEY = 'productshot_user';
  const originalFetch = window.fetch.bind(window);
  let currentUser = readUser();
  let authMode = 'login';

  function apiBase() {
    return window.PRODUCTSHOT_API_BASE || '';
  }

  function readUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    } catch (_) {
      return null;
    }
  }

  function setSession(_token, user) {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    currentUser = user;
    updateAuthControls();
  }

  function clearSession() {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    currentUser = null;
    updateAuthControls();
  }

  function say(message, type = '') {
    if (typeof window.toast === 'function') window.toast(message, type);
    else console.log(message);
  }

  function toUrl(value) {
    const raw = typeof value === 'string' ? value : value?.url;
    if (!raw) return null;
    try {
      return new URL(raw, window.location.origin);
    } catch (_) {
      return null;
    }
  }

  function isPublicApi(url) {
    const path = url.pathname;
    return path === '/api/health' || path === '/api/templates' || path.startsWith('/api/auth/');
  }

  function isProtectedApi(value) {
    const url = toUrl(value);
    if (!url) return false;
    return url.pathname.startsWith('/api/') && !isPublicApi(url);
  }

  window.fetch = async function authFetch(input, init = {}) {
    const nextInit = { ...init, credentials: init.credentials || 'include' };
    const response = await originalFetch(input, nextInit);
    if (isProtectedApi(input) && response.status === 401) {
      clearSession();
      openAuthModal('登录已过期，请重新登录。');
    }
    return response;
  };

  async function authRequest(path, body) {
    const response = await originalFetch(`${apiBase()}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `请求失败：${response.status}`);
    }
    return data;
  }

  async function refreshMe() {
    const response = await originalFetch(`${apiBase()}/api/auth/me`, {
      credentials: 'include',
    });
    if (!response.ok) {
      clearSession();
      return;
    }
    currentUser = await response.json();
    localStorage.setItem(USER_KEY, JSON.stringify(currentUser));
    updateAuthControls();
  }

  function injectAuthStyles() {
    if (document.getElementById('authStyles')) return;
    const style = document.createElement('style');
    style.id = 'authStyles';
    style.textContent = `
      .auth-field{display:grid;gap:8px;margin:12px 0}.auth-field span{font-size:13px;font-weight:900;color:#273752}.auth-field input{height:44px;border:1px solid var(--line);border-radius:12px;padding:0 12px;color:var(--navy);font-weight:760;background:#fff}.auth-field input:focus{outline:0;border-color:var(--blue);box-shadow:0 0 0 3px #eaf2ff}.auth-toggle{margin-top:12px;text-align:center;color:var(--muted);font-size:13px}.auth-toggle button{border:0;background:transparent;color:var(--blue);font-weight:950;cursor:pointer}.auth-status{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;background:#fff;padding:7px 10px;color:#33415c;font-size:12px;font-weight:900}.auth-status button{border:0;background:transparent;color:var(--blue);font-weight:950;cursor:pointer}.auth-status .danger{color:#f97316}.auth-tip{margin:10px 0 0;color:var(--muted);font-size:12px;line-height:1.55}.auth-error{min-height:20px;color:#f97316;font-size:13px;font-weight:850;margin-top:8px}.auth-register-only[hidden]{display:none!important}
    `;
    document.head.appendChild(style);
  }

  function ensureAuthModal() {
    injectAuthStyles();
    if (document.getElementById('authModal')) return;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'authModal';
    modal.hidden = true;
    modal.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="authTitle">
        <div class="modal-head">
          <div>
            <h3 id="authTitle">登录 ProductShot AI</h3>
            <p id="authSubtitle">登录后，上传图片、生成任务和历史记录会只归属于你。</p>
          </div>
          <button class="modal-close" type="button" data-auth-close aria-label="关闭">×</button>
        </div>
        <form id="authForm">
          <label class="auth-field"><span>邮箱</span><input id="authEmail" type="email" autocomplete="email" required /></label>
          <label class="auth-field"><span>密码</span><input id="authPassword" type="password" autocomplete="current-password" required minlength="8" /></label>
          <label class="auth-field auth-register-only" hidden><span>昵称</span><input id="authDisplayName" type="text" maxlength="120" autocomplete="name" /></label>
          <div class="auth-error" id="authError"></div>
          <button class="primary-btn full" id="authSubmit" type="submit">登录</button>
          <p class="auth-toggle"><span id="authToggleText">还没有账号？</span><button id="authToggleBtn" type="button">注册一个</button></p>
          <p class="auth-tip">会话使用 HttpOnly Cookie 保存，前端脚本无法直接读取 token；生产环境请务必开启 HTTPS。</p>
        </form>
      </div>`;
    document.body.appendChild(modal);

    modal.addEventListener('click', event => {
      if (event.target === modal || event.target.closest('[data-auth-close]')) closeAuthModal();
    });
    document.getElementById('authToggleBtn')?.addEventListener('click', toggleAuthMode);
    document.getElementById('authForm')?.addEventListener('submit', submitAuthForm);
  }

  function setAuthMode(mode) {
    authMode = mode;
    const isRegister = authMode === 'register';
    const title = document.getElementById('authTitle');
    const subtitle = document.getElementById('authSubtitle');
    const submit = document.getElementById('authSubmit');
    const toggleText = document.getElementById('authToggleText');
    const toggleBtn = document.getElementById('authToggleBtn');
    const displayRow = document.querySelector('.auth-register-only');
    const password = document.getElementById('authPassword');

    if (title) title.textContent = isRegister ? '注册 ProductShot AI' : '登录 ProductShot AI';
    if (subtitle) subtitle.textContent = isRegister ? '创建账号后，你的上传、生成和历史记录会自动隔离。' : '登录后，上传图片、生成任务和历史记录会只归属于你。';
    if (submit) submit.textContent = isRegister ? '注册并登录' : '登录';
    if (toggleText) toggleText.textContent = isRegister ? '已有账号？' : '还没有账号？';
    if (toggleBtn) toggleBtn.textContent = isRegister ? '去登录' : '注册一个';
    if (displayRow) displayRow.hidden = !isRegister;
    if (password) password.autocomplete = isRegister ? 'new-password' : 'current-password';
  }

  function toggleAuthMode() {
    setAuthMode(authMode === 'login' ? 'register' : 'login');
  }

  function openAuthModal(message = '') {
    ensureAuthModal();
    setAuthMode(authMode);
    const modal = document.getElementById('authModal');
    const error = document.getElementById('authError');
    if (error) error.textContent = message;
    if (modal) modal.hidden = false;
    setTimeout(() => document.getElementById('authEmail')?.focus(), 0);
  }

  function closeAuthModal() {
    const modal = document.getElementById('authModal');
    if (modal) modal.hidden = true;
  }

  async function submitAuthForm(event) {
    event.preventDefault();
    const submit = document.getElementById('authSubmit');
    const error = document.getElementById('authError');
    const email = document.getElementById('authEmail')?.value || '';
    const password = document.getElementById('authPassword')?.value || '';
    const displayName = document.getElementById('authDisplayName')?.value || '';
    if (submit) submit.disabled = true;
    if (error) error.textContent = '';
    try {
      const path = authMode === 'register' ? '/api/auth/register' : '/api/auth/login';
      const payload = authMode === 'register'
        ? { email, password, display_name: displayName || undefined }
        : { email, password };
      const data = await authRequest(path, payload);
      setSession(data.access_token, data.user);
      closeAuthModal();
      say(authMode === 'register' ? '注册成功，已登录' : '登录成功', 'success');
      if (typeof window.loadHistory === 'function') window.loadHistory({ keepCurrent: true });
    } catch (err) {
      if (error) error.textContent = err.message || '登录失败，请重试';
      say(err.message || '登录失败，请重试', 'error');
    } finally {
      if (submit) submit.disabled = false;
    }
  }

  async function logout() {
    try {
      await originalFetch(`${apiBase()}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (_) {
      // Even if the network request fails, clear local UI state.
    }
    clearSession();
    say('已退出登录', 'success');
    if (typeof window.clearCurrentTaskView === 'function') window.clearCurrentTaskView('请登录');
    openAuthModal('请重新登录后继续使用工作台。');
  }

  function updateAuthControls() {
    const navButton = Array.from(document.querySelectorAll('.desktop-nav button')).find(button => button.textContent.includes('登录') || button.textContent.includes('进入工作台') || button.textContent.includes('我的工作台'));
    if (navButton) {
      navButton.textContent = currentUser ? '我的工作台' : '登录';
      navButton.onclick = event => {
        event.preventDefault();
        if (currentUser) document.getElementById('dashboard')?.scrollIntoView({ behavior: 'smooth' });
        else openAuthModal();
      };
    }

    const dashActions = document.querySelector('.dash-actions');
    if (!dashActions) return;
    let status = document.getElementById('authStatus');
    if (!status) {
      status = document.createElement('span');
      status.className = 'auth-status';
      status.id = 'authStatus';
      dashActions.prepend(status);
    }
    if (currentUser) {
      status.innerHTML = `<span>${escapeText(currentUser.display_name || currentUser.email)}</span><button class="danger" type="button" data-auth-logout>退出</button>`;
      status.querySelector('[data-auth-logout]')?.addEventListener('click', logout);
    } else {
      status.innerHTML = '<span>未登录</span><button type="button" data-auth-login>登录</button>';
      status.querySelector('[data-auth-login]')?.addEventListener('click', () => openAuthModal());
    }
  }

  function escapeText(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function installDownloadInterceptor() {
    document.addEventListener('click', async event => {
      const button = event.target.closest('#downloadAllBtn');
      if (!button) return;
      const task = typeof state !== 'undefined' ? state.lastTask : null;
      if (!task?.id) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      try {
        button.disabled = true;
        button.classList.add('is-loading');
        if (typeof setButtonContent === 'function') setButtonContent(button, '下载中…', 'download');
        else button.textContent = '下载中…';
        const response = await fetch(`${apiBase()}/api/tasks/${encodeURIComponent(task.id)}/download.zip`);
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.detail || `下载失败：${response.status}`);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `productshot-${task.id}.zip`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (err) {
        say(err.message || '下载失败，请稍后重试', 'error');
      } finally {
        button.classList.remove('is-loading');
        if (typeof window.updateDownloadAllButton === 'function') window.updateDownloadAllButton(task);
        else {
          button.disabled = false;
          button.textContent = '下载全部';
        }
      }
    }, true);
  }

  document.addEventListener('DOMContentLoaded', () => {
    ensureAuthModal();
    updateAuthControls();
    refreshMe();
    installDownloadInterceptor();
  });

  window.ProductShotAuth = {
    open: openAuthModal,
    logout,
    getToken: () => '',
  };
})();
