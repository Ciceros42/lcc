/* leaderboard.js — Reads localStorage, computes points, renders leaderboard.
   Requires: data/users.js (window.USERS), data/problems.js (window.PROBLEMS)
*/
(function () {
  'use strict';

  var STORAGE_KEY = 'lcc_sends';

  function loadSends() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch (e) { return {}; }
  }

  // Total grade value = 500 * 1.5^n where n is the V-number (V0=0, V1=1, etc.)
  // VB treated as n=-1, V? treated as n=0. Per-climb value = total / count at grade.
  function gradeExponent(label) {
    if (!label) return null;
    var m = label.match(/^V(\d+)$/i);
    if (m) return parseInt(m[1], 10);
    return null; // VB and V? worth 0 points
  }

  function buildGradeValues() {
    var counts = {};
    (window.PROBLEMS || []).forEach(function (p) {
      if (p.gradeLabel) counts[p.gradeLabel] = (counts[p.gradeLabel] || 0) + 1;
    });
    var vals = {};
    Object.keys(counts).forEach(function (g) {
      var exp = gradeExponent(g);
      vals[g] = exp === null ? 0 : (500 * Math.pow(1.5, exp)) / counts[g];
    });
    return vals;
  }

  // grade → total climb count
  function buildGradeTotals() {
    var counts = {};
    (window.PROBLEMS || []).forEach(function (p) {
      if (p.gradeLabel) counts[p.gradeLabel] = (counts[p.gradeLabel] || 0) + 1;
    });
    return counts;
  }

  function render() {
    var loading = document.getElementById('leaderboard-loading');
    var body    = document.getElementById('leaderboard-body');
    if (!body) return;

    var users      = window.USERS || [];
    var sends      = loadSends();
    var gradeVals  = buildGradeValues();
    var gradeTotals = buildGradeTotals();

    // Build per-user ascent list from sends data
    var userSends = {};
    users.forEach(function (u) { userSends[u] = []; });

    Object.keys(sends).forEach(function (climbId) {
      var entry = sends[climbId];
      (entry.senders || []).forEach(function (username) {
        if (userSends[username]) {
          userSends[username].push({
            id:         climbId,
            name:       entry.name,
            grade:      entry.grade,
            boulder_url: entry.boulder_url
          });
        }
      });
    });

    // Compute points per user
    var rows = users.map(function (username) {
      var ascents = userSends[username];
      var points  = ascents.reduce(function (sum, a) {
        return sum + (gradeVals[a.grade] || 0);
      }, 0);
      return { username: username, ascents: ascents, points: points };
    });

    if (loading) loading.style.display = 'none';

    // Sort and render — also wired to toggle buttons
    var sortMode = 'points';

    function sortRows() {
      if (sortMode === 'sends') {
        rows.sort(function (a, b) {
          if (b.ascents.length !== a.ascents.length) return b.ascents.length - a.ascents.length;
          return b.points - a.points;
        });
      } else {
        rows.sort(function (a, b) {
          if (b.points !== a.points) return b.points - a.points;
          return b.ascents.length - a.ascents.length;
        });
      }
    }

    var btnPoints = document.getElementById('sort-points');
    var btnSends  = document.getElementById('sort-sends');

    function setSort(mode) {
      sortMode = mode;
      if (btnPoints) btnPoints.classList.toggle('lb-sort-active', mode === 'points');
      if (btnSends)  btnSends.classList.toggle('lb-sort-active', mode === 'sends');
      // Close any open detail rows
      document.querySelectorAll('.lb-detail-row').forEach(function (el) { el.remove(); });
      document.querySelectorAll('.lb-row-active').forEach(function (el) { el.classList.remove('lb-row-active'); });
      renderRows();
    }

    if (btnPoints) btnPoints.addEventListener('click', function () { setSort('points'); });
    if (btnSends)  btnSends.addEventListener('click',  function () { setSort('sends'); });

    function renderRows() {
      sortRows();
      body.innerHTML = '';
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="4" class="lb-empty">No users added yet.</td></tr>';
        return;
      }
      rows.forEach(function (row, i) {
        var tr = document.createElement('tr');
        tr.className = 'lb-row';
        tr.innerHTML =
          '<td class="lb-rank">' + (i + 1) + '</td>'
          + '<td class="lb-username">' + esc(row.username) + '</td>'
          + '<td class="lb-points">' + Math.round(row.points) + '</td>'
          + '<td class="lb-sends">' + row.ascents.length + '</td>';

        tr.addEventListener('click', function () {
          var existing = document.getElementById('detail-' + i);
          if (existing) {
            existing.remove();
            tr.classList.remove('lb-row-active');
            return;
          }
          document.querySelectorAll('.lb-detail-row').forEach(function (el) { el.remove(); });
          document.querySelectorAll('.lb-row-active').forEach(function (el) { el.classList.remove('lb-row-active'); });
          tr.classList.add('lb-row-active');
          renderDetail(tr, i, row, gradeVals, gradeTotals);
        });

        body.appendChild(tr);
      });
    }

    renderRows();
  }

  var GRADE_ORDER = ['V0','V1','V2','V3','V4','V5','V6','V7','V8','V9',
                     'V10','V11','V12','V13','V14','V15','V16'];

  function renderDetail(tr, idx, row, gradeVals, gradeTotals) {
    // Group user's sends by grade
    var byGrade = {};
    row.ascents.forEach(function (a) {
      if (!byGrade[a.grade]) byGrade[a.grade] = [];
      byGrade[a.grade].push(a);
    });

    var gradesWithSends = GRADE_ORDER.filter(function (g) { return byGrade[g]; }).reverse();

    var gradeRowsHtml = gradesWithSends.map(function (g) {
      var sends = byGrade[g];
      var total = gradeTotals[g] || 0;
      var pts   = Math.round(sends.length * (gradeVals[g] || 0));
      var pct   = total ? Math.round(100 * sends.length / total) : 0;
      return '<div class="lb-grade-row">'
        + '<span class="lb-grade-label">' + esc(g) + '</span>'
        + '<span class="lb-grade-bar-wrap"><span class="lb-grade-bar" style="width:' + pct + '%"></span></span>'
        + '<span class="lb-grade-stat">' + sends.length + '/' + total + '</span>'
        + '<span class="lb-grade-pts">' + pts + ' pts</span>'
        + '</div>';
    }).join('');

    var sortedAscents = row.ascents.slice().sort(function (a, b) {
      return GRADE_ORDER.indexOf(b.grade) - GRADE_ORDER.indexOf(a.grade)
          || a.name.localeCompare(b.name);
    });

    var ascentListHtml = sortedAscents.map(function (a) {
      var href = a.boulder_url ? a.boulder_url + '#' + a.id : '#';
      return '<li class="lb-ascent-item">'
        + '<a class="lb-ascent-link" href="' + esc(href) + '">' + esc(a.name) + '</a>'
        + '<span class="lb-ascent-grade">' + esc(a.grade) + '</span>'
        + '</li>';
    }).join('');

    var detail = document.createElement('tr');
    detail.id = 'detail-' + idx;
    detail.className = 'lb-detail-row';

    var gradeSection = gradeRowsHtml || '<p class="lb-empty-sub">No sends yet.</p>';
    var ascentSection = ascentListHtml
      ? '<ul class="lb-ascent-list">' + ascentListHtml + '</ul>'
      : '<p class="lb-empty-sub">No sends yet.</p>';

    var td = document.createElement('td');
    td.colSpan = 4;
    td.className = 'lb-detail-cell';
    td.innerHTML =
      '<div class="lb-detail-inner">'
      + '<h3 class="lb-detail-name">' + esc(row.username) + '</h3>'
      + '<div class="lb-detail-cols">'
      +   '<div class="lb-detail-grades">'
      +     '<h4 class="lb-detail-section-title">By Grade</h4>'
      +     gradeSection
      +   '</div>'
      +   '<div class="lb-detail-list">'
      +     '<h4 class="lb-detail-section-title">All Sends</h4>'
      +     ascentSection
      +   '</div>'
      + '</div>'
      + '</div>';

    detail.appendChild(td);
    tr.insertAdjacentElement('afterend', detail);
  }

  function esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // Scripts are at end of body so DOM is already ready — call directly
  render();

})();
