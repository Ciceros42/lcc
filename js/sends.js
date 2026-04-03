/* sends.js — Log sends via Supabase.
   Requires: supabase-js CDN, config.js, data/users.js (window.USERS)
*/
(function () {
  'use strict';

  var sb = window.supabase.createClient(window.LCC_SUPABASE_URL, window.LCC_SUPABASE_KEY);
  var boulderUrl = (window.location.pathname.match(/boulders\/[^/]+\.html/) || [''])[0];

  // username -> Set of climb_ids they have sent (loaded once on page load)
  var sentByUser = {};

  async function loadSends() {
    var res = await sb.from('ascents').select('username, climb_id').in('username', window.USERS || []);
    if (res.error) { console.error('loadSends:', res.error); return; }
    sentByUser = {};
    (window.USERS || []).forEach(function (u) { sentByUser[u] = new Set(); });
    res.data.forEach(function (row) {
      if (sentByUser[row.username]) sentByUser[row.username].add(row.climb_id);
    });
    refreshAllButtons();
  }

  function isSent(username, climbId) {
    return sentByUser[username] && sentByUser[username].has(climbId);
  }

  // ── Picker ────────────────────────────────────────────────────────────────
  var activePicker = null;

  function closePicker() {
    if (activePicker) { activePicker.remove(); activePicker = null; }
  }

  function openPicker(btn, climbId, climbName, grade) {
    closePicker();
    var users = window.USERS || [];
    if (!users.length) return;

    var picker = document.createElement('div');
    picker.className = 'send-picker';

    users.forEach(function (username) {
      var sent = isSent(username, climbId);
      var row = document.createElement('button');
      row.className = 'send-picker-row' + (sent ? ' send-picker-row-sent' : '');
      row.innerHTML = (sent ? '<span class="send-check">&#10003;</span> ' : '<span class="send-check send-check-empty"></span> ') + username;
      row.addEventListener('mousedown', function (e) {
        e.preventDefault();
        toggleSend(username, climbId, climbName, grade, btn);
        closePicker();
      });
      picker.appendChild(row);
    });

    document.body.appendChild(picker);
    activePicker = picker;
    var rect = btn.getBoundingClientRect();
    picker.style.top  = (rect.bottom + window.scrollY + 4) + 'px';
    picker.style.left = (rect.left  + window.scrollX) + 'px';
  }

  document.addEventListener('click', function (e) {
    if (activePicker && !activePicker.contains(e.target) && !e.target.classList.contains('send-btn')) {
      closePicker();
    }
  });

  // ── Toggle send ───────────────────────────────────────────────────────────
  async function toggleSend(username, climbId, climbName, grade, btn) {
    if (isSent(username, climbId)) {
      var res = await sb.from('ascents').delete()
        .eq('username', username).eq('climb_id', climbId);
      if (!res.error) {
        sentByUser[username].delete(climbId);
        updateBtn(btn, climbId);
      }
    } else {
      var res = await sb.from('ascents').insert({
        username:    username,
        climb_id:    climbId,
        climb_name:  climbName,
        grade_label: grade,
        boulder_url: boulderUrl
      });
      if (!res.error) {
        sentByUser[username].add(climbId);
        updateBtn(btn, climbId);
      }
    }
  }

  // ── Button label ──────────────────────────────────────────────────────────
  function getSenders(climbId) {
    return (window.USERS || []).filter(function (u) { return isSent(u, climbId); });
  }

  function updateBtn(btn, climbId) {
    var senders = getSenders(climbId);
    if (!senders.length) {
      btn.textContent = '+ Log Send';
      btn.classList.remove('send-btn-sent');
    } else {
      btn.innerHTML = '&#10003; ' + senders.join(', ');
      btn.classList.add('send-btn-sent');
    }
  }

  function refreshAllButtons() {
    document.querySelectorAll('.send-btn').forEach(function (btn) {
      updateBtn(btn, btn.dataset.climbId);
    });
  }

  // ── Inject buttons ────────────────────────────────────────────────────────
  function injectButtons() {
    document.querySelectorAll('.problem-entry').forEach(function (article) {
      if (article.querySelector('.send-btn')) return;
      var climbId   = article.dataset.climbId;
      var climbName = article.dataset.climbName;
      var grade     = article.dataset.grade;
      if (!climbId) return;

      var btn = document.createElement('button');
      btn.className = 'send-btn';
      btn.dataset.climbId = climbId;
      btn.textContent = '+ Log Send';
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        openPicker(btn, climbId, climbName, grade);
      });

      var topoDiv = article.querySelector('.problem-topo');
      if (topoDiv) topoDiv.insertAdjacentElement('afterend', btn);
      else article.appendChild(btn);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { injectButtons(); loadSends(); });
  } else {
    injectButtons();
    loadSends();
  }

})();
