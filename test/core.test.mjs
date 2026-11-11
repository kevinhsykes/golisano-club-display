// node --test test/   (run `python build.py` first; uses web/data/portfolio.json)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { compute, marketStatus, freshness, mergeQuotes, historySeries, comparisonSeries, sinceStatement, positionNotes, isNew, totalGain } from '../web/core.js';

const load = f => JSON.parse(readFileSync(new URL(`../web/data/${f}`, import.meta.url), 'utf8'));
const full = () => load('portfolio.json');
// Tests pin the Oct 9 snapshot (now in history) so they don't change with each refresh.
const OCT9 = JSON.parse(readFileSync(new URL('../data/source/historical-quotes.json', import.meta.url), 'utf8'))
  .find(h => h.collected_at_utc === '2026-10-09T14:44:50Z');
// Holdings as of Oct 9: the statement positions (trades recorded later are left out; SPY's
// statement size is restored from the first history point).
const oct9 = () => {
  const p = full();
  const syms = new Set(OCT9.quotes.map(q => q.symbol));
  p.holdings = p.holdings.filter(h => syms.has(h.symbol) && !h.opened);
  const spy = p.holdings.find(h => h.symbol === 'SPY');
  spy.shares = p.history[0].spy_shares; spy.cost_basis = p.history[0].spy_cost;
  p.realized = [];
  p.quotes = { collected_at_utc: OCT9.collected_at_utc, items: OCT9.quotes };
  return p;
};
const at = iso => new Date(iso);

test('Oct 9 snapshot matches the published Oct 9 figures to the cent', () => {
  const s = compute(oct9());
  assert.equal(s.total.toFixed(2), '109481.42');
  assert.equal(s.cost.toFixed(2), '100831.99');
  assert.equal(s.gain.toFixed(2), '8649.43');
  assert.equal((s.gainPct * 100).toFixed(2), '8.58');
  assert.equal(s.rows.length, 18);
  assert.equal(s.rows.reduce((a, r) => a + r.weight, 0).toFixed(10), '1.0000000000');
});

test('public payload carries no shares, basis or dollar history but gives the same percentages', () => {
  let pub;
  try { pub = load('portfolio.public.json'); } catch { return; } // built with --public
  assert.equal(pub.amounts, 'hidden');
  for (const h of pub.holdings) { assert.equal(h.shares, undefined); assert.equal(h.cost_basis, undefined); }
  // Trade log, flows and realized gains carry no share counts or dollar amounts in the public build.
  assert.ok(pub.trades.length >= 3);
  for (const t of pub.trades) for (const k of ['shares', 'amount', 'fees', 'realized_gain', 'cost_removed']) assert.equal(t[k], undefined, k);
  for (const f of pub.flows) assert.equal(f.amount, undefined);
  for (const r of pub.realized) { assert.equal(r.gain, undefined); assert.equal(r.proceeds, undefined); }
  for (const h of pub.history) for (const k of ['cost', 'spy_shares', 'spy_cost', 'flow', 'realized', 'sold_cost']) assert.equal(h[k], undefined, k);
  assert.equal(pub.statement.value, null);
  assert.ok(pub.history.every(p => p.value === undefined));
  const a = compute(full()), b = compute(pub);
  assert.equal((a.gainPct * 100).toFixed(4), (b.gainPct * 100).toFixed(4));
  assert.equal((a.dayPct * 100).toFixed(4), (b.dayPct * 100).toFixed(4));
});

test('market clock: regular hours, weekend, holiday and early close (ET)', () => {
  const cal = full().calendar;
  assert.equal(marketStatus(at('2026-10-21T15:40:00Z'), cal).state, 'open');     // Wed 11:40 AM
  assert.equal(marketStatus(at('2026-10-21T13:00:00Z'), cal).state, 'pre');      // 9:00 AM
  assert.equal(marketStatus(at('2026-10-21T21:30:00Z'), cal).state, 'after');    // 5:30 PM
  assert.equal(marketStatus(at('2026-10-24T15:00:00Z'), cal).state, 'closed');   // Saturday
  const tg = marketStatus(at('2026-11-26T15:00:00Z'), cal);                     // Thanksgiving
  assert.equal(tg.state, 'closed'); assert.equal(tg.holiday, true);
  assert.equal(tg.lastClosedSession, '2026-11-25');
  const bf = marketStatus(at('2026-11-27T18:30:00Z'), cal);                     // 1:30 PM day after
  assert.equal(bf.state, 'after'); assert.equal(bf.earlyClose, '13:00');
  assert.equal(marketStatus(at('2026-03-09T13:45:00Z'), cal).state, 'open');     // after DST start, 9:45 AM EDT
});

test('freshness: live, stale during session, mid-session prices after close, closing prices', () => {
  const p = oct9(), cal = p.calendar, q = p.quotes.items;
  const f = iso => freshness(q, marketStatus(at(iso), cal), at(iso)).level;
  assert.equal(f('2026-10-09T14:52:00Z'), 'live');    // 13 min after newest quote
  assert.equal(f('2026-10-09T15:30:00Z'), 'stale');   // 51 min, market open
  assert.equal(f('2026-10-09T21:00:00Z'), 'stale');   // after close, prices are from 10:39 AM
  assert.equal(f('2026-10-21T15:40:00Z'), 'stale');   // 12 days old
  const closing = q.map(x => ({ ...x, provider_update_at_utc: '2026-10-09T20:00:00Z' }));
  assert.equal(freshness(closing, marketStatus(at('2026-10-10T15:00:00Z'), cal), at('2026-10-10T15:00:00Z')).level, 'closed');
  // One symbol stuck two hours behind the rest flags the board by name, even though the newest quote is fresh.
  const fresh = q.map(x => ({ ...x, provider_update_at_utc: '2026-10-09T15:25:00Z' }));
  fresh[3] = { ...fresh[3], provider_update_at_utc: '2026-10-09T13:35:00Z' };
  const stuck = freshness(fresh, marketStatus(at('2026-10-09T15:30:00Z'), cal), at('2026-10-09T15:30:00Z'));
  assert.equal(stuck.level, 'stale');
  assert.match(stuck.reason, new RegExp('^' + fresh[3].symbol + ' has not updated'));
});

test('mergeQuotes keeps last good prices on incomplete or older snapshots', () => {
  const p = oct9();
  const before = JSON.stringify(p.quotes);
  // Dated after every saved history point, so the merged prices are the newest observation.
  const lastSaved = Math.max(...p.history.map(h => Date.parse(h.as_of_utc)));
  const day = 86400000, iso = ms => new Date(ms).toISOString().replace('.000Z', 'Z');
  const newer = { schema: 'portfolio-quotes.v1', collected_at_utc: iso(lastSaved + day),
    quotes: p.quotes.items.map(x => ({ ...x, provider_update_at_utc: iso(lastSaved + day - 120000) })) };
  assert.equal(mergeQuotes(p, { ...newer, quotes: newer.quotes.slice(1) }), false);
  assert.equal(mergeQuotes(p, { ...newer, quotes: newer.quotes.map(x => ({ ...x, provider_update_at_utc: '2026-10-01T14:00:00Z' })) }), false);
  assert.equal(mergeQuotes(p, { ...newer, quotes: newer.quotes.map((x, i) => (i ? x : { ...x, price: '0' })) }), false);
  assert.equal(JSON.stringify(p.quotes), before);
  assert.equal(mergeQuotes(p, newer), true);
  const pts = historySeries(p, compute(p));
  assert.equal(pts[pts.length - 1].kind, 'live');
});

test('comparison chart starts from the statement gain over cost, not zero', () => {
  for (const p of [full(), load('portfolio.public.json')]) {
    const [port, spy, picks] = comparisonSeries(p, compute(p));
    assert.equal((port.points[0].y * 100).toFixed(2), '8.97');   // $9,040.18 / $100,831.99
    assert.equal((spy.points[0].y * 100).toFixed(2), '10.81');   // SPY statement gain / its cost
    assert.equal((picks.points[0].y * 100).toFixed(2), '7.18');
  }
});

// ---------- recorded trades (MU and CAT bought 2026-11-11) ----------

test('a recorded buy adds the position now but leaves earlier history points unchanged', () => {
  const p = full();
  const mu = p.holdings.find(h => h.symbol === 'MU');
  assert.equal(mu.shares, '7');
  assert.equal(mu.cost_basis, '5772.90');
  assert.equal(mu.opened.price, '824.70');
  assert.equal(mu.stop.price, '659.76');
  assert.equal(p.holdings.find(h => h.symbol === 'CAT').stop, undefined);
  const before = p.history.filter(h => h.as_of_utc < '2026-11-11T17:54:00Z');
  assert.ok(before.length > 5);
  for (const h of before) { assert.equal(h.cost, '100831.99'); assert.equal(h.flow, '0.00'); }
  const after = p.history.filter(h => h.as_of_utc >= '2026-11-11T17:54:00Z');
  // Reallocation: 14 SPY sold (estimated 761.31 at 12:54 PM ET) funds the buys.
  // cost = 100,831.99 + 5,772.90 + 4,868.32 - 9,783.48 (SPY average cost removed)
  for (const h of after) { assert.equal(h.cost, '101689.73'); assert.equal(h.spy_shares, '57'); assert.equal(h.realized, '874.86'); }
  assert.equal(after[0].flow, '-17.12');                                // 10,641.22 bought - 10,658.34 sold
  assert.equal(p.holdings.find(h => h.symbol === 'SPY').shares, '57');
  assert.equal(p.realized[0].estimated, true);
});

test('a sale is not a loss: gain vs cost includes realized gain, in both payloads', () => {
  for (const p of [full(), load('portfolio.public.json')]) {
    const s = compute(p), tg = totalGain(p, s);
    assert.ok(tg.realized > 0);
    assert.ok(Math.abs(tg.gain - s.gain - tg.realized) < 1e-9);
    const [port] = comparisonSeries(p, s);
    const live = port.points[port.points.length - 1].y;
    assert.equal(live.toFixed(6), tg.pct.toFixed(6));
  }
  const a = full(), b = load('portfolio.public.json');
  assert.equal(totalGain(a, compute(a)).pct.toFixed(6), totalGain(b, compute(b)).pct.toFixed(6));
});

test('return since the statement is time-weighted: a purchase is not counted as gain', () => {
  for (const p of [full(), load('portfolio.public.json')]) {
    const s = compute(p);
    const twr = sinceStatement(p, s);
    const naive = p.statement.units_value ? s.total / Number(p.statement.units_value) - 1 : s.total / Number(p.statement.value) - 1;
    assert.ok(Math.abs(twr) < 0.25);
    // Net flow is -$17.12 (reallocation), so TWR and value/statement now differ only by that.
    assert.ok(Math.abs(naive - twr) < 0.01, `naive ${naive} vs twr ${twr}`);
  }
  // Same answer in both payloads.
  const a = sinceStatement(full(), compute(full())), b = sinceStatement(load('portfolio.public.json'), compute(load('portfolio.public.json')));
  assert.equal(a.toFixed(6), b.toFixed(6));
});

test('live link: a trade after the last saved point is a flow, not a jump', () => {
  // Synthetic: last saved point worth 100 with TWR +10%; then 50 is added (a buy) and nothing moves.
  const p = { statement: { value: '90.91' }, history: [{ as_of_utc: '2026-11-12T15:00:00Z', value: '100', twr: '0.10' }],
    flows: [{ effective_utc: '2026-11-12T15:30:00Z', amount: '50' }],
    quotes: { items: [{ provider_update_at_utc: '2026-11-12T16:00:00Z' }] } };
  assert.equal(sinceStatement(p, { dollars: true, total: 150 }).toFixed(6), '0.100000');
  assert.equal(sinceStatement(p, { dollars: true, total: 165 }).toFixed(6), '0.210000');   // +10% on top
  // Without the flow the same total would be a fake +65%: the guard must fail without it.
  assert.equal(sinceStatement({ ...p, flows: [] }, { dollars: true, total: 150 }).toFixed(6), '0.650000');
  // A flow dated after the newest quote is not applied yet.
  const early = { ...p, quotes: { items: [{ provider_update_at_utc: '2026-11-12T15:10:00Z' }] } };
  assert.equal(sinceStatement(early, { dollars: true, total: 100 }).toFixed(6), '0.100000');
});

test('stop-loss distance: ok, near (within 5%), hit', () => {
  const h = { stop: { price: '659.76' }, opened: { price: '824.70', executed_at_utc: '2026-11-11T17:54:00Z' } };
  assert.equal(positionNotes(h, 824.70).stopLevel, 'ok');
  assert.equal(positionNotes(h, 824.70).stopGap.toFixed(4), '0.2000');
  assert.equal(positionNotes(h, 690).stopLevel, 'near');
  assert.equal(positionNotes(h, 659.76).stopLevel, 'hit');
  assert.equal(positionNotes(h, 600).stopLevel, 'hit');
  assert.equal(positionNotes(h, 907.17).sinceBuy.toFixed(4), '0.1000');
  assert.deepEqual(positionNotes({}, 10), {});
  const r = { openedAt: Date.parse('2026-11-11T17:54:00Z') };
  assert.equal(isNew(r, Date.parse('2026-11-12T00:00:00Z')), true);
  assert.equal(isNew(r, Date.parse('2026-11-26T00:00:00Z')), false);
  assert.equal(isNew({}, Date.parse('2026-11-12T00:00:00Z')), false);
});

test('comparison chart: the buy does not move earlier points; latest point uses the new cost', () => {
  const p = full();
  const [port] = comparisonSeries(p, compute(p));
  const nov10 = p.history.findIndex(h => h.date === '2026-11-10');
  assert.equal(port.points[nov10].y.toFixed(6), (Number(p.history[nov10].value) / 100831.99 - 1).toFixed(6));
});

test("today's change for a position bought today starts from the buy price, not yesterday's close", () => {
  const p = full();
  const mu = p.holdings.find(h => h.symbol === 'MU');
  const q = p.quotes.items.find(x => x.symbol === 'MU');
  // A quote in the buy session after the fill: day value counts from $824.70.
  q.provider_update_at_utc = '2026-11-11T19:00:00Z'; q.price = '830.00'; q.previous_close = '725.11';
  let r = compute(p).rows.find(x => x.symbol === 'MU');
  assert.equal(r.boughtToday, true);
  assert.equal(r.dayValue.toFixed(2), ((830 - 824.70) * 7).toFixed(2));
  assert.ok(r.dayPct > 0.14);                          // the stock's own move is still shown per row
  // Next session: yesterday's close is the baseline again.
  q.provider_update_at_utc = '2026-11-12T15:00:00Z'; q.previous_close = '830.00'; q.price = '840.00';
  r = compute(p).rows.find(x => x.symbol === 'MU');
  assert.equal(r.boughtToday, false);
  assert.equal(r.dayValue.toFixed(2), (10 * 7).toFixed(2));
  assert.equal(mu.opened.date, '2026-11-11');
});
