// node --test test/   (run `python build.py` first; uses web/data/portfolio.json)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { compute, marketStatus, freshness, mergeQuotes, historySeries, comparisonSeries } from '../web/core.js';

const load = f => JSON.parse(readFileSync(new URL(`../web/data/${f}`, import.meta.url), 'utf8'));
const full = () => load('portfolio.json');
// Tests pin the Oct 9 snapshot (now in history) so they don't change with each refresh.
const OCT9 = JSON.parse(readFileSync(new URL('../data/source/historical-quotes.json', import.meta.url), 'utf8'))
  .find(h => h.collected_at_utc === '2026-10-09T14:44:50Z');
const oct9 = () => { const p = full(); p.quotes = { collected_at_utc: OCT9.collected_at_utc, items: OCT9.quotes }; return p; };
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

// Calendar coverage guard: data/source/xnys-calendar.json covers a fixed window; this test is
// the alarm that a student sees long before it runs out. See README "Calendar renewal".
const CALENDAR = JSON.parse(readFileSync(new URL('../data/source/xnys-calendar.json', import.meta.url), 'utf8'));
const CALENDAR_RANGE_END = CALENDAR.range[1];
const CALENDAR_WARNING_DAYS = 120, DAY_MS = 86400000;
const calendarCoverageMessage = () =>
  `calendar coverage ends ${CALENDAR_RANGE_END}; renew the XNYS calendar (see README) before then`;
// "Today" is the real UTC date in a normal run (computed once, so a run is deterministic);
// CAL_TODAY=YYYY-MM-DD overrides it to rehearse the warning.
const calToday = () => {
  const override = process.env.CAL_TODAY;
  if (override === undefined) return new Date().toISOString().slice(0, 10);
  assert.match(override, /^\d{4}-\d{2}-\d{2}$/, `CAL_TODAY must be YYYY-MM-DD, got ${JSON.stringify(override)}`);
  assert.equal(new Date(`${override}T00:00:00Z`).toISOString().slice(0, 10), override,
    `CAL_TODAY must be a real calendar date, got ${JSON.stringify(override)}`);
  return override;
};
const daysOfCalendarLeft = today =>
  Math.round((Date.parse(CALENDAR_RANGE_END) - Date.parse(today)) / DAY_MS);

test('XNYS calendar covers at least 120 more days from today', () => {
  const today = calToday();
  assert.ok(daysOfCalendarLeft(today) >= CALENDAR_WARNING_DAYS, calendarCoverageMessage());
});

test('calendar coverage guard fires when CAL_TODAY is inside the 120-day window', () => {
  const inside = new Date(Date.parse(CALENDAR_RANGE_END) - 30 * DAY_MS).toISOString().slice(0, 10);
  const prev = process.env.CAL_TODAY;
  process.env.CAL_TODAY = inside;
  try {
    const today = calToday();
    assert.equal(today, inside, 'CAL_TODAY must drive the guard');
    assert.throws(
      () => assert.ok(daysOfCalendarLeft(today) >= CALENDAR_WARNING_DAYS, calendarCoverageMessage()),
      { message: calendarCoverageMessage() },
    );
  } finally {
    if (prev === undefined) delete process.env.CAL_TODAY; else process.env.CAL_TODAY = prev;
  }
});

test('comparison chart starts from the statement gain over cost, not zero', () => {
  for (const p of [full(), load('portfolio.public.json')]) {
    const [port, spy, picks] = comparisonSeries(p, compute(p));
    assert.equal((port.points[0].y * 100).toFixed(2), '8.97');   // $9,040.18 / $100,831.99
    assert.equal((spy.points[0].y * 100).toFixed(2), '10.81');   // SPY statement gain / its cost
    assert.equal((picks.points[0].y * 100).toFixed(2), '7.18');
  }
});
