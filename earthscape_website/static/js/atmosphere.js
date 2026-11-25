/* EarthScape atmosphere: weather-driven theme, particle effects, week strip and fallback globe.
   Frontend only. It reads Open-Meteo straight from the browser, so no backend route is touched. */
(function () {
  'use strict';

  const CITIES = {
    karachi: { n: 'Karachi', c: 'Pakistan', lat: 24.8607, lon: 67.0011 },
    dubai: { n: 'Dubai', c: 'UAE', lat: 25.2048, lon: 55.2708 },
    mumbai: { n: 'Mumbai', c: 'India', lat: 19.0760, lon: 72.8777 },
    london: { n: 'London', c: 'UK', lat: 51.5072, lon: -0.1276 },
    moscow: { n: 'Moscow', c: 'Russia', lat: 55.7558, lon: 37.6173 },
    new_york: { n: 'New York', c: 'USA', lat: 40.7128, lon: -74.0060 },
    tokyo: { n: 'Tokyo', c: 'Japan', lat: 35.6762, lon: 139.6503 },
    sydney: { n: 'Sydney', c: 'Australia', lat: -33.8688, lon: 151.2093 }
  };
  const KEYS = Object.keys(CITIES);

  const META = {
    hot: { label: 'Intense heat', icon: 'bi-thermometer-sun' },
    clear: { label: 'Clear skies', icon: 'bi-sun' },
    night: { label: 'Clear night', icon: 'bi-moon-stars' },
    cloud: { label: 'Cloudy', icon: 'bi-cloud' },
    fog: { label: 'Fog and haze', icon: 'bi-cloud-fog2' },
    rain: { label: 'Rain', icon: 'bi-cloud-rain-heavy' },
    storm: { label: 'Thunderstorms', icon: 'bi-cloud-lightning-rain' },
    snow: { label: 'Snowfall', icon: 'bi-cloud-snow' }
  };

  // Used only when the browser cannot reach Open-Meteo. Shown with a "sample" badge.
  const DEMO = {
    karachi: [38, 0, 1], dubai: [42, 0, 1], mumbai: [29, 63, 1], london: [11, 61, 1],
    moscow: [-4, 73, 1], new_york: [9, 3, 1], tokyo: [18, 1, 1], sydney: [22, 95, 1]
  };

  const reduceMotion = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const num = (v, d) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(d == null ? 0 : d));

  function classify(code, temp, isDay) {
    if ([95, 96, 99].includes(code)) return 'storm';
    if ([71, 73, 75, 77, 85, 86].includes(code)) return 'snow';
    if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return 'rain';
    if ([45, 48].includes(code)) return 'fog';
    if (isDay && temp >= 36) return 'hot';
    if (code <= 1) return isDay ? 'clear' : 'night';
    return 'cloud';
  }

  /* ---------- data ---------- */
  let store = {}, storeAt = 0, inflight = null;

  function demoFor(key) {
    const d = DEMO[key], t = d[0];
    const days = [], today = new Date();
    for (let i = 0; i < 7; i++) {
      const dt = new Date(today); dt.setDate(today.getDate() + i);
      days.push({ date: dt, tmax: Math.round(t + Math.sin(i * 1.3) * 3), code: i % 3 === 2 && d[1] > 50 ? 3 : d[1] });
    }
    return { key, temp: t, feels: t, humidity: null, wind: null, code: d[1], isDay: true, cond: classify(d[1], t, true), days, live: false };
  }

  function fetchAll() {
    if (inflight) return inflight;
    if (Date.now() - storeAt < 240000 && Object.keys(store).length) return Promise.resolve(store);
    const lat = KEYS.map(k => CITIES[k].lat).join(',');
    const lon = KEYS.map(k => CITIES[k].lon).join(',');
    const url = 'https://api.open-meteo.com/v1/forecast?latitude=' + lat + '&longitude=' + lon +
      '&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,is_day' +
      '&daily=weather_code,temperature_2m_max&forecast_days=7&timezone=auto&wind_speed_unit=kmh';
    inflight = fetch(url).then(r => { if (!r.ok) throw new Error('weather ' + r.status); return r.json(); })
      .then(arr => {
        arr = Array.isArray(arr) ? arr : [arr];
        const out = {};
        arr.forEach((p, i) => {
          const key = KEYS[i], c = p.current || {}, d = p.daily || {};
          const days = (d.time || []).map((t, j) => ({ date: new Date(t + 'T12:00:00'), tmax: d.temperature_2m_max[j], code: d.weather_code[j] }));
          out[key] = {
            key, temp: c.temperature_2m, feels: c.apparent_temperature, humidity: c.relative_humidity_2m,
            wind: c.wind_speed_10m, code: c.weather_code, isDay: c.is_day === 1,
            cond: classify(c.weather_code, c.temperature_2m, c.is_day === 1), days, live: true
          };
        });
        store = out; storeAt = Date.now(); return store;
      })
      .catch(() => {
        const out = {}; KEYS.forEach(k => { out[k] = demoFor(k); });
        store = out; storeAt = Date.now(); return store;
      })
      .finally(() => { inflight = null; });
    return inflight;
  }

  /* ---------- state ---------- */
  let current = 'karachi', cond = 'clear';
  try { const s = localStorage.getItem('earthscapeWeatherCity'); if (s && CITIES[s]) current = s; } catch (_) { }

  function applyCondition(c) {
    cond = c;
    document.body.dataset.weather = c;
    fx.setMode(c);
  }

  function bind(data) {
    const d = data[current]; if (!d) return;
    applyCondition(d.cond);
    const meta = META[d.cond], city = CITIES[current];
    const set = (name, val) => $$('[data-wx="' + name + '"]').forEach(el => { el.textContent = val; });
    set('temp', num(d.temp)); set('city', city.n); set('country', city.c); set('label', meta.label);
    set('feels', num(d.feels)); set('tmax', d.days && d.days[0] ? num(d.days[0].tmax) : '—'); set('humidity', d.humidity == null ? '—' : num(d.humidity));
    set('wind', d.wind == null ? '—' : num(d.wind)); set('source', d.live ? 'Live · Open-Meteo' : 'Sample data · offline');
    $$('[data-wx="icon"]').forEach(el => { el.className = 'bi ' + meta.icon; });
    renderChips(data); renderWeek(d); renderMenu(data); renderCards(data);
  }

  function useCity(key, silent) {
    if (!CITIES[key]) return;
    current = key;
    try { localStorage.setItem('earthscapeWeatherCity', key); } catch (_) { }
    const sel = $('#liveWeatherCity');
    if (sel && sel.value !== key && Array.from(sel.options).some(o => o.value === key)) {
      sel.value = key; if (!silent) sel.dispatchEvent(new Event('change'));
    }
    fetchAll().then(bind);
  }

  /* ---------- UI renderers ---------- */
  function renderChips(data) {
    $$('[data-wx-chips]').forEach(box => {
      box.innerHTML = '';
      KEYS.forEach(k => {
        const d = data[k], b = document.createElement('button');
        b.type = 'button'; b.className = 'wx-pill cond-' + d.cond + (k === current ? ' on' : '');
        b.setAttribute('aria-pressed', k === current ? 'true' : 'false');
        b.innerHTML = '<i class="bi ' + META[d.cond].icon + '"></i><span class="wx-pill-name">' + CITIES[k].n +
          '</span><span class="wx-pill-temp">' + num(d.temp) + '°</span>';
        b.addEventListener('click', () => useCity(k));
        box.appendChild(b);
      });
    });
  }

  function renderMenu(data) {
    $$('[data-wx-menu]').forEach(menu => {
      menu.innerHTML = '';
      KEYS.forEach(k => {
        const d = data[k], li = document.createElement('li');
        li.innerHTML = '<button type="button" class="dropdown-item wx-item' + (k === current ? ' active' : '') + '"><i class="bi ' +
          META[d.cond].icon + '"></i><span>' + CITIES[k].n + '</span><b>' + num(d.temp) + '°</b></button>';
        li.firstChild.addEventListener('click', () => useCity(k));
        menu.appendChild(li);
      });
    });
  }

  function renderCards(data) {
    $$('[data-live-weather-city]').forEach(card => {
      const d = data[card.dataset.liveWeatherCity]; if (!d) return;
      card.className = card.className.replace(/\bcond-\w+/g, '').trim() + ' cond-' + d.cond;
      const tag = $('[data-cond-tag]', card); if (tag) tag.textContent = META[d.cond].label;
      const ic = $('[data-cond-icon]', card); if (ic) ic.className = 'bi ' + META[d.cond].icon;
    });
  }

  function renderWeek(d) {
    $$('[data-week]').forEach(box => {
      const days = d.days.slice(0, 7); if (!days.length) return;
      const temps = days.map(x => x.tmax), lo = Math.min.apply(null, temps), hi = Math.max.apply(null, temps);
      const H = 74, span = Math.max(hi - lo, 4);
      const ys = temps.map(t => 10 + (1 - (t - lo) / span) * (H - 24));
      const n = days.length;
      let cols = '';
      days.forEach((x, i) => {
        const c = classify(x.code, x.tmax, true);
        cols += '<div class="wk-col"><span class="wk-day">' + x.date.toLocaleDateString('en-GB', { weekday: 'short' }) +
          '</span><span class="wk-temp">' + num(x.tmax) + '°</span><span class="wk-dot cond-' + c + '" style="margin-top:' + (ys[i] + 8) +
          'px"><i class="bi ' + META[c].icon + '"></i></span></div>';
      });
      let path = '';
      ys.forEach((y, i) => {
        const x = ((i + .5) / n) * 1000, cy = y + 16;
        if (!i) path += 'M' + x + ',' + cy;
        else { const px = ((i - .5) / n) * 1000, py = ys[i - 1] + 16, mx = (px + x) / 2; path += ' C' + mx + ',' + py + ' ' + mx + ',' + cy + ' ' + x + ',' + cy; }
      });
      box.innerHTML = '<svg class="wk-line" viewBox="0 0 1000 ' + (H + 40) + '" preserveAspectRatio="none" aria-hidden="true"><path d="' + path +
        '" vector-effect="non-scaling-stroke"/></svg><div class="wk-cols" style="--wk-h:' + (H + 40) + 'px">' + cols + '</div>';
      box.style.setProperty('--wk-svg-top', '60px');
    });
  }

  /* ---------- effects canvas ---------- */
  const fx = (function () {
    const canvas = document.createElement('canvas');
    canvas.className = 'fx-canvas'; canvas.setAttribute('aria-hidden', 'true');
    const flash = document.createElement('div'); flash.className = 'sky-flash'; flash.setAttribute('aria-hidden', 'true');
    const ctx = canvas.getContext('2d');
    let W = 0, H = 0, dpr = 1, mode = 'clear', parts = [], raf = 0, last = 0, nextBolt = 0;

    function mount() {
      const sky = document.createElement('div'); sky.className = 'sky'; sky.setAttribute('aria-hidden', 'true');
      document.body.prepend(canvas); document.body.prepend(flash); document.body.prepend(sky);
      resize(); addEventListener('resize', resize);
      document.addEventListener('visibilitychange', () => { document.hidden ? stop() : start(); });
    }
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = innerWidth; H = innerHeight;
      canvas.width = W * dpr; canvas.height = H * dpr;
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); seed();
    }
    const rnd = (a, b) => a + Math.random() * (b - a);

    function seed() {
      parts = []; const area = W * H;
      if (mode === 'rain' || mode === 'storm') {
        const n = Math.round(area / (mode === 'storm' ? 4200 : 7500));
        for (let i = 0; i < n; i++) parts.push({ x: rnd(0, W + 200), y: rnd(0, H), l: rnd(12, 30), v: rnd(700, 1100), a: rnd(.18, .5) });
      } else if (mode === 'snow') {
        const n = Math.round(area / 9000);
        for (let i = 0; i < n; i++) parts.push({ x: rnd(0, W), y: rnd(0, H), r: rnd(1, 3.6), v: rnd(28, 70), ph: rnd(0, 6.28), a: rnd(.35, .9) });
      } else if (mode === 'hot') {
        const n = Math.round(area / 16000);
        for (let i = 0; i < n; i++) parts.push({ x: rnd(0, W), y: rnd(0, H), r: rnd(1, 2.8), v: rnd(14, 46), ph: rnd(0, 6.28), a: rnd(.2, .6) });
      } else if (mode === 'cloud' || mode === 'fog') {
        const n = mode === 'fog' ? 9 : 7;
        for (let i = 0; i < n; i++) parts.push({ x: rnd(-200, W), y: rnd(0, H * .9), r: rnd(220, 460), v: rnd(6, 18), a: rnd(.05, mode === 'fog' ? .16 : .1) });
      } else {
        const n = Math.round(area / (mode === 'night' ? 5200 : 22000));
        for (let i = 0; i < n; i++) parts.push({ x: rnd(0, W), y: rnd(0, H), r: rnd(.5, mode === 'night' ? 1.5 : 2.2), ph: rnd(0, 6.28), s: rnd(.4, 1.4), a: rnd(.25, .8) });
      }
    }

    function bolt() {
      if (reduceMotion) return;
      flash.animate([{ opacity: 0 }, { opacity: .55 }, { opacity: .08 }, { opacity: .4 }, { opacity: 0 }], { duration: 650, easing: 'ease-out' });
    }

    function frame(t) {
      raf = requestAnimationFrame(frame);
      const dt = Math.min((t - last) / 1000, .05); last = t;
      ctx.clearRect(0, 0, W, H);
      if (mode === 'rain' || mode === 'storm') {
        ctx.lineWidth = 1; ctx.lineCap = 'round';
        const slant = mode === 'storm' ? .32 : .18;
        for (const p of parts) {
          p.y += p.v * dt; p.x -= p.v * slant * dt;
          if (p.y > H) { p.y = -p.l; p.x = rnd(0, W + 200); }
          if (p.x < -20) p.x += W + 40;
          ctx.strokeStyle = 'rgba(170,205,255,' + p.a + ')';
          ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + p.l * slant, p.y - p.l); ctx.stroke();
        }
        if (mode === 'storm' && t > nextBolt) { bolt(); nextBolt = t + rnd(3800, 9000); }
      } else if (mode === 'snow') {
        for (const p of parts) {
          p.y += p.v * dt; p.ph += dt; p.x += Math.sin(p.ph) * 16 * dt;
          if (p.y > H + 6) { p.y = -6; p.x = rnd(0, W); }
          ctx.fillStyle = 'rgba(235,246,255,' + p.a + ')';
          ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.283); ctx.fill();
        }
      } else if (mode === 'hot') {
        for (const p of parts) {
          p.y -= p.v * dt; p.ph += dt; p.x += Math.sin(p.ph * 1.4) * 10 * dt;
          if (p.y < -8) { p.y = H + 8; p.x = rnd(0, W); }
          const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 5);
          g.addColorStop(0, 'rgba(255,190,110,' + p.a + ')'); g.addColorStop(1, 'rgba(255,140,60,0)');
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 5, 0, 6.283); ctx.fill();
        }
      } else if (mode === 'cloud' || mode === 'fog') {
        for (const p of parts) {
          p.x += p.v * dt; if (p.x - p.r > W) p.x = -p.r;
          const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
          g.addColorStop(0, 'rgba(205,220,235,' + p.a + ')'); g.addColorStop(1, 'rgba(205,220,235,0)');
          ctx.fillStyle = g; ctx.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
        }
      } else {
        for (const p of parts) {
          p.ph += dt * p.s;
          const a = p.a * (.55 + .45 * Math.sin(p.ph * 2));
          ctx.fillStyle = (mode === 'night' ? 'rgba(200,215,255,' : 'rgba(190,230,255,') + a + ')';
          ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.283); ctx.fill();
        }
      }
    }
    function start() { if (!raf && !reduceMotion) { last = performance.now(); raf = requestAnimationFrame(frame); } }
    function stop() { cancelAnimationFrame(raf); raf = 0; }
    function setMode(m) { mode = m; seed(); nextBolt = performance.now() + 1500; ctx.clearRect(0, 0, W, H); start(); }
    return { mount, setMode };
  })();

  /* ---------- fallback globe (procedural, used when static/video/earth.mp4 is missing) ---------- */
  function startGlobe(canvas) {
    const S = 560, TW = 768, TH = 384;
    canvas.width = canvas.height = S;
    const ctx = canvas.getContext('2d');
    const h3 = (x, y, z) => { let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 1442695041); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967295; };
    const sm = t => t * t * (3 - 2 * t);
    function vn(x, y, z) {
      const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z), u = sm(x - xi), v = sm(y - yi), w = sm(z - zi);
      const l = (a, b, t) => a + (b - a) * t;
      return l(l(l(h3(xi, yi, zi), h3(xi + 1, yi, zi), u), l(h3(xi, yi + 1, zi), h3(xi + 1, yi + 1, zi), u), v),
        l(l(h3(xi, yi, zi + 1), h3(xi + 1, yi, zi + 1), u), l(h3(xi, yi + 1, zi + 1), h3(xi + 1, yi + 1, zi + 1), u), v), w);
    }
    const fbm = (x, y, z, o) => { let a = .5, f = 1, s = 0; for (let i = 0; i < (o || 5); i++) { s += a * vn(x * f, y * f, z * f); f *= 2; a *= .5; } return s; };

    const tex = new Uint8ClampedArray(TW * TH * 3), cl = new Uint8ClampedArray(TW * TH);
    for (let j = 0; j < TH; j++) {
      const lat = (.5 - j / TH) * Math.PI, cy = Math.cos(lat), sy = Math.sin(lat);
      for (let i = 0; i < TW; i++) {
        const lon = (i / TW) * 6.2832 - 3.1416, x = cy * Math.cos(lon), z = cy * Math.sin(lon);
        const e = fbm(x * 1.7 + 5, sy * 1.7 + 5, z * 1.7 + 5), k = (j * TW + i) * 3;
        let r, g, b;
        if (e > .53) {
          const h = (e - .53) * 5, al = Math.abs(lat);
          if (al > 1.18) { r = 232; g = 240; b = 248; }
          else if (al > .3 && al < .62 && fbm(x * 3 + 9, sy * 3, z * 3 + 9, 3) > .5) { r = 176 + h * 40; g = 148 + h * 30; b = 98; }
          else { r = 38 + h * 90; g = 98 + h * 60; b = 54 + h * 20; }
        } else {
          const d = Math.max(0, (.53 - e) * 4);
          r = 10; g = 52 + (1 - d) * 40; b = 104 + (1 - d) * 60;
          if (Math.abs(lat) > 1.3) { r = 200; g = 222; b = 240; }
        }
        tex[k] = r; tex[k + 1] = g; tex[k + 2] = b;
        const c = fbm(x * 2.6 + 20, sy * 2.6 + 20, z * 2.6 + 20, 4);
        cl[j * TW + i] = c > .55 ? Math.min(255, (c - .55) * 900) : 0;
      }
    }

    const px = [];
    const R = S / 2 - 2, L = [-.5, -.45, .74], ll = Math.hypot(L[0], L[1], L[2]);
    for (let yy = 0; yy < S; yy++) for (let xx = 0; xx < S; xx++) {
      const x = (xx - S / 2) / R, y = (yy - S / 2) / R, r2 = x * x + y * y;
      if (r2 > 1) continue;
      const z = Math.sqrt(1 - r2), lat = Math.asin(-y);
      const dif = Math.max(0, (x * L[0] - y * L[1] + z * L[2]) / ll);
      px.push({ o: (yy * S + xx) * 4, u: (Math.atan2(x, z) / 6.2832 + .5) * TW, row: Math.min(TH - 1, Math.max(0, Math.floor((.5 - lat / Math.PI) * TH))) * TW, sh: .16 + dif * .95, rim: Math.pow(1 - z, 3) });
    }
    const img = ctx.createImageData(S, S), data = img.data;
    let t0 = performance.now(), lastDraw = 0;
    function draw(t) {
      requestAnimationFrame(draw);
      if (t - lastDraw < 33) return; lastDraw = t;
      const off = reduceMotion ? 0 : ((t - t0) / 1000) * 9, off2 = off * 1.35;
      for (let n = 0; n < px.length; n++) {
        const p = px[n];
        const ui = ((p.u - off) % TW + TW) % TW | 0, uc = ((p.u - off2) % TW + TW) % TW | 0;
        const k = (p.row + ui) * 3, ca = cl[p.row + uc] / 255 * .85;
        let r = tex[k], g = tex[k + 1], b = tex[k + 2];
        r = r * (1 - ca) + 238 * ca; g = g * (1 - ca) + 244 * ca; b = b * (1 - ca) + 250 * ca;
        const rm = p.rim * 150;
        data[p.o] = Math.min(255, r * p.sh + rm * .35); data[p.o + 1] = Math.min(255, g * p.sh + rm * .7); data[p.o + 2] = Math.min(255, b * p.sh + rm); data[p.o + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
    }
    requestAnimationFrame(draw);
  }

  function initEarth() {
    $$('[data-earth]').forEach(stage => {
      const video = $('video', stage), globe = $('.earth-fallback', stage);
      if (globe) startGlobe(globe);
      if (!video) return;
      const ok = () => stage.classList.add('has-video');
      const bad = () => stage.classList.remove('has-video');
      video.addEventListener('playing', ok);
      video.addEventListener('error', bad);
      $$('source', video).forEach(s => s.addEventListener('error', bad));
      const p = video.play && video.play(); if (p && p.catch) p.catch(bad);
    });
  }

  /* ---------- misc ---------- */
  function markActiveLinks() {
    $$('.side-link').forEach(a => {
      const href = a.getAttribute('href');
      if (href && (location.pathname === href || (href.length > 1 && location.pathname.indexOf(href) === 0))) a.classList.add('active');
    });
  }

  function stripes() {
    $$('[data-stripes]').forEach(box => {
      const n = 64; let h = '';
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1), wob = Math.sin(i * 1.9) * .06 + Math.sin(i * .7) * .05, v = Math.min(1, Math.max(0, t * .95 + wob));
        const hue = v < .5 ? 212 : 6, sat = 62 + Math.abs(v - .5) * 40, lit = 26 + (1 - Math.abs(2 * v - 1)) * 26 + Math.abs(2 * v - 1) * 8;
        h += '<i style="background:hsl(' + hue + ',' + sat + '%,' + lit + '%)"></i>';
      }
      box.innerHTML = h;
    });
  }

  function clock() {
    const els = $$('[data-wx-clock]'); if (!els.length) return;
    const tick = () => {
      const n = new Date(), t = n.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      const dt = n.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' }) + ' \u2019' + String(n.getFullYear()).slice(2);
      els.forEach(e => { e.textContent = t + ' - ' + dt; });
    };
    tick(); setInterval(tick, 20000);
  }

  function init() {
    clock(); fx.mount(); markActiveLinks(); stripes(); initEarth();
    document.body.dataset.weather = 'clear';
    fetchAll().then(bind);
    setInterval(() => { storeAt = 0; fetchAll().then(bind); }, 300000);
    const sel = $('#liveWeatherCity');
    if (sel) {
      if (Array.from(sel.options).some(o => o.value === current)) sel.value = current;
      sel.addEventListener('change', () => { if (CITIES[sel.value] && sel.value !== current) useCity(sel.value, true); });
    }
  }

  window.Atmosphere = { useCity, cities: CITIES, meta: META };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();