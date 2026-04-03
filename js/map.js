/* map.js — Leaflet map init for index.html */
(function () {
  var map = L.map('map', {
    center: [40.5718, -111.7731],
    zoom: 15,
    zoomControl: true,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  // ── Pre-compute lookups ────────────────────────────────────────────────────
  var boulderByUrl = {};
  (window.BOULDERS || []).forEach(function (b) { if (b.url) boulderByUrl[b.url] = b; });

  var subCentroids = {};
  (window.BOULDERS || []).forEach(function (b) {
    if (!b.latitude || !b.subarea_id) return;
    if (!subCentroids[b.subarea_id]) subCentroids[b.subarea_id] = { s_lat: 0, s_lng: 0, n: 0 };
    subCentroids[b.subarea_id].s_lat += parseFloat(b.latitude);
    subCentroids[b.subarea_id].s_lng += parseFloat(b.longitude);
    subCentroids[b.subarea_id].n++;
  });

  // ── Helpers ────────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function dotLabel(dotSize, dotColor, labelText, labelSize) {
    return '<div style="position:relative;display:inline-block">'
      + '<div style="width:' + dotSize + 'px;height:' + dotSize + 'px;background:' + dotColor
      + ';border:1.5px solid #000;border-radius:50%;box-shadow:0 0 4px rgba(0,0,0,0.7)"></div>'
      + '<div style="position:absolute;top:50%;left:' + (dotSize + 4) + 'px;transform:translateY(-50%);'
      + 'white-space:nowrap;font-size:' + labelSize + 'px;font-family:sans-serif;font-weight:600;color:#eee;'
      + 'text-shadow:0 0 3px #000,0 0 3px #000,1px 1px 0 #000,-1px -1px 0 #000;'
      + 'pointer-events:none;line-height:1">' + esc(labelText) + '</div></div>';
  }

  // ── Area markers (gold — always visible) ──────────────────────────────────
  var areaIcon = L.divIcon({
    className: '',
    html: '<div style="width:14px;height:14px;background:#c8a96e;border:2px solid #111;border-radius:50%;box-shadow:0 0 6px rgba(0,0,0,0.7)"></div>',
    iconSize: [14, 14], iconAnchor: [7, 7], popupAnchor: [0, -10],
  });
  (window.AREAS || []).forEach(function (a) {
    var lat = parseFloat(a.latitude), lng = parseFloat(a.longitude);
    if (!lat || !lng) return;
    L.marker([lat, lng], { icon: areaIcon }).addTo(map).bindPopup(
      '<div style="font-family:sans-serif;min-width:160px">'
      + '<div style="font-weight:700;font-size:14px;margin-bottom:4px;color:#c8a96e">' + esc(a.name) + '</div>'
      + '<div style="font-size:12px;color:#777;margin-bottom:8px">' + a.problemCount + ' problems &middot; ' + a.gradeRange + '</div>'
      + '<a href="' + a.url + '" style="font-size:12px;color:#c8a96e;font-weight:600">View Area &rarr;</a>'
      + '</div>'
    );
  });

  // ── Subarea markers (teal + label — zoom 14–15) ───────────────────────────
  var subLayer = L.layerGroup();
  (window.SUBAREAS || []).forEach(function (s) {
    var c = subCentroids[s.id];
    if (!c) return;
    var lat = c.s_lat / c.n, lng = c.s_lng / c.n;
    L.marker([lat, lng], { icon: L.divIcon({ className: '', html: dotLabel(8, '#7ec8a4', s.name, 10), iconSize: [8, 8], iconAnchor: [4, 4], popupAnchor: [0, -7] }) })
      .bindPopup(
        '<div style="font-family:sans-serif;min-width:140px">'
        + '<div style="font-weight:700;font-size:13px;margin-bottom:2px;color:#7ec8a4">' + esc(s.name) + '</div>'
        + '<div style="font-size:11px;color:#999;margin-bottom:4px">' + esc(s.area_name) + '</div>'
        + '<div style="font-size:11px;color:#777;margin-bottom:6px">' + s.boulder_count + ' boulders</div>'
        + '<a href="' + s.url + '" style="font-size:11px;color:#c8a96e;font-weight:600">View &rarr;</a>'
        + '</div>'
      ).addTo(subLayer);
  });

  // ── Boulder markers (orange + label — zoom 16+) ───────────────────────────
  var bldLayer = L.layerGroup();
  var boulderMarkerByUrl = {};
  (window.BOULDERS || []).forEach(function (b) {
    var lat = parseFloat(b.latitude), lng = parseFloat(b.longitude);
    if (!lat || !lng) return;
    var m = L.marker([lat, lng], { icon: L.divIcon({ className: '', html: dotLabel(6, '#e8803c', b.name, 9), iconSize: [6, 6], iconAnchor: [3, 3], popupAnchor: [0, -5] }) })
      .bindPopup(
        '<div style="font-family:sans-serif;min-width:130px">'
        + '<div style="font-weight:700;font-size:12px;margin-bottom:2px;color:#e8803c">' + esc(b.name) + '</div>'
        + '<div style="font-size:11px;color:#999;margin-bottom:2px">' + esc(b.subarea_name) + ' · ' + esc(b.area_name) + '</div>'
        + '<div style="font-size:11px;color:#777;margin-bottom:5px">' + (b.climb_count || 0) + ' climbs</div>'
        + '<a href="' + (b.url || b.subarea_url) + '" style="font-size:11px;color:#c8a96e;font-weight:600">View Boulder &rarr;</a>'
        + '</div>'
      ).addTo(bldLayer);
    if (b.url) boulderMarkerByUrl[b.url] = m;
  });

  // ── Zoom-based layer visibility ────────────────────────────────────────────
  function updateLayers() {
    var z = map.getZoom();
    if (z >= 16)      { map.removeLayer(subLayer); map.addLayer(bldLayer); }
    else if (z >= 14) { map.addLayer(subLayer);    map.removeLayer(bldLayer); }
    else              { map.removeLayer(subLayer);  map.removeLayer(bldLayer); }
  }
  map.on('zoomend', updateLayers);
  updateLayers();

  // ── Map search control ─────────────────────────────────────────────────────
  var SearchControl = L.Control.extend({
    options: { position: 'topright' },
    onAdd: function () {
      var c = L.DomUtil.create('div', 'map-search-control');
      L.DomEvent.disableClickPropagation(c);
      L.DomEvent.disableScrollPropagation(c);
      c.innerHTML =
        '<div class="map-search-input-wrap">'
        + '<svg class="map-search-icon" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">'
        + '<circle cx="8.5" cy="8.5" r="5" stroke="#9a9a9a" stroke-width="1.5"/>'
        + '<line x1="12.5" y1="12.5" x2="17" y2="17" stroke="#9a9a9a" stroke-width="1.5" stroke-linecap="round"/>'
        + '</svg>'
        + '<input type="text" id="map-search-input" placeholder="Search areas, boulders, climbs\u2026" autocomplete="off">'
        + '<button id="map-search-clear" title="Clear">&times;</button>'
        + '</div>'
        + '<ul id="map-search-results"></ul>';
      return c;
    }
  });
  new SearchControl().addTo(map);

  var inp     = document.getElementById('map-search-input');
  var resList = document.getElementById('map-search-results');
  var clearBtn = document.getElementById('map-search-clear');
  var currentResults = [];
  var activeIdx = -1;
  var debounceTimer;

  function problemAnchor(name) {
    return 'problem-' + name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }

  var TYPE_COLOR = { area: '#c8a96e', subarea: '#7ec8a4', boulder: '#e8803c', climb: '#cccccc' };

  function selectResult(r) {
    if (!r) return;
    inp.value = r.label;
    resList.style.display = 'none';
    clearBtn.style.display = 'block';
    map.flyTo([r.lat, r.lng], r.zoom, { duration: 0.9 });
    if (r.type === 'boulder' || r.type === 'climb') {
      var boulderUrl = r.type === 'climb'
        ? (r.link ? r.link.split('#')[0] : null)
        : r.link;
      var marker = boulderUrl ? boulderMarkerByUrl[boulderUrl] : null;
      if (marker) {
        map.once('moveend', function () { marker.openPopup(); });
      }
    } else {
      L.popup({ offset: [0, -4], className: 'map-search-popup' })
        .setLatLng([r.lat, r.lng])
        .setContent(
          '<div style="font-family:sans-serif;min-width:150px">'
          + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#888;margin-bottom:3px">' + r.typeLabel + '</div>'
          + '<div style="font-weight:700;font-size:14px;color:' + TYPE_COLOR[r.type] + ';margin-bottom:4px">' + esc(r.label) + '</div>'
          + '<div style="font-size:11px;color:#999;margin-bottom:6px">' + esc(r.sub) + '</div>'
          + (r.link ? '<a href="' + r.link + '" style="font-size:12px;color:#c8a96e;font-weight:600">View &rarr;</a>' : '')
          + '</div>'
        )
        .openOn(map);
    }
  }

  function renderResults(results) {
    currentResults = results;
    activeIdx = -1;
    if (!results.length) {
      resList.innerHTML = '<li class="map-search-no-results">No results found</li>';
    } else {
      resList.innerHTML = results.map(function (r, i) {
        return '<li data-idx="' + i + '">'
          + '<span class="msr-badge msr-' + r.type + '">' + r.typeLabel + '</span>'
          + '<span class="msr-label">' + esc(r.label) + '</span>'
          + '<span class="msr-sub">' + esc(r.sub) + '</span>'
          + '</li>';
      }).join('');
    }
    resList.style.display = 'block';
  }

  function doSearch(q) {
    if (!q || q.length < 2) { resList.style.display = 'none'; return; }
    var qLow = q.toLowerCase();
    var results = [];

    function score(name) {
      var n = name.toLowerCase();
      return n === qLow ? 0 : n.indexOf(qLow) === 0 ? 1 : 2;
    }

    (window.AREAS || []).forEach(function (a) {
      if (!a.latitude || a.name.toLowerCase().indexOf(qLow) === -1) return;
      results.push({ type: 'area', typeLabel: 'Area', typeOrder: 0, label: a.name,
        sub: a.problemCount + ' problems', score: score(a.name),
        lat: parseFloat(a.latitude), lng: parseFloat(a.longitude), zoom: 13, link: a.url });
    });

    (window.SUBAREAS || []).forEach(function (s) {
      if (s.name.toLowerCase().indexOf(qLow) === -1) return;
      var c = subCentroids[s.id];
      if (!c) return;
      results.push({ type: 'subarea', typeLabel: 'Subarea', typeOrder: 1, label: s.name,
        sub: s.area_name, score: score(s.name),
        lat: c.s_lat / c.n, lng: c.s_lng / c.n, zoom: 15, link: s.url });
    });

    (window.BOULDERS || []).forEach(function (b) {
      if (!b.latitude || b.name.toLowerCase().indexOf(qLow) === -1) return;
      results.push({ type: 'boulder', typeLabel: 'Boulder', typeOrder: 2, label: b.name,
        sub: b.subarea_name, score: score(b.name),
        lat: parseFloat(b.latitude), lng: parseFloat(b.longitude), zoom: 19, link: b.url || b.subarea_url });
    });

    (window.PROBLEMS || []).forEach(function (p) {
      if (p.name.toLowerCase().indexOf(qLow) === -1) return;
      var b = boulderByUrl[p.boulder_url];
      if (!b || !b.latitude) return;
      results.push({ type: 'climb', typeLabel: 'Climb', typeOrder: 3, label: p.name,
        sub: (p.gradeLabel || 'V?') + ' · ' + (p.boulder_name || ''), score: score(p.name),
        lat: parseFloat(b.latitude), lng: parseFloat(b.longitude), zoom: 19,
        link: p.boulder_url ? p.boulder_url + '#' + problemAnchor(p.name) : null });
    });

    results.sort(function (a, b) {
      return a.score !== b.score ? a.score - b.score : a.typeOrder - b.typeOrder;
    });

    renderResults(results.slice(0, 10));
  }

  inp.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    clearBtn.style.display = inp.value ? 'block' : 'none';
    debounceTimer = setTimeout(function () { doSearch(inp.value.trim()); }, 150);
  });

  inp.addEventListener('keydown', function (e) {
    var items = resList.querySelectorAll('li[data-idx]');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      selectResult(currentResults[activeIdx >= 0 ? activeIdx : 0]);
      return;
    } else if (e.key === 'Escape') {
      resList.style.display = 'none';
      return;
    }
    items.forEach(function (li, i) { li.classList.toggle('active', i === activeIdx); });
  });

  resList.addEventListener('mousedown', function (e) {
    var li = e.target.closest('li[data-idx]');
    if (li) selectResult(currentResults[parseInt(li.dataset.idx, 10)]);
  });

  clearBtn.addEventListener('mousedown', function () {
    inp.value = '';
    clearBtn.style.display = 'none';
    resList.style.display = 'none';
    map.closePopup();
    inp.focus();
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest('.map-search-control')) resList.style.display = 'none';
  });

})();
