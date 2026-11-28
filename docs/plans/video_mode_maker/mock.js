// PAD-1654 mock-ups: original placeholder art for the worked example
// (Night Harbour), drawn as SVG on the 1360x768 stage.  No game content.
(function () {
  const F = 'font-family="IBM Plex Sans Condensed, IBM Plex Sans, sans-serif" font-weight="600"';
  const rnd = (s) => () => ((s = (s * 16807) % 2147483647) / 2147483647);

  function defs() {
    return `<defs>
      <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#070d1f"/><stop offset="1" stop-color="#1c3768"/></linearGradient>
      <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#123f73"/><stop offset="1" stop-color="#06182f"/></linearGradient>
      <radialGradient id="moon" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff6d8"/><stop offset=".6" stop-color="#ffe9a8"/><stop offset="1" stop-color="#ffe9a8" stop-opacity="0"/></radialGradient>
      <radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff3b0"/><stop offset=".35" stop-color="#ffb347" stop-opacity=".8"/><stop offset="1" stop-color="#ff6a00" stop-opacity="0"/></radialGradient>
      <radialGradient id="wp" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ffd166"/><stop offset=".5" stop-color="#ff5a3c"/><stop offset="1" stop-color="#7a1010"/></radialGradient>
      <linearGradient id="hull" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9edf2"/><stop offset="1" stop-color="#8a97a8"/></linearGradient>
      <linearGradient id="ship" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a4b63"/><stop offset="1" stop-color="#18222f"/></linearGradient>
      <filter id="soft"><feGaussianBlur stdDeviation="3"/></filter>
    </defs>`;
  }

  function skyline(y, col) {
    const r = rnd(7); let x = 0, d = `M0 ${y + 80}`;
    while (x < 1360) { const w = 30 + r() * 60, h = 20 + r() * 90; d += ` L${x} ${y + 80 - h} L${x + w} ${y + 80 - h}`; x += w; }
    return `<path d="${d} L1360 ${y + 80} Z" fill="${col}"/>`;
  }
  function stars(n) {
    const r = rnd(3); let s = '';
    for (let i = 0; i < n; i++) s += `<circle cx="${r() * 1360}" cy="${r() * 230}" r="${.6 + r() * 1.4}" fill="#cfe2ff" opacity="${.3 + r() * .6}"/>`;
    return s;
  }
  function sea() {
    let s = `<rect x="0" y="300" width="1360" height="468" fill="url(#sea)"/>`;
    const r = rnd(11);
    for (let i = 0; i < 70; i++) { const y = 310 + Math.pow(r(), 1.6) * 450, w = 10 + (y - 300) * .12; s += `<rect x="${r() * 1360}" y="${y}" width="${w}" height="${1 + (y - 300) / 160}" rx="1" fill="#7fb6ff" opacity="${.12 + r() * .25}"/>`; }
    for (const bx of [140, 540, 820, 1220]) s += `<line x1="680" y1="300" x2="${bx}" y2="768" stroke="#9cc8ff" stroke-opacity=".18" stroke-width="2"/>`;
    return s;
  }
  function boat(x, y, sc = 1) {
    return `<g transform="translate(${x} ${y}) scale(${sc})">
      <ellipse cx="0" cy="8" rx="120" ry="16" fill="#cfe6ff" opacity=".35" filter="url(#soft)"/>
      <path d="M-30 6 L-110 60 M30 6 L110 60" stroke="#e8f3ff" stroke-width="6" opacity=".5"/>
      <path d="M-78 -18 L78 -18 L62 10 L-62 10 Z" fill="url(#hull)" stroke="#2a3442" stroke-width="2"/>
      <path d="M-34 -18 L-26 -52 L30 -52 L40 -18 Z" fill="#c9d3df" stroke="#2a3442" stroke-width="2"/>
      <rect x="-20" y="-46" width="44" height="14" rx="2" fill="#20324a"/>
      <rect x="-6" y="-74" width="10" height="24" fill="#5b6b80"/>
      <circle cx="0" cy="-78" r="5" fill="#ffcf5a"/>
    </g>`;
  }
  function drone(x, y, sc = 1) {
    return `<g transform="translate(${x} ${y}) scale(${sc})">
      <ellipse cx="0" cy="0" rx="40" ry="11" fill="#55657b" stroke="#1a2230" stroke-width="2"/>
      <ellipse cx="0" cy="-8" rx="18" ry="11" fill="#8fa3bd" stroke="#1a2230" stroke-width="2"/>
      <circle cx="0" cy="-8" r="5" fill="#ff5a3c"/>
      <rect x="-52" y="-3" width="18" height="4" fill="#c7d3e2"/><rect x="34" y="-3" width="18" height="4" fill="#c7d3e2"/>
    </g>`;
  }
  function mine(x, y, sc = 1) {
    let sp = '';
    for (let a = 0; a < 8; a++) { const t = a * Math.PI / 4; sp += `<line x1="${Math.cos(t) * 18}" y1="${Math.sin(t) * 18}" x2="${Math.cos(t) * 28}" y2="${Math.sin(t) * 28}" stroke="#2b2f36" stroke-width="5" stroke-linecap="round"/>`; }
    return `<g transform="translate(${x} ${y}) scale(${sc})">${sp}<circle r="21" fill="#3a3f48" stroke="#14171c" stroke-width="2"/><circle r="5" fill="#ff3b3b"/><circle r="12" fill="#ff3b3b" opacity=".25"/></g>`;
  }
  function crate(x, y, sc = 1) {
    return `<g transform="translate(${x} ${y}) scale(${sc})"><rect x="-24" y="-24" width="48" height="48" rx="4" fill="#c58a3e" stroke="#5a3b14" stroke-width="3"/>
      <path d="M-24 -24 L24 24 M24 -24 L-24 24" stroke="#5a3b14" stroke-width="3"/><circle r="10" fill="#6fc07a" stroke="#1d4a26" stroke-width="2"/><path d="M-5 0 H5 M0 -5 V5" stroke="#fff" stroke-width="3"/></g>`;
  }
  function warship(x, y, sc = 1, wps) {
    let s = `<g transform="translate(${x} ${y}) scale(${sc})">
      <path d="M-330 40 L330 40 L280 110 L-280 110 Z" fill="url(#ship)" stroke="#0b1018" stroke-width="3"/>
      <path d="M-220 40 L-200 -30 L200 -30 L220 40 Z" fill="#2c3a4f" stroke="#0b1018" stroke-width="3"/>
      <path d="M-90 -30 L-70 -120 L80 -120 L100 -30 Z" fill="#3b4c66" stroke="#0b1018" stroke-width="3"/>
      <rect x="-40" y="-170" width="70" height="50" fill="#2a3850" stroke="#0b1018" stroke-width="3"/>
      <rect x="-8" y="-230" width="10" height="60" fill="#5b6b80"/>
      ${[-160, -110, 120, 170].map((cx) => `<rect x="${cx - 12}" y="-10" width="24" height="18" fill="#1a2433"/>`).join('')}
      <rect x="-300" y="60" width="600" height="6" fill="#0d141e"/>`;
    for (const w of wps || []) {
      s += `<circle cx="${w[0]}" cy="${w[1]}" r="40" fill="url(#glow)" opacity="${w[2] ? .9 : .25}"/>
            <circle cx="${w[0]}" cy="${w[1]}" r="22" fill="url(#wp)" stroke="${w[2] ? '#ffd166' : '#5a2020'}" stroke-width="3" opacity="${w[2] ? 1 : .6}"/>
            <circle cx="${w[0]}" cy="${w[1]}" r="34" fill="none" stroke="#ff5a3c" stroke-width="3" stroke-dasharray="${w[2] ? '0' : '6 6'}" opacity="${w[2] ? .95 : .5}"/>`;
    }
    return s + '</g>';
  }
  function sight(x, y) {
    return `<g transform="translate(${x} ${y})" stroke="#ffd166" stroke-width="4" fill="none">
      <circle r="30"/><circle r="4" fill="#ffd166"/><path d="M-46 0 H-18 M18 0 H46 M0 -46 V-18 M0 18 V46"/></g>`;
  }

  // the HUD, laid out as the reference does it (plan section 1)
  function hud(o) {
    o = Object.assign({ hp: 5, prog: .42, combo: 'COMBO 4  x2', score: '12,500', prompts: ['LANE', 'SHOOT', 'LANE'], callout: '', line: '', meter: null }, o);
    let s = '';
    for (let i = 0; i < 6; i++) s += `<rect x="${28 + i * 30}" y="22" width="24" height="18" rx="3" fill="${i < o.hp ? '#5ee07a' : '#2a3a2f'}" stroke="#0b1a10" stroke-width="2"/>`;
    s += `<rect x="380" y="28" width="600" height="6" rx="3" fill="#ffffff" opacity=".18"/><rect x="380" y="28" width="${600 * o.prog}" height="6" rx="3" fill="#ffffff" opacity=".9"/>`;
    s += `<text x="1150" y="40" ${F} font-size="22" fill="#f2c14e" text-anchor="end">${o.combo}</text>`;
    s += `<text x="1332" y="42" ${F} font-size="30" fill="#ffffff" text-anchor="end" style="font-variant-numeric:tabular-nums">${o.score}</text>`;
    if (o.meter) {
      s += `<rect x="380" y="640" width="600" height="26" rx="6" fill="#000" opacity=".55" stroke="#f2c14e" stroke-width="2"/>
            <rect x="384" y="644" width="${592 * o.meter}" height="18" rx="4" fill="#f2c14e"/>
            <rect x="${384 + 592 * .8}" y="640" width="3" height="26" fill="#f0705f"/>`;
    }
    if (o.callout) s += `<text x="680" y="200" ${F} font-size="64" text-anchor="middle" fill="#f2c14e" stroke="#1b1d1f" stroke-width="10" paint-order="stroke" letter-spacing="1">${o.callout}</text>`;
    if (o.line) s += `<rect x="330" y="680" width="700" height="34" rx="4" fill="#000" opacity=".55"/><text x="680" y="704" ${F} font-size="20" fill="#f2c14e" text-anchor="middle" letter-spacing="1.5">${o.line}</text>`;
    // prompt bar
    s += `<rect x="0" y="728" width="1360" height="40" fill="#05070b" opacity=".82"/>`;
    const p = o.prompts;
    if (p[0]) s += `<path d="M40 748 L58 736 L58 760 Z" fill="#f2c14e"/><text x="68" y="756" ${F} font-size="20" fill="#e9eae7">${p[0]}</text>`;
    s += `<circle cx="${680 - (p[1] ? 36 : 0)}" cy="748" r="13" fill="none" stroke="#f2c14e" stroke-width="3"/><circle cx="${680 - (p[1] ? 36 : 0)}" cy="748" r="6" fill="#f2c14e"/>`;
    if (p[1]) s += `<text x="660" y="756" ${F} font-size="20" fill="#e9eae7">${p[1]}</text>`;
    if (p[2]) s += `<text x="1292" y="756" ${F} font-size="20" fill="#e9eae7" text-anchor="end">${p[2]}</text><path d="M1320 748 L1302 736 L1302 760 Z" fill="#f2c14e"/>`;
    return s;
  }

  function scene(kind, o) {
    o = o || {};
    let s = `<svg class="art" viewBox="0 0 1360 768" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">${defs()}`;
    if (kind === 'chase' || kind === 'intro' || kind === 'won' || kind === 'lost' || kind === 'charge') {
      s += `<rect width="1360" height="768" fill="url(#sky)"/>${stars(90)}<circle cx="1080" cy="110" r="70" fill="url(#moon)"/>`;
      s += skyline(150, '#0d1a33') + skyline(190, '#0a1428') + sea();
    }
    if (kind === 'chase') {
      s += `<line x1="680" y1="640" x2="680" y2="330" stroke="#fff3b0" stroke-width="4" opacity=".85"/><circle cx="680" cy="330" r="16" fill="url(#glow)"/>`;
      s += drone(430, 190, .9) + drone(905, 250, 1.05) + drone(1150, 170, .8) + mine(470, 430, .9) + mine(560, 560, 1.2) + crate(905, 420, 1);
      s += `<circle cx="905" cy="245" r="54" fill="none" stroke="#ffffff" stroke-width="3" opacity=".9"/><circle cx="905" cy="245" r="62" fill="none" stroke="#ffffff" stroke-width="1.5" opacity=".4"/>`;
      s += boat(680, 690);
      if (o.hud !== false) s += hud(Object.assign({}, o.hudOpts));
    } else if (kind === 'boss') {
      s += `<rect width="1360" height="768" fill="#0b1426"/>${skyline(250, '#0f1d36')}<rect y="430" width="1360" height="338" fill="#0a2240"/>`;
      s += warship(680, 330, 1.1, [[-180, -20, true], [0, -60, false], [180, -20, true]]);
      s += sight(o.sx || 482, o.sy || 300);
      s += `<circle cx="1010" cy="420" r="14" fill="#ff8a3c" stroke="#3a1206" stroke-width="3"/><path d="M1010 420 L1060 380" stroke="#ff8a3c" stroke-width="5" opacity=".5"/>`;
      s += boat(680, 720, .8);
      if (o.hud !== false) s += hud(Object.assign({ prog: .3, combo: 'COMBO 8  x3', score: '41,200', prompts: ['', 'FIRE', ''], callout: o.callout === undefined ? 'HIT THE WEAK SPOTS!' : o.callout, line: 'ACTION AS THE SIGHT CROSSES EACH ONE' }, o.hudOpts));
    } else if (kind === 'charge') {
      s += boat(680, 600, 1.3);
      s += `<path d="M560 640 L420 768 M800 640 L940 768" stroke="#e8f3ff" stroke-width="14" opacity=".35"/>`;
      if (o.hud !== false) s += hud({ prog: .8, combo: 'COMBO 12  x4', score: '88,900', prompts: ['LEFT', '', 'RIGHT'], callout: 'LEFT - RIGHT - LEFT - RIGHT!', meter: .62 });
    } else if (kind === 'intro') {
      s += warship(900, 300, .7, []) + boat(400, 640, 1.2) + `<text x="680" y="130" ${F} font-size="76" fill="#f2c14e" stroke="#1b1d1f" stroke-width="10" paint-order="stroke" text-anchor="middle">NIGHT HARBOUR</text>`;
    } else if (kind === 'won') {
      s += `<circle cx="900" cy="300" r="200" fill="url(#glow)"/>` + boat(500, 640, 1.2) + `<text x="680" y="140" ${F} font-size="80" fill="#6fc07a" stroke="#0b1a10" stroke-width="10" paint-order="stroke" text-anchor="middle">HARBOUR CLEAR</text>`;
    } else if (kind === 'lost') {
      s += `<rect width="1360" height="768" fill="#000" opacity=".5"/>` + `<text x="680" y="390" ${F} font-size="80" fill="#f0705f" stroke="#1a0707" stroke-width="10" paint-order="stroke" text-anchor="middle">SUNK</text>`;
    }
    return s + '</svg>';
  }

  // small art for the asset grid
  function icon(kind) {
    const v = { boat: boat(0, 30, .55), drone: drone(0, 0, 1), mine: mine(0, 0, 1.2), crate: crate(0, 0, 1.1), warship: warship(0, 0, .13, []), sight: sight(0, 0) }[kind];
    return `<svg viewBox="-60 -60 120 120" xmlns="http://www.w3.org/2000/svg">${defs()}${v}</svg>`;
  }

  // selection chrome in stage coordinates (plan section 6, "Selection and handles")
  function selection(x, y, w, h, opts) {
    opts = opts || {};
    const acc = 'var(--accent)', hs = 8 / (opts.k || 1);
    let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="none" stroke="${acc}" stroke-width="${1.5 / (opts.k || 1)}"/>`;
    for (const [hx, hy] of [[0, 0], [.5, 0], [1, 0], [0, .5], [1, .5], [0, 1], [.5, 1], [1, 1]])
      s += `<rect x="${x + w * hx - hs / 2}" y="${y + h * hy - hs / 2}" width="${hs}" height="${hs}" fill="var(--panel)" stroke="${acc}" stroke-width="${1.5 / (opts.k || 1)}"/>`;
    s += `<line x1="${x + w / 2}" y1="${y}" x2="${x + w / 2}" y2="${y - 24 / (opts.k || 1) * 1.6}" stroke="${acc}" stroke-width="${1.5 / (opts.k || 1)}"/>`;
    s += `<circle cx="${x + w / 2}" cy="${y - 24 / (opts.k || 1) * 1.6 - 5}" r="${6 / (opts.k || 1) * 1.4}" fill="var(--panel)" stroke="${acc}" stroke-width="${1.5 / (opts.k || 1)}"/>`;
    if (opts.anchor) s += `<path d="M${opts.anchor[0] - 8} ${opts.anchor[1]} h16 M${opts.anchor[0]} ${opts.anchor[1] - 8} v16" stroke="${acc}" stroke-width="2"/>`;
    return s;
  }

  window.VM = { scene, icon, selection, hud };
})();
