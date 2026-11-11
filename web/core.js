// Shared data, market-clock, math and formatting for the TV and Canvas views.
// No dependencies; runs in any current browser (Chromium kiosk, Fire TV, Canvas iframe).

export const ET = 'America/New_York';
const STALE_OPEN_MINUTES = 30;
export const STALE_SYMBOL_MINUTES = 90; // a single quote older than this during the session flags the board

export async function fetchJson(url, timeoutMs = 20000) {
  const signal = typeof AbortSignal !== 'undefined' && AbortSignal.timeout ? AbortSignal.timeout(timeoutMs) : undefined;
  const res = await fetch(url, { cache: 'no-store', signal });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

// The deployed build id (web/version.json, written by build.py). Pages fetch it at boot and again
// on every poll; a changed id means a new deploy, and the page reloads itself to pick it up.
export async function fetchVersion() {
  try { return await fetchJson('version.json', 10000); } catch { return null; }
}
export function buildChanged(boot, now) {
  return !!(boot && now && boot.build && now.build && boot.build !== now.build);
}

// Merge a complete portfolio-quotes.v1 snapshot over the payload's quotes.
// An incomplete or older snapshot is ignored so the last good prices stay up.
export function mergeQuotes(payload, snap) {
  if (!snap || snap.schema !== 'portfolio-quotes.v1' || !Array.isArray(snap.quotes)) return false;
  const need = new Set(payload.holdings.map(h => h.symbol));
  const got = new Map(snap.quotes.map(q => [q.symbol, q]));
  for (const s of need) {
    const q = got.get(s);
    if (!q || !(Number(q.price) > 0) || !(Number(q.previous_close) > 0) || !q.provider_update_at_utc) return false;
  }
  if (newestQuote(snap.quotes) <= newestQuote(payload.quotes.items)) return false;
  payload.quotes = { collected_at_utc: snap.collected_at_utc, items: [...need].map(s => got.get(s)), meta: snap.meta || null };
  return true;
}

// "Prices delayed 15 minutes · Data provided by X" — exchanges require the delay notice
// at or near the top of every display, and on tickers at least every 90 seconds.
export function delayNotice(payload) {
  const meta = payload.quotes.meta;
  if (!meta) return 'Saved prices, not a live feed';
  const delay = meta.delay_minutes ? `Prices delayed ${meta.delay_minutes} minutes` : 'Real-time prices';
  const scope = meta.market_scope === 'partial' ? ' · not sourced from all markets' : '';
  return `${delay}${scope} · ${meta.attribution}`;
}

// The last refresh attempt, from web/data/refresh-health.json (written by
// tools/snapshot_quotes.py on every run, success or failure). Returns the record when it is
// well formed, otherwise null so the page can show a plain "no refresh record yet" fallback
// instead of a broken or spoofed-looking line.
export function parseRefreshHealth(rec) {
  if (!rec || typeof rec !== 'object' || Array.isArray(rec)) return null;
  if (typeof rec.attempted_at_utc !== 'string' || Number.isNaN(Date.parse(rec.attempted_at_utc))) return null;
  if (typeof rec.ok !== 'boolean' || rec.provider !== 'yahoo-snapshot') return null;
  if (!Number.isInteger(rec.symbols_requested) || rec.symbols_requested < 0) return null;
  if (!Number.isInteger(rec.symbols_written) || rec.symbols_written < 0 || rec.symbols_written > rec.symbols_requested) return null;
  if (rec.error !== null && typeof rec.error !== 'string') return null;
  return rec;
}

// "Last refresh attempt: Oct 26, 4:32 PM ET (ok) · 18/18 symbols" — the setup/diagnostics line.
export function refreshHealthLine(rec) {
  const h = parseRefreshHealth(rec);
  if (!h) return 'no refresh record yet';
  const when = new Date(h.attempted_at_utc);
  return `Last refresh attempt: ${fmtShortDate(when)}, ${fmtTime(when)} (${h.ok ? 'ok' : 'failed'})`
    + ` · ${h.symbols_written}/${h.symbols_requested} symbols`;
}

export const newestQuote = items => Math.max(...items.map(q => Date.parse(q.provider_update_at_utc)));
export const oldestQuote = items => Math.min(...items.map(q => Date.parse(q.provider_update_at_utc)));

// ---------- market clock (NYSE regular session, holidays from exchange_calendars) ----------

export function etParts(date) {
  const f = new Intl.DateTimeFormat('en-US', {
    timeZone: ET, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
  const p = Object.fromEntries(f.formatToParts(date).map(x => [x.type, x.value]));
  return { ymd: `${p.year}-${p.month}-${p.day}`, minutes: Number(p.hour) * 60 + Number(p.minute) };
}

const weekday = ymd => new Date(`${ymd}T12:00:00Z`).getUTCDay();
const shiftDay = (ymd, n) => {
  const d = new Date(`${ymd}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const isSession = (ymd, cal) => weekday(ymd) % 6 !== 0 && !cal.weekday_holidays.includes(ymd);
const closeAt = (ymd, cal) => {
  const t = cal.early_closes[ymd];
  return t ? Number(t.slice(0, 2)) * 60 + Number(t.slice(3)) : 16 * 60;
};

export function marketStatus(now, cal) {
  const { ymd, minutes } = etParts(now);
  const session = isSession(ymd, cal);
  const open = 9 * 60 + 30;
  const close = closeAt(ymd, cal);
  let state = 'closed';
  if (session && minutes >= 4 * 60 && minutes < open) state = 'pre';
  else if (session && minutes >= open && minutes < close) state = 'open';
  else if (session && minutes >= close && minutes < 20 * 60) state = 'after';

  // Most recent session whose regular close has already happened.
  let last = ymd;
  if (!(session && minutes >= close)) {
    last = shiftDay(ymd, -1);
    while (!isSession(last, cal)) last = shiftDay(last, -1);
  }
  return {
    state, ymd,
    holiday: !session && weekday(ymd) % 6 !== 0,
    earlyClose: cal.early_closes[ymd] || null,
    lastClosedSession: last,
    lastClosedAt: closeAt(last, cal),
    calendarKnown: ymd >= cal.range[0] && ymd <= cal.range[1],
  };
}

// live | closed | stale, with the reason in plain words.
export function freshness(items, status, now, delayMinutes = 0) {
  const newest = newestQuote(items);
  const ageMin = (now - newest) / 60000;
  const newestYmd = etParts(new Date(newest)).ymd;
  if (status.state === 'open') {
    // A 15-minute-delayed feed is normally ~16 minutes old; stale means no update for 15 more.
    const limit = delayMinutes ? delayMinutes + 15 : STALE_OPEN_MINUTES;
    if (ageMin > limit) return { level: 'stale', newest, ageMin, reason: 'Prices are not updating' };
    // One symbol stuck on an old print must not ride on the others' freshness.
    const oldest = oldestQuote(items);
    if ((now - oldest) / 60000 > STALE_SYMBOL_MINUTES) {
      const sym = items.find(q => Date.parse(q.provider_update_at_utc) === oldest)?.symbol || 'A holding';
      return { level: 'stale', newest, ageMin, reason: `${sym} has not updated since ${new Date(oldest).toISOString().slice(11, 16)} UTC` };
    }
    return { level: 'live', newest, ageMin };
  }
  if (newestYmd < status.lastClosedSession) {
    return { level: 'stale', newest, ageMin, reason: 'Prices are from an earlier session' };
  }
  // Same session, but saved well before that session's close: not closing prices.
  const { minutes } = etParts(new Date(newest));
  if (newestYmd === status.lastClosedSession && minutes < status.lastClosedAt - 20) {
    return { level: 'stale', newest, ageMin, reason: 'Last saved prices are from before the close' };
  }
  return { level: 'closed', newest, ageMin };
}

// ---------- portfolio math ----------
// Full payload: integer cents x whole shares, exact. Public payload: relative units.

export function compute(payload) {
  const quotes = new Map(payload.quotes.items.map(q => [q.symbol, q]));
  const dollars = payload.amounts === 'shown';
  const rows = payload.holdings.map(h => {
    const q = quotes.get(h.symbol);
    const price = Number(q.price);
    const prev = Number(q.previous_close);
    const size = dollars ? Number(h.shares) : Number(h.units);
    const cents = p => Math.round(p * 100);
    const value = dollars ? (cents(price) * size) / 100 : price * size;
    const prevValue = dollars ? (cents(prev) * size) / 100 : prev * size;
    const cost = dollars ? Number(h.cost_basis) : Number(h.avg_cost) * size;
    return {
      ...h, price, prev, value, prevValue, cost,
      dayChange: price - prev, dayPct: price / prev - 1,
      dayValue: value - prevValue, gainValue: value - cost,
      costPct: price / Number(h.avg_cost) - 1,
      asOf: Date.parse(q.provider_update_at_utc),
    };
  });
  const sum = k => rows.reduce((a, r) => a + r[k], 0);
  const total = sum('value');
  const prevTotal = sum('prevValue');
  const cost = sum('cost');
  rows.forEach(r => { r.weight = r.value / total; });
  const spy = rows.find(r => r.symbol === 'SPY');
  return {
    rows, dollars, total, cost,
    dayChange: total - prevTotal, dayPct: total / prevTotal - 1,
    gain: total - cost, gainPct: total / cost - 1,
    spyDayPct: spy ? spy.dayPct : null,
  };
}

// History as {t, y} points: dollars when shown, otherwise an index (statement = 100).
// A live point is appended when quotes are newer than the last saved observation.
// Public payload: units = shares / total cost, so statement.units_value is the
// statement value in the same units and the index is total / units_value x 100.
export function historySeries(payload, summary) {
  const pts = payload.history.map(h => ({
    t: Date.parse(h.as_of_utc),
    y: summary.dollars ? Number(h.value) : Number(h.index),
    kind: h.kind,
  }));
  const newest = newestQuote(payload.quotes.items);
  const last = pts[pts.length - 1];
  if (!last || newest > last.t + 60000) {
    const y = summary.dollars ? summary.total : (summary.total / Number(payload.statement.units_value)) * 100;
    pts.push({ t: newest, y, kind: 'live' });
  }
  return pts;
}

// ---------- formatting ----------

const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const usd2 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtUsd = (x, cents = false) => (cents ? usd2 : usd0).format(x);
export const fmtSignedUsd = (x, cents = false) => `${x >= 0 ? '+' : '−'}${(cents ? usd2 : usd0).format(Math.abs(x))}`;
export const fmtPct = (x, digits = 2) => `${x >= 0 ? '+' : '−'}${Math.abs(x * 100).toFixed(digits)}%`;
export const fmtWeight = x => `${(x * 100).toFixed(1)}%`;
export const fmtPrice = x => x.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const arrow = x => (x > 0 ? '▲' : x < 0 ? '▼' : '■');
export const dir = x => (x > 0 ? 'up' : x < 0 ? 'down' : 'flat');

export const fmtTime = t => new Intl.DateTimeFormat('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit' }).format(t) + ' ET';
export const fmtDay = t => new Intl.DateTimeFormat('en-US', { timeZone: ET, weekday: 'short', month: 'short', day: 'numeric' }).format(t);
export const fmtShortDate = t => new Intl.DateTimeFormat('en-US', { timeZone: ET, month: 'short', day: 'numeric' }).format(t);
export const fmtYmd = ymd => fmtDay(new Date(`${ymd}T16:00:00Z`));

export const STATUS_LABEL = { open: 'Market open', pre: 'Pre-market', after: 'After hours', closed: 'Market closed' };

export function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v;
    else if (k === 'style') n.style.cssText = v;
    else if (v !== null && v !== undefined && v !== false) n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid);
  return n;
}

// SVG line chart of discrete saved observations. Returns an <svg> element.
export function lineChart(points, { width, height, pad = 40, left: leftPad, unit = 1, format, dollars }) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  const ys = points.map(p => p.y).filter(Number.isFinite);
  if (ys.length < 2) return svg;
  const t0 = points[0].t, t1 = points[points.length - 1].t;
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const span = hi - lo || hi * 0.01;
  lo -= span * 0.25; hi += span * 0.25;
  const left = leftPad ?? pad * 2.6, right = pad * 0.6, top = pad * 0.5, bottom = pad * 1.1;
  const x = t => left + ((t - t0) / (t1 - t0 || 1)) * (width - left - right);
  const y = v => top + (1 - (v - lo) / (hi - lo)) * (height - top - bottom);
  const add = (tag, attrs) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    svg.append(n);
    return n;
  };
  for (let i = 0; i <= 3; i++) {
    const v = lo + ((hi - lo) * i) / 3;
    add('line', { x1: left, x2: width - right, y1: y(v), y2: y(v), class: 'grid' });
    add('text', { x: left - 10 * unit, y: y(v) + 6 * unit, class: 'axis', 'text-anchor': 'end' }).textContent = format(v);
  }
  const valid = points.filter(p => Number.isFinite(p.y));
  add('polyline', { points: valid.map(p => `${x(p.t)},${y(p.y)}`).join(' '), class: 'line' });
  valid.forEach((p, i) => {
    add('circle', { cx: x(p.t), cy: y(p.y), r: (i === valid.length - 1 ? 7 : 5) * unit, class: `dot ${p.kind}` });
  });
  // Label dates from the newest backwards, skipping any that would collide (~90px apart);
  // the first date is always kept.
  const gap = 90 * unit, labelIdx = new Set([0]);
  let lastX = Infinity;
  for (let i = valid.length - 1; i > 0; i--) {
    const px = x(valid[i].t);
    if (lastX - px >= gap && px - x(valid[0].t) >= gap) { labelIdx.add(i); lastX = px; }
  }
  valid.forEach((p, i) => {
    if (!labelIdx.has(i)) return;
    add('text', { x: x(p.t), y: height - bottom * 0.25, class: 'axis', 'text-anchor': i === 0 ? 'start' : i === valid.length - 1 ? 'end' : 'middle' })
      .textContent = fmtShortDate(p.t);
  });
  svg.setAttribute('aria-label', `Portfolio ${dollars ? 'value' : 'index'} at ${valid.length} saved observations`);
  return svg;
}

// ---------- portfolio vs market ----------
// Gain over cost basis at each saved observation, for: the whole portfolio, the club's own
// SPY position (the IPS benchmark), and the 17 stock picks without SPY. Purchase dates are
// unknown, so this is unrealized gain on what was paid, not a same-period benchmark return.
// Works for both payloads: the public one carries relative units and avg cost, no dollars.
export function comparisonSeries(payload, summary) {
  const spyH = payload.holdings.find(h => h.symbol === 'SPY');
  const spyAvg = Number(spyH.avg_cost);
  const spySize = summary.dollars ? Number(spyH.shares) : Number(spyH.units);
  const totalCost = summary.cost;                      // dollars, or 1.0 in units
  const picksCost = totalCost - spySize * spyAvg;
  const valueAt = h => (summary.dollars ? Number(h.value)
    : (Number(h.index) / 100) * Number(payload.statement.units_value));
  const pts = payload.history.map(h => ({ t: Date.parse(h.as_of_utc), spy: Number(h.spy), total: valueAt(h) }));
  const newest = newestQuote(payload.quotes.items);
  if (!pts.length || newest > pts[pts.length - 1].t + 60000) {
    pts.push({ t: newest, live: true, total: summary.total,
      spy: Number(payload.quotes.items.find(q => q.symbol === 'SPY').price) });
  }
  return [
    { name: 'Portfolio', cls: 'port', points: pts.map(p => ({ t: p.t, live: p.live, y: p.total / totalCost - 1 })) },
    { name: 'SPY position', cls: 'spy', points: pts.map(p => ({ t: p.t, live: p.live, y: p.spy / spyAvg - 1 })) },
    { name: 'Stock picks (excl. SPY)', cls: 'picks',
      points: pts.map(p => ({ t: p.t, live: p.live, y: (p.total - p.spy * spySize) / picksCost - 1 })) },
  ];
}

// Multi-line % change chart with a zero line and end labels. Returns an <svg>.
export function compareChart(series, { width, height, pad = 18, left = 62, right = 200, unit = 1 }) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    svg.append(n);
    return n;
  };
  const all = series.flatMap(s => s.points);
  const t0 = Math.min(...all.map(p => p.t)), t1 = Math.max(...all.map(p => p.t));
  let lo = Math.min(0, ...all.map(p => p.y)), hi = Math.max(0, ...all.map(p => p.y));
  const span = hi - lo || 0.01;
  lo -= span * 0.15; hi += span * 0.15;
  const top = pad * 0.6, bottom = pad * 1.6;
  const x = t => left + ((t - t0) / (t1 - t0 || 1)) * (width - left - right);
  const y = v => top + (1 - (v - lo) / (hi - lo)) * (height - top - bottom);
  const step = [0.0025, 0.005, 0.01, 0.02, 0.05, 0.1].find(s => (hi - lo) / s <= 7) || 0.2;
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    add('line', { x1: left, x2: width - right, y1: y(v), y2: y(v), class: Math.abs(v) < 1e-9 ? 'zero' : 'grid' });
    add('text', { x: left - 8 * unit, y: y(v) + 4 * unit, class: 'axis', 'text-anchor': 'end' }, `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`);
  }
  // date labels from newest back, skipping collisions
  const pts0 = series[0].points, gap = 70 * unit;
  let lastX = Infinity;
  const keep = new Set([0]);
  for (let i = pts0.length - 1; i > 0; i--) {
    const px = x(pts0[i].t);
    if (lastX - px >= gap && px - x(pts0[0].t) >= gap) { keep.add(i); lastX = px; }
  }
  pts0.forEach((p, i) => keep.has(i) && add('text', { x: x(p.t), y: height - bottom * 0.3, class: 'axis',
    'text-anchor': i === 0 ? 'start' : i === pts0.length - 1 ? 'end' : 'middle' }, fmtShortDate(p.t)));
  // lines, dots, end labels (nudged apart so they don't overlap)
  const ends = series.map(s => ({ s, last: s.points[s.points.length - 1] })).sort((a, b) => y(a.last.y) - y(b.last.y));
  let prevY = -Infinity;
  for (const { s, last } of ends) {
    add('polyline', { points: s.points.map(p => `${x(p.t)},${y(p.y)}`).join(' '), class: `line ${s.cls}` });
    s.points.forEach(p => add('circle', { cx: x(p.t), cy: y(p.y), r: (p.live ? 5 : 3.5) * unit, class: `dot ${s.cls}` }));
    const ly = Math.max(y(last.y) + 4 * unit, prevY + 16 * unit);
    prevY = ly;
    add('text', { x: x(last.t) + 10 * unit, y: ly, class: `endlabel ${s.cls}` }, `${s.name} ${fmtPct(last.y, 1)}`);
  }
  svg.setAttribute('aria-label', series.map(s => `${s.name} ${fmtPct(s.points[s.points.length - 1].y, 1)}`).join(', ') + ' unrealized gain over cost since the Sept 22 statement; purchase dates unknown, so not a same-period return');
  return svg;
}
