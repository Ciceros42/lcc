/* sends.js — Log sends on boulder pages via localStorage.
   Requires: data/users.js (window.USERS)
   Storage:  localStorage key "lcc_sends"
             { climbId: { name, grade, boulder_url, senders: [username, ...] } }
*/
(function () {
  'use strict';

  var STORAGE_KEY = 'lcc_sends';

  function loadData() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch (e) { return {}; }
  }

  function saveData(data) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }

  function getSenders(climbId) {
    var data = loadData();
    return (data[climbId] && data[climbId].senders) || [];
  }

  function toggleSend(climbId, climbName, grade, boulderUrl, username) {
    var data = loadData();
    if (!data[climbId]) {
      data[climbId] = { name: climbName, grade: grade, boulder_url: boulderUrl, senders: [] };
    }
    var idx = data[climbId].senders.indexOf(username);
    if (idx === -1) {
      data[climbId].senders.push(username);
    } else {
      data[climbId].senders.splice(idx, 1);
    }
    saveData(data);
    return data[climbId].senders;
  }

  // ── Picker dropdown ───────────────────────────────────────────────────────
  var activePicker = null;

  function closePicker() {
    if (activePicker) { activePicker.remove(); activePicker = null; }
  }

  function openPicker(btn, climbId, climbName, grade, boulderUrl) {
    closePicker();

    var users = window.USERS || [];
    if (!users.length) {
      var msg = document.createElement('div');
      msg.className = 'send-picker';
      msg.textContent = 'No users added yet.';
      positionAndShow(msg, btn);
      return;
    }

    var senders = getSenders(climbId);

    var picker = document.createElement('div');
    picker.className = 'send-picker';

    users.forEach(function (username) {
      var isSent = senders.indexOf(username) !== -1;
      var row = document.createElement('button');
      row.className = 'send-picker-row' + (isSent ? ' send-picker-row-sent' : '');
      row.innerHTML = (isSent ? '<span class="send-check">&#10003;</span> ' : '<span class="send-check send-check-empty"></span> ') + username;
      row.addEventListener('mousedown', function (e) {
        e.preventDefault();
        var newSenders = toggleSend(climbId, climbName, grade, boulderUrl, username);
        updateBtn(btn, newSenders);
        closePicker();
      });
      picker.appendChild(row);
    });

    positionAndShow(picker, btn);
  }

  function positionAndShow(picker, btn) {
    document.body.appendChild(picker);
    activePicker = picker;

    var rect = btn.getBoundingClientRect();
    picker.style.top  = (rect.bottom + window.scrollY + 4) + 'px';
    picker.style.left = (rect.left + window.scrollX) + 'px';
  }

  document.addEventListener('click', function (e) {
    if (activePicker && !activePicker.contains(e.target) && !e.target.classList.contains('send-btn')) {
      closePicker();
    }
  });

  // ── Button label ──────────────────────────────────────────────────────────
  function updateBtn(btn, senders) {
    if (!senders || !senders.length) {
      btn.textContent = '+ Log Send';
      btn.classList.remove('send-btn-sent');
    } else {
      btn.textContent = '&#10003; ' + senders.join(', ');
      btn.innerHTML   = '&#10003; ' + senders.map(function (s) {
        return '<span>' + s + '</span>';
      }).join(', ');
      btn.classList.add('send-btn-sent');
    }
  }

  // ── Inject buttons ────────────────────────────────────────────────────────
  function injectButtons() {
    var boulderUrl = (window.location.pathname.match(/boulders\/[^/]+\.html/) || [''])[0];

    document.querySelectorAll('.problem-entry').forEach(function (article) {
      if (article.querySelector('.send-btn')) return;
      var climbId   = article.dataset.climbId;
      var climbName = article.dataset.climbName;
      var grade     = article.dataset.grade;
      if (!climbId) return;

      var btn = document.createElement('button');
      btn.className = 'send-btn';
      updateBtn(btn, getSenders(climbId));

      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        openPicker(btn, climbId, climbName, grade, boulderUrl);
      });

      var topoDiv = article.querySelector('.problem-topo');
      if (topoDiv) topoDiv.insertAdjacentElement('afterend', btn);
      else article.appendChild(btn);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectButtons);
  } else {
    injectButtons();
  }

})();
