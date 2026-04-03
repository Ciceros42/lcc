/* leaderboard.js — Fetches ascents from Supabase, computes points, renders leaderboard.
   Requires: supabase-js CDN, config.js, data/users.js (window.USERS), data/problems.js (window.PROBLEMS)
*/
(function () {
  'use strict';

  var sb = window.supabase.createClient(window.LCC_SUPABASE_URL, window.LCC_SUPABASE_KEY);

  // total grade value = 500 * 1.3^n  (n = V-number; VB and V? = 0 points)
  function gradeExponent(label) {
    if (!label) return null;
    var m = label.match(/^V(\d+)$/i);
    if (m) return parseInt(m[1], 10);
    return null;
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

  function buildGradeTotals() {
    var counts = {};
    (window.PROBLEMS || []).forEach(function (p) {
      if (p.gradeLabel) counts[p.gradeLabel] = (counts[p.gradeLabel] || 0) + 1;
    });
    return counts;
  }

  async function loadAndRender() {
    var loading = document.getElementById('leaderboard-loading');
    var body    = document.getElementById('leaderboard-body');
    if (!body) return;

    var res = await sb.from('ascents').select('username, climb_id, climb_name, grade_label, boulder_url');
    if (res.error) {
      if (loading) loading.textContent = 'Failed to load leaderboard. Please refresh.';
      console.error(res.error);
      return;
    }

    var gradeVals   = buildGradeValues();
    var gradeTotals = buildGradeTotals();
    var users       = window.USERS || [];

    // Group ascents by username
    var byUser = {};
    users.forEach(function (u) { byUser[u] = []; });
    res.data.forEach(function (row) {
      if (byUser[row.username]) byUser[row.username].push(row);
    });

    var rows = users.map(function (username) {
      var ascents = byUser[username];
      var points  = ascents.reduce(function (sum, a) {
        return sum + (gradeVals[a.grade_label] || 0);
      }, 0);
      return { username: username, ascents: ascents, points: points };
    });

    if (loading) loading.style.display = 'none';

    var sortMode = 'points';

    function sortRows() {
      if (sortMode === 'sends') {
        rows.sort(function (a, b) {
          return b.ascents.length !== a.ascents.length
            ? b.ascents.length - a.ascents.length
            : b.points - a.points;
        });
      } else {
        rows.sort(function (a, b) {
          return b.points !== a.points
            ? b.points - a.points
            : b.ascents.length - a.ascents.length;
        });
      }
    }

    var btnPoints = document.getElementById('sort-points');
    var btnSends  = document.getElementById('sort-sends');

    function setSort(mode) {
      sortMode = mode;
      if (btnPoints) btnPoints.classList.toggle('lb-sort-active', mode === 'points');
      if (btnSends)  btnSends.classList.toggle('lb-sort-active', mode === 'sends');
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
          '<td class="lb-rank">'     + (i + 1) + '</td>'
          + '<td class="lb-username">' + esc(row.username) + '</td>'
          + '<td class="lb-points">'   + Math.round(row.points) + '</td>'
          + '<td class="lb-sends">'    + row.ascents.length + '</td>';

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

  var GRADE_ORDER = ['VB','V?','V0','V1','V2','V3','V4','V5','V6','V7','V8','V9',
                     'V10','V11','V12','V13','V14','V15','V16'];

  function renderDetail(tr, idx, row, gradeVals, gradeTotals) {
    var byGrade = {};
    row.ascents.forEach(function (a) {
      if (!byGrade[a.grade_label]) byGrade[a.grade_label] = [];
      byGrade[a.grade_label].push(a);
    });

    var gradesWithSends = GRADE_ORDER.filter(function (g) { return byGrade[g]; }).reverse();

    var gradeRowsHtml = gradesWithSends.map(function (g) {
      var sends = byGrade[g];
      var total = gradeTotals[g] || 0;
      var pts   = Math.round(sends.length * (gradeVals[g] || 0));
      var pct   = total ? Math.round(100 * sends.length / total) : 0;
      return '<div class="lb-grade-row">'
        + '<span class="lb-grade-label">'    + esc(g) + '</span>'
        + '<span class="lb-grade-bar-wrap"><span class="lb-grade-bar" style="width:' + pct + '%"></span></span>'
        + '<span class="lb-grade-stat">'     + sends.length + '/' + total + '</span>'
        + '<span class="lb-grade-pts">'      + pts + ' pts</span>'
        + '</div>';
    }).join('');

    var sortedAscents = row.ascents.slice().sort(function (a, b) {
      return GRADE_ORDER.indexOf(b.grade_label) - GRADE_ORDER.indexOf(a.grade_label)
          || a.climb_name.localeCompare(b.climb_name);
    });

    var ascentListHtml = sortedAscents.map(function (a) {
      var href = a.boulder_url ? a.boulder_url + '#' + a.climb_id : '#';
      return '<li class="lb-ascent-item">'
        + '<a class="lb-ascent-link" href="' + esc(href) + '">' + esc(a.climb_name) + '</a>'
        + '<span class="lb-ascent-grade">' + esc(a.grade_label) + '</span>'
        + '</li>';
    }).join('');

    var gradeSection  = gradeRowsHtml || '<p class="lb-empty-sub">No sends yet.</p>';
    var ascentSection = ascentListHtml
      ? '<ul class="lb-ascent-list">' + ascentListHtml + '</ul>'
      : '<p class="lb-empty-sub">No sends yet.</p>';

    var detail = document.createElement('tr');
    detail.id = 'detail-' + idx;
    detail.className = 'lb-detail-row';

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

  loadAndRender();

})();
