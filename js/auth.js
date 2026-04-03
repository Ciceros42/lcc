/* auth.js — Login/register/logout for all pages.
   Requires: supabase-js CDN, config.js
   Exposes:  window.sb  (Supabase client)
             window.sbUser (current user or null)
   Fires:    document event "lccAuth" with {user} on every auth state change
*/
(function () {
  'use strict';

  // ── Init Supabase client ──────────────────────────────────────────────────
  window.sb = window.supabase.createClient(
    window.LCC_SUPABASE_URL,
    window.LCC_SUPABASE_KEY
  );
  window.sbUser = null;

  // ── Inject auth area into header ──────────────────────────────────────────
  function injectAuthArea() {
    var area = document.getElementById('auth-area');
    if (!area) return;
    area.innerHTML =
      '<button class="nav-login-btn" id="nav-login-btn">Log In</button>'
      + '<span class="nav-user-info" id="nav-user-info" style="display:none">'
      +   '<span class="nav-username" id="nav-username"></span>'
      +   '<button class="nav-logout-btn" id="nav-logout-btn">Log Out</button>'
      + '</span>';

    document.getElementById('nav-login-btn').addEventListener('click', openModal);
    document.getElementById('nav-logout-btn').addEventListener('click', doLogout);
  }

  // ── Inject modal HTML into body ───────────────────────────────────────────
  function injectModal() {
    var el = document.createElement('div');
    el.innerHTML = [
      '<div id="auth-overlay" class="auth-overlay" style="display:none">',
      '  <div class="auth-modal">',
      '    <button class="auth-modal-close" id="auth-close">&times;</button>',
      '    <h2 class="auth-modal-title">LCC Bouldering</h2>',
      '    <div class="auth-tabs">',
      '      <button class="auth-tab-btn active" data-tab="login">Log In</button>',
      '      <button class="auth-tab-btn" data-tab="register">Register</button>',
      '    </div>',
      '    <div id="auth-panel-login" class="auth-panel">',
      '      <div class="auth-field">',
      '        <label class="auth-label">Username</label>',
      '        <input class="auth-input" type="text" id="auth-login-username" autocomplete="username" placeholder="your username">',
      '      </div>',
      '      <div class="auth-field">',
      '        <label class="auth-label">Password</label>',
      '        <input class="auth-input" type="password" id="auth-login-password" autocomplete="current-password" placeholder="password">',
      '      </div>',
      '      <div class="auth-error" id="auth-login-error"></div>',
      '      <button class="auth-submit" id="auth-login-submit">Log In</button>',
      '    </div>',
      '    <div id="auth-panel-register" class="auth-panel" style="display:none">',
      '      <div class="auth-field">',
      '        <label class="auth-label">Username</label>',
      '        <input class="auth-input" type="text" id="auth-reg-username" autocomplete="username" placeholder="choose a username">',
      '      </div>',
      '      <div class="auth-field">',
      '        <label class="auth-label">Password</label>',
      '        <input class="auth-input" type="password" id="auth-reg-password" autocomplete="new-password" placeholder="choose a password">',
      '      </div>',
      '      <div class="auth-field">',
      '        <label class="auth-label">Confirm Password</label>',
      '        <input class="auth-input" type="password" id="auth-reg-confirm" autocomplete="new-password" placeholder="repeat password">',
      '      </div>',
      '      <div class="auth-error" id="auth-reg-error"></div>',
      '      <button class="auth-submit" id="auth-reg-submit">Create Account</button>',
      '    </div>',
      '  </div>',
      '</div>'
    ].join('\n');
    document.body.appendChild(el.firstElementChild);

    // Tab switching
    document.querySelectorAll('.auth-tab-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.auth-tab-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var tab = btn.dataset.tab;
        document.getElementById('auth-panel-login').style.display    = tab === 'login'    ? '' : 'none';
        document.getElementById('auth-panel-register').style.display = tab === 'register' ? '' : 'none';
        document.getElementById('auth-login-error').textContent = '';
        document.getElementById('auth-reg-error').textContent   = '';
      });
    });

    // Close
    document.getElementById('auth-close').addEventListener('click', closeModal);
    document.getElementById('auth-overlay').addEventListener('click', function (e) {
      if (e.target === this) closeModal();
    });

    // Login submit
    document.getElementById('auth-login-submit').addEventListener('click', doLogin);
    document.getElementById('auth-login-password').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') doLogin();
    });

    // Register submit
    document.getElementById('auth-reg-submit').addEventListener('click', doRegister);
    document.getElementById('auth-reg-confirm').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') doRegister();
    });
  }

  // ── Modal helpers ─────────────────────────────────────────────────────────
  function openModal() {
    document.getElementById('auth-overlay').style.display = 'flex';
    setTimeout(function () { document.getElementById('auth-login-username').focus(); }, 50);
  }

  function closeModal() {
    document.getElementById('auth-overlay').style.display = 'none';
  }

  // ── Auth actions ──────────────────────────────────────────────────────────
  function setLoginError(msg)  { document.getElementById('auth-login-error').textContent = msg; }
  function setRegError(msg)    { document.getElementById('auth-reg-error').textContent = msg; }
  function setSubmitLoading(id, loading) {
    var btn = document.getElementById(id);
    if (btn) btn.disabled = loading;
  }

  function usernameToEmail(u) { return u.trim().toLowerCase() + '@lcc.internal'; }

  function validateUsername(u) {
    if (!u) return 'Username is required.';
    if (u.length < 3) return 'Username must be at least 3 characters.';
    if (!/^[a-zA-Z0-9_-]+$/.test(u)) return 'Username may only contain letters, numbers, _ and -.';
    return null;
  }

  async function doLogin() {
    var username = document.getElementById('auth-login-username').value.trim();
    var password = document.getElementById('auth-login-password').value;
    setLoginError('');
    if (!username || !password) { setLoginError('Please enter username and password.'); return; }
    setSubmitLoading('auth-login-submit', true);
    try {
      var res = await window.sb.auth.signInWithPassword({
        email: usernameToEmail(username),
        password: password
      });
      if (res.error) { setLoginError('Incorrect username or password.'); return; }
      closeModal();
    } catch (e) {
      setLoginError('Login failed. Please try again.');
    } finally {
      setSubmitLoading('auth-login-submit', false);
    }
  }

  async function doRegister() {
    var username = document.getElementById('auth-reg-username').value.trim();
    var password = document.getElementById('auth-reg-password').value;
    var confirm  = document.getElementById('auth-reg-confirm').value;
    setRegError('');

    var usernameErr = validateUsername(username);
    if (usernameErr) { setRegError(usernameErr); return; }
    if (password.length < 6) { setRegError('Password must be at least 6 characters.'); return; }
    if (password !== confirm) { setRegError('Passwords do not match.'); return; }

    // Check if username already taken
    var existing = await window.sb.from('profiles').select('id').eq('username', username).maybeSingle();
    if (existing.data) { setRegError('Username already taken.'); return; }

    setSubmitLoading('auth-reg-submit', true);
    try {
      var res = await window.sb.auth.signUp({
        email: usernameToEmail(username),
        password: password
      });
      if (res.error) { setRegError(res.error.message); return; }

      // Create profile row
      var userId = res.data.user.id;
      var profRes = await window.sb.from('profiles').insert({ id: userId, username: username });
      if (profRes.error) { setRegError('Account created but profile setup failed: ' + profRes.error.message); return; }

      closeModal();
    } catch (e) {
      setRegError('Registration failed. Please try again.');
    } finally {
      setSubmitLoading('auth-reg-submit', false);
    }
  }

  async function doLogout() {
    await window.sb.auth.signOut();
  }

  // ── Auth state handler ────────────────────────────────────────────────────
  function updateHeader(user) {
    var loginBtn   = document.getElementById('nav-login-btn');
    var userInfo   = document.getElementById('nav-user-info');
    var usernameEl = document.getElementById('nav-username');
    if (!loginBtn) return;
    if (user) {
      loginBtn.style.display  = 'none';
      userInfo.style.display  = 'flex';
      usernameEl.textContent  = user.username;
    } else {
      loginBtn.style.display  = '';
      userInfo.style.display  = 'none';
    }
  }

  // Cache username from profiles table
  var cachedUsername = null;

  async function resolveUsername(user) {
    if (!user) return null;
    if (cachedUsername) return cachedUsername;
    var res = await window.sb.from('profiles').select('username').eq('id', user.id).maybeSingle();
    cachedUsername = res.data ? res.data.username : (user.email || '').split('@')[0];
    return cachedUsername;
  }

  window.sb.auth.onAuthStateChange(async function (event, session) {
    cachedUsername = null;
    var user = session ? session.user : null;
    window.sbUser = user;
    var username = user ? await resolveUsername(user) : null;
    var detail = { user: user, username: username };
    updateHeader(username ? { username: username } : null);
    document.dispatchEvent(new CustomEvent('lccAuth', { detail: detail }));
  });

  // ── Boot ──────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    injectAuthArea();
    injectModal();
  });

})();
