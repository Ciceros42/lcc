/* search.js — Client-side problem search for index.html */
(function () {
  var nameInput    = document.getElementById('search-name');
  var minSelect    = document.getElementById('grade-min');
  var maxSelect    = document.getElementById('grade-max');
  var clearBtn     = document.getElementById('search-clear');
  var resultsBox   = document.getElementById('search-results');
  var resultsList  = document.getElementById('results-list');
  var resultsCount = document.getElementById('results-count');

  // V? (ungraded) and VB (beginner) are below V0
  var GRADES = ['V?','VB','V0','V1','V2','V3','V4','V5','V6','V7','V8','V9','V10',
                'V11','V12','V13','V14','V15','V16','V17'];
  var gradeIndex = {};
  GRADES.forEach(function (g, i) { gradeIndex[g] = i; });

  function buildSelects() {
    GRADES.forEach(function (g, i) {
      minSelect.appendChild(new Option(g, i));
      maxSelect.appendChild(new Option(g, i));
    });
    minSelect.value = 0;
    maxSelect.value = GRADES.length - 1;
  }

  function stars(n) {
    var s = '';
    for (var i = 0; i < 3; i++) s += i < n ? '★' : '☆';
    return s;
  }

  function problemAnchor(name) {
    return 'problem-' + name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }

  function runSearch() {
    var query    = nameInput.value.trim().toLowerCase();
    var minGrade = parseInt(minSelect.value, 10);
    var maxGrade = parseInt(maxSelect.value, 10);

    if (minGrade > maxGrade) { var t = minGrade; minGrade = maxGrade; maxGrade = t; }

    var hasFilter = query.length > 0 || minGrade > 0 || maxGrade < GRADES.length - 1;
    if (!hasFilter) { resultsBox.classList.remove('active'); return; }

    var filtered = (window.PROBLEMS || []).filter(function (p) {
      var nameMatch = query.length === 0 || p.name.toLowerCase().indexOf(query) !== -1;
      var gl = (p.gradeLabel || 'V?').toString().toUpperCase();
      if (gl !== 'V?' && gl !== 'VB' && !gl.startsWith('V')) gl = 'V' + gl;
      var gi = gradeIndex[gl];
      if (gi === undefined) gi = gradeIndex['V?'];
      var gradeMatch = gi >= minGrade && gi <= maxGrade;
      return nameMatch && gradeMatch;
    });

    resultsBox.classList.add('active');
    resultsCount.textContent = filtered.length + ' problem' + (filtered.length !== 1 ? 's' : '') + ' found';

    if (filtered.length === 0) {
      resultsList.innerHTML = '<p class="no-results">No problems match your search.</p>';
      return;
    }

    resultsList.innerHTML = '';
    filtered.forEach(function (p) {
      var href = p.boulder_url
        ? p.boulder_url + '#' + problemAnchor(p.name)
        : (p.subarea_url || '#');
      var li = document.createElement('li');
      li.className = 'result-item';
      li.innerHTML =
        '<a href="' + href + '">' + p.name + '</a>' +
        '<span class="grade-badge">' + (p.gradeLabel || 'V?') + '</span>' +
        '<span class="stars">' + stars(Math.round(p.stars || 0)) + '</span>' +
        '<span class="result-location">' + (p.subarea || p.area || '') + ' &mdash; ' + (p.area || '') + '</span>';
      resultsList.appendChild(li);
    });
  }

  function clearSearch() {
    nameInput.value = '';
    minSelect.value = 0;
    maxSelect.value = GRADES.length - 1;
    resultsBox.classList.remove('active');
  }

  buildSelects();
  nameInput.addEventListener('input', runSearch);
  minSelect.addEventListener('change', runSearch);
  maxSelect.addEventListener('change', runSearch);
  clearBtn.addEventListener('click', clearSearch);
})();
