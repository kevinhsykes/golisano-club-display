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
  const tradeSize = t => Number(dollars ? t.shares : t.shares_units);
  const rows = payload.holdings.map(h => {
    const q = quotes.get(h.symbol);
    const price = Number(q.price);
    const prev = Number(q.previous_close);
    const size = dollars ? Number(h.shares) : Number(h.units);
    const cents = p => Math.round(p * 100);
    const notes = positionNotes(h, price);
    // Trades in this symbol during the quote's session: shares bought today start at their buy
    // price, and shares sold today count their move from yesterday's close up to the sale.
    const qt = Date.parse(q.provider_update_at_utc), qDay = etParts(new Date(qt)).ymd;
    const today = (payload.trades || []).filter(t => t.symbol === h.symbol && Date.parse(t.executed_at_utc) <= qt &&
      etParts(new Date(Date.parse(t.executed_at_utc))).ymd === qDay && Number.isFinite(tradeSize(t)));
    const bought = today.filter(t => t.type === 'buy'), sold = today.filter(t => t.type === 'sell');
    const sizeAtOpen = size - bought.reduce((a, t) => a + tradeSize(t), 0) + sold.reduce((a, t) => a + tradeSize(t), 0);
    const money = (p, n) => (dollars ? (cents(p) * n) / 100 : p * n);
    const value = money(price, size);
    const openValue = money(prev, sizeAtOpen);
    const boughtValue = bought.reduce((a, t) => a + money(Number(t.price), tradeSize(t)), 0);
    const prevValue = openValue + boughtValue;
    const proceeds = sold.reduce((a, t) => a + money(Number(t.price), tradeSize(t)), 0);
    const dayValue = value + proceeds - prevValue;
    const cost = dollars ? Number(h.cost_basis) : Number(h.avg_cost) * size;
    return {
      ...h, price, prev, value, prevValue, openValue, boughtValue, proceeds, cost,
      // dayPct is the club's own day on this holding; stockDayPct is the stock's move (tape, SPY benchmark).
      dayChange: price - prev, stockDayPct: price / prev - 1,
      dayValue, dayPct: prevValue > 0 ? dayValue / prevValue : price / prev - 1,
      gainValue: value - cost,
      costPct: price / Number(h.avg_cost) - 1,
      asOf: qt,
      boughtToday: bought.length > 0, tradedToday: today.length > 0, ...notes,
    };
  });
  const sum = k => rows.reduce((a, r) => a + r[k], 0);
  const total = sum('value');
  // Day % base: the holdings at yesterday's close plus only the NEW money a buy needed. Money moved
  // from a sale into a buy on the same day is a reallocation, so it is not counted twice.
  const dayBase = sum('openValue') + Math.max(0, sum('boughtValue') - sum('proceeds'));
  const cost = sum('cost');
  rows.forEach(r => { r.weight = r.value / total; });
  const spy = rows.find(r => r.symbol === 'SPY');
  return {
    rows, dollars, total, cost,
    dayChange: sum('dayValue'), dayPct: sum('dayValue') / dayBase, dayBase,
    gain: total - cost, gainPct: total / cost - 1,
    spyDayPct: spy ? spy.stockDayPct : null,
  };
}

// New positions and stop-loss rules recorded with a buy (build.py: holdings[].opened / .stop).
// sinceBuy: price vs the first buy price. stopGap: how far the price is above the stop, as a
// share of the price (0.12 = the stop is 12% below). stopLevel: ok | near (within 5%) | hit.
export const STOP_NEAR = 0.05;
export function positionNotes(h, price) {
  const out = {};
  if (h.opened) {
    out.openedAt = Date.parse(h.opened.executed_at_utc);
    out.buyPrice = Number(h.opened.price);
    out.sinceBuy = price / out.buyPrice - 1;
  }
  if (h.stop && Number(h.stop.price) > 0) {
    out.stopPrice = Number(h.stop.price);
    out.stopRule = h.stop.rule || null;
    out.stopGap = 1 - out.stopPrice / price;
    out.stopLevel = price <= out.stopPrice ? 'hit' : out.stopGap <= STOP_NEAR ? 'near' : 'ok';
  }
  return out;
}

// Positions bought within `days` of `now` (default two weeks): shown as NEW on the screens.
export const isNew = (r, now, days = 14) => r.openedAt !== undefined && now - r.openedAt < days * 86400000 && now >= r.openedAt;

// Time-weighted return since the Sept 22 statement. build.py chains it over the saved points
// (history[].twr); the live link uses the trades recorded after the last saved point, so money
// added for a purchase never shows up as gain.
export function sinceStatement(payload, summary) {
  const hist = payload.history;
  const last = hist[hist.length - 1];
  const dollars = summary.dollars;
  const valueOf = h => (dollars ? Number(h.value) : (Number(h.index) / 100) * Number(payload.statement.units_value));
  if (!last || last.twr === undefined) {
    // Older payloads: no trades recorded, so value over statement value is the same thing.
    return dollars ? summary.total / Number(payload.statement.value) - 1 : summary.total / Number(payload.statement.units_value) - 1;
  }
  const lastT = Date.parse(last.as_of_utc);
  const newest = newestQuote(payload.quotes.items);
  const flowAfter = (payload.flows || [])
    .filter(f => Date.parse(f.effective_utc) > lastT && Date.parse(f.effective_utc) <= newest)
    .reduce((a, f) => a + Number(dollars ? f.amount : f.amount_units), 0);
  return (1 + Number(last.twr)) * summary.total / (valueOf(last) + flowAfter) - 1;
}

// The S&P 500 over the same period as sinceStatement: SPY's price now over its price at the Sept 22
// statement (history[0].spy). Price return only: SPY's dividends are not in the saved quotes.
export function spySinceStatement(payload) {
  const start = Number(payload.history?.[0]?.spy);
  const q = payload.quotes.items.find(x => x.symbol === 'SPY');
  return start > 0 && q && Number(q.price) > 0 ? Number(q.price) / start - 1 : null;
}

// How the cost basis moved since the Sept 22 statement (full payload only):
// start + bought - cost of shares sold = now. A sale removes only the sold shares' original cost,
// while the buy spends the whole proceeds, so a gain that is reinvested raises the basis.
export function costBasisWalk(payload) {
  if (payload.amounts !== 'shown' || !payload.statement?.basis) return null;
  const trades = payload.trades || [];
  const sum = (f, k) => trades.filter(f).reduce((a, t) => a + Number(t[k] || 0), 0);
  const start = Number(payload.statement.basis);
  const bought = sum(t => t.type === 'buy', 'amount');
  const removed = sum(t => t.type === 'sell', 'cost_removed');
  const proceeds = sum(t => t.type === 'sell', 'amount');
  const realized = sum(t => t.type === 'sell', 'realized_gain');
  return { start, bought, removed, proceeds, realized, end: start + bought - removed, change: bought - removed, cashKept: proceeds - bought };
}

// The walk in sentences. Every branch must stay true for any mix of buys and sales: a gain or a
// loss, proceeds reinvested in full, in part or not at all, and buys paid for with other money.
export function costBasisStory(w, estimated = false) {
  const usd = v => fmtUsd(Math.abs(v), true), zero = v => Math.abs(v) < 0.005;
  const est = estimated ? ' (estimated)' : '';
  const out = [];
  const sold = !zero(w.removed) || !zero(w.proceeds);
  if (sold) {
    const result = zero(w.realized) ? 'so there is no realized gain or loss'
      : `so the realized ${w.realized > 0 ? 'gain' : 'loss'} is ${usd(w.realized)}${est}`;
    const perSale = zero(w.proceeds - w.removed - w.realized) ? '' : ' (each sale is rounded to the cent)';
    out.push(`A sale removes only the original cost of the shares sold (${usd(w.removed)}). The sales brought in ${usd(w.proceeds)}${est}, ${result}${perSale}.`);
  }
  const moved = zero(w.change) ? 'did not change' : `${w.change > 0 ? 'rose' : 'fell'} by ${usd(w.change)}`;
  if (!sold) {
    out.push(`The club bought ${usd(w.bought)} of shares and sold nothing, so the cost basis ${moved}.`);
  } else if (zero(w.bought)) {
    out.push(`Nothing was bought, so the cost basis ${moved}: the original cost of the shares sold.`);
  } else {
    let s = `The club bought ${usd(w.bought)} of shares. Bought minus the original cost of the shares sold: the cost basis ${moved}.`;
    if (zero(w.cashKept)) s += ' All of the sale proceeds were reinvested.';
    else if (w.cashKept > 0) s += ` ${usd(w.cashKept)} of the sale proceeds was not reinvested; the club records no cash balance.`;
    else s += ` The purchases cost ${usd(w.cashKept)} more than the sales brought in; that money did not come from these sales.`;
    out.push(s);
    if (w.realized > 0 && w.change > 0 && w.cashKept >= -0.005 && zero(w.realized - w.cashKept - w.change)) {
      out.push(zero(w.cashKept) ? 'The rise is the realized gain, reinvested. It is not money added by members.'
        : `The rise is the realized gain that was reinvested: ${usd(w.realized)} minus the ${usd(w.cashKept)} not reinvested. It is not money added by members.`);
    }
  }
  return out;
}

// Gain including sales: unrealized gain on what we hold plus gain realized by sales up to the
// newest quote. The percent is over the net money put in (see below).
export function totalGain(payload, summary) {
  const newest = newestQuote(payload.quotes.items), d = summary.dollars;
  const sold = (payload.realized || []).filter(r => Date.parse(r.executed_at_utc) <= newest);
  const realized = sold.reduce((a, r) => a + Number(d ? r.gain : r.gain_units), 0);
  const soldCost = sold.reduce((a, r) => a + Number(d ? r.cost : r.cost_units), 0);
  const gain = summary.gain + realized;
  // Over the net money put in (statement cost plus outside flows) = current cost - realized gain,
  // so selling one holding to buy another does not change the percent.
  return { gain, pct: gain / (summary.cost - realized), realized, soldCost, estimated: sold.some(r => r.estimated) };
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
    if (k === 'class') { if (v) n.className = v; }
    else if (k === 'style') n.style.cssText = v;
    else if (v !== null && v !== undefined && v !== false) n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid);
  return n;
}

// Pick which x-axis date labels to draw so none overlap. Each label's box depends on its anchor
// (first: start, last: end, others: middle). The newest and the first are always kept.
export function pickDateLabels(xs, texts, charPx, padPx) {
  const n = xs.length, box = i => {
    const w = texts[i].length * charPx;
    return i === 0 ? [xs[i], xs[i] + w] : i === n - 1 ? [xs[i] - w, xs[i]] : [xs[i] - w / 2, xs[i] + w / 2];
  };
  const kept = [];
  const fits = i => kept.every(j => { const a = box(i), b = box(j); return a[1] + padPx <= b[0] || b[1] + padPx <= a[0]; });
  for (const i of [n - 1, 0, ...Array.from({ length: Math.max(0, n - 2) }, (_, k) => n - 2 - k)]) {
    if (i < 0 || kept.includes(i)) continue;
    if (i === n - 1 || fits(i)) kept.push(i);
  }
  return new Set(kept);
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
  // Date labels that do not overlap (newest and first kept).
  const labelIdx = pickDateLabels(valid.map(p => x(p.t)), valid.map(p => fmtShortDate(p.t)), 9 * unit, 14 * unit);
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
// SPY position (the IPS benchmark), and the stock picks without SPY. Each point uses the cost
// and SPY position held at that moment (build.py), so a new buy does not move earlier points.
// Statement purchase dates are unknown, so this is unrealized gain on what was paid, not a
// same-period benchmark return. Works for both payloads (the public one is in relative units).
export function comparisonSeries(payload, summary) {
  const spyH = payload.holdings.find(h => h.symbol === 'SPY');
  const tg = totalGain(payload, summary);
  if (!spyH) {
    // No SPY position (sold out): only the portfolio line.
    const pts = payload.history.map(h => ({ t: Date.parse(h.as_of_utc), y: (Number(summary.dollars ? h.value : (Number(h.index) / 100) * Number(payload.statement.units_value))
      - Number(summary.dollars ? h.cost : h.cost_units) + Number(summary.dollars ? h.realized : h.realized_units)) /
      (Number(summary.dollars ? h.cost : h.cost_units) - Number(summary.dollars ? h.realized : h.realized_units)) }));
    pts.push({ t: newestQuote(payload.quotes.items), live: true, y: tg.pct });
    return [{ name: 'Portfolio', cls: 'port', points: pts }];
  }
  const now = {
    cost: summary.cost, realized: tg.realized, soldCost: tg.soldCost,
    spySize: summary.dollars ? Number(spyH.shares) : Number(spyH.units),
    spyAvg: Number(spyH.avg_cost),
  };
  const d = summary.dollars;
  const valueAt = h => (d ? Number(h.value) : (Number(h.index) / 100) * Number(payload.statement.units_value));
  const pts = payload.history.map(h => {
    const cost = Number(d ? h.cost : h.cost_units), spySize = Number(d ? h.spy_shares : h.spy_units);
    const spyCost = Number(d ? h.spy_cost : h.spy_cost_units);
    const known = Number.isFinite(cost) && cost > 0 && spySize > 0 && spyCost > 0;
    return { t: Date.parse(h.as_of_utc), spy: Number(h.spy), total: valueAt(h),
      ...(known ? { cost, spySize, spyAvg: spyCost / spySize,
        realized: Number(d ? h.realized : h.realized_units) || 0, soldCost: Number(d ? h.sold_cost : h.sold_cost_units) || 0 } : now) };
  });
  const newest = newestQuote(payload.quotes.items);
  if (!pts.length || newest > pts[pts.length - 1].t + 60000) {
    pts.push({ t: newest, live: true, total: summary.total, ...now,
      spy: Number(payload.quotes.items.find(q => q.symbol === 'SPY').price) });
  }
  return [
    // Portfolio: unrealized plus realized gain, over the net money put in (so a reallocation is flat).
    { name: 'Portfolio', cls: 'port', points: pts.map(p => ({ t: p.t, live: p.live, y: (p.total - p.cost + p.realized) / (p.cost - p.realized) })) },
    { name: 'SPY position', cls: 'spy', points: pts.map(p => ({ t: p.t, live: p.live, y: p.spy / p.spyAvg - 1 })) },
    { name: 'Stock picks', cls: 'picks',
      points: pts.map(p => ({ t: p.t, live: p.live, y: (p.total - p.spy * p.spySize) / (p.cost - p.spySize * p.spyAvg) - 1 })) },
  ];
}

// Multi-line % change chart with a zero line and end labels. Returns an <svg>.
export function compareChart(series, { width, height, pad = 18, left = 62, right = 200, unit = 1, charPx = 8 * unit }) {
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
  // date labels that do not overlap (newest and first kept)
  const pts0 = series[0].points;
  const keep = pickDateLabels(pts0.map(p => x(p.t)), pts0.map(p => fmtShortDate(p.t)), charPx, 12 * unit);
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
