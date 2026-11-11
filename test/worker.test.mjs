// Worker refresh logic against a fake KV and fake provider responses. No network.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker, { refresh, shouldFetch, validate, SYMBOLS } from '../worker/index.js';

const fakeKV = () => {
  const m = new Map();
  return {
    m,
    async get(k, type) { const v = m.get(k); return v === undefined ? null : type === 'json' ? JSON.parse(v) : v; },
    async put(k, v) { m.set(k, v); },
  };
};
const env = kv => ({ PROVIDER: 'twelvedata', DELAY_MINUTES: '0', MARKET_SCOPE: 'partial', TWELVEDATA_KEY: 'k', QUOTES: kv });

// Twelve Data batch /quote body for every symbol at one quote time.
const tdBody = (quoteIso, bump = 0, drop = null) => Object.fromEntries(SYMBOLS.filter(s => s !== drop).map((s, i) => [
  s.replace('/', '.'),
  { symbol: s.replace('/', '.'), currency: 'USD', close: String(100 + i + bump), previous_close: String(99 + i),
    last_quote_at: Date.parse(quoteIso) / 1000, is_market_open: true },
]));
const fetchReturning = body => async (url, init) => {
  assert.match(url, /api\.twelvedata\.com\/quote\?symbol=AAPL,AMD,.*BRK\.B.*&prepost=false/);
  assert.equal(init.headers.Authorization, 'apikey k');
  return new Response(JSON.stringify(body), { status: 200 });
};

test('cron gate: fetches during the session and 20 minutes after the close only', () => {
  assert.equal(shouldFetch(new Date('2026-10-21T13:29:00Z')), false); // 9:29 AM EDT, before the open
  assert.equal(shouldFetch(new Date('2026-10-21T13:31:00Z')), true);  // 9:31 AM EDT
  assert.equal(shouldFetch(new Date('2026-10-21T20:10:00Z')), true);  // 4:10 PM close capture
  assert.equal(shouldFetch(new Date('2026-10-21T20:25:00Z')), false); // 4:25 PM
  assert.equal(shouldFetch(new Date('2026-11-26T15:00:00Z')), false); // Thanksgiving
  assert.equal(shouldFetch(new Date('2026-11-27T18:10:00Z')), true);  // 1:10 PM after 1 PM early close
  assert.equal(shouldFetch(new Date('2026-12-07T14:45:00Z')), true);  // 9:45 AM EST
});

test('refresh stores a complete snapshot and /api/quotes serves it without health', async () => {
  const kv = fakeKV();
  const now = new Date('2026-10-21T15:00:00Z');
  const r = await refresh(env(kv), now, fetchReturning(tdBody('2026-10-21T14:44:30Z')));
  assert.equal(r.ok, true);
  const res = await worker.fetch(new Request('https://x/api/quotes'), env(kv));
  const snap = await res.json();
  assert.equal(snap.quotes.length, 18);
  assert.equal(snap.quotes.find(q => q.symbol === 'BRK/B').price, '103');
  assert.equal(snap.meta.delay_minutes, 0);
  assert.equal(snap.meta.market_scope, 'partial');
  assert.equal(snap.health, undefined);
  assert.equal(res.headers.get('cache-control'), 'no-store');
});

test('an incomplete or older provider response keeps the last good prices', async () => {
  const kv = fakeKV();
  await refresh(env(kv), new Date('2026-10-21T15:00:00Z'), fetchReturning(tdBody('2026-10-21T14:44:30Z')));
  const good = JSON.parse(kv.m.get('quotes:latest')).quotes;

  const missing = await refresh(env(kv), new Date('2026-10-21T15:01:00Z'), fetchReturning(tdBody('2026-10-21T14:45:30Z', 1, 'SOFI')));
  assert.equal(missing.ok, false);
  assert.match(missing.error, /SOFI/);
  const older = await refresh(env(kv), new Date('2026-10-21T15:02:00Z'), fetchReturning(tdBody('2026-10-21T14:30:00Z', 2)));
  assert.equal(older.ok, false);
  const http500 = await refresh(env(kv), new Date('2026-10-21T15:03:00Z'), async () => new Response('down', { status: 500 }));
  assert.equal(http500.ok, false);

  const stored = JSON.parse(kv.m.get('quotes:latest'));
  assert.deepEqual(stored.quotes, good);
  assert.equal(stored.health.ok, false);
  const health = await (await worker.fetch(new Request('https://x/api/health'), env(kv))).json();
  assert.equal(health.last_attempt.ok, false);
});

test('after the close, one history entry per session, updated in place', async () => {
  const kv = fakeKV();
  await refresh(env(kv), new Date('2026-10-21T20:01:00Z'), fetchReturning(tdBody('2026-10-21T19:45:00Z')));
  await refresh(env(kv), new Date('2026-10-21T20:02:00Z'), fetchReturning(tdBody('2026-10-21T19:46:00Z')));
  await refresh(env(kv), new Date('2026-10-21T20:03:00Z'), fetchReturning(tdBody('2026-10-21T19:47:00Z', 0.5)));
  const hist = await (await worker.fetch(new Request('https://x/api/history'), env(kv))).json();
  assert.equal(hist.length, 1);
  assert.equal(hist[0].date, '2026-10-21');
  assert.equal(hist[0].prices.AAPL, '100.5');
  // during the session: no history write
  const kv2 = fakeKV();
  await refresh(env(kv2), new Date('2026-10-21T15:00:00Z'), fetchReturning(tdBody('2026-10-21T14:44:30Z')));
  assert.equal(kv2.m.has('history'), false);
});

test('tiingo adapter maps the IEX response, including BRK.B', async () => {
  const { tiingo } = await import('../worker/providers.js');
  const body = SYMBOLS.map((s, i) => ({ ticker: s.replace('/', '.').toLowerCase(), last: 50 + i, prevClose: 49 + i,
    lastSaleTimestamp: '2026-10-21T14:59:58.123Z' }));
  const rows = await tiingo.fetch(SYMBOLS, { TIINGO_KEY: 't' }, async (url, init) => {
    assert.match(url, /api\.tiingo\.com\/iex\/\?tickers=aapl,amd,.*brk\.b/);
    assert.equal(init.headers.Authorization, 'Token t');
    return new Response(JSON.stringify(body), { status: 200 });
  });
  assert.equal(rows.length, 18);
  assert.equal(rows.find(r => r.symbol === 'BRK/B').price, '53');
  await assert.rejects(tiingo.fetch(SYMBOLS, { TIINGO_KEY: 't' }, async () => new Response(JSON.stringify(body.slice(1)), { status: 200 })), /incomplete quote for AAPL/);
});

test('a provider outage (thrown fetch or non-200) keeps the last good snapshot, no partial write', async () => {
  const kv = fakeKV();
  await refresh(env(kv), new Date('2026-10-21T15:00:00Z'), fetchReturning(tdBody('2026-10-21T14:44:30Z')));
  const good = JSON.parse(kv.m.get('quotes:latest')).quotes;

  const thrown = await refresh(env(kv), new Date('2026-10-21T15:01:00Z'), async () => { throw new Error('getaddrinfo ENOTFOUND'); });
  assert.equal(thrown.ok, false);
  assert.match(thrown.error, /ENOTFOUND/);
  const http503 = await refresh(env(kv), new Date('2026-10-21T15:02:00Z'), async () => new Response('maintenance', { status: 503 }));
  assert.equal(http503.ok, false);
  assert.match(http503.error, /HTTP 503/);

  const stored = JSON.parse(kv.m.get('quotes:latest'));
  assert.deepEqual(stored.quotes, good);
  assert.equal(stored.health.ok, false);
  assert.match(stored.health.error, /HTTP 503/);
  const snap = await (await worker.fetch(new Request('https://x/api/quotes'), env(kv))).json();
  assert.equal(snap.quotes.length, 18); // /api/quotes still serves the last good snapshot
});

test('a valid JSON response with a symbol missing from SYMBOLS is treated as incomplete', async () => {
  const kv = fakeKV();
  await refresh(env(kv), new Date('2026-10-21T15:00:00Z'), fetchReturning(tdBody('2026-10-21T14:44:30Z')));
  const good = JSON.parse(kv.m.get('quotes:latest')).quotes;

  // 200 with parseable JSON, but SOFI's slot carries HOOD, which is not in SYMBOLS
  const body = tdBody('2026-10-21T14:46:30Z', 3);
  body['HOOD'] = body['SOFI'];
  delete body['SOFI'];
  const r = await refresh(env(kv), new Date('2026-10-21T15:01:00Z'), fetchReturning(body));
  assert.equal(r.ok, false);
  assert.match(r.error, /incomplete quote for SOFI/);
  const stored = JSON.parse(kv.m.get('quotes:latest'));
  assert.deepEqual(stored.quotes, good);
  assert.equal(stored.health.ok, false);

  // validate() is the backstop: an unknown or repeated symbol is rejected outright
  const rows = SYMBOLS.map((s, i) => ({ symbol: s, price: String(100 + i), previous_close: String(99 + i),
    currency: 'USD', provider_update_at_utc: '2026-10-21T14:46:30Z' }));
  const now = new Date('2026-10-21T15:01:00Z');
  assert.throws(() => validate([...rows.slice(0, 17), { ...rows[0], symbol: 'HOOD' }], now), /unexpected or duplicate symbol HOOD/);
  assert.throws(() => validate([...rows.slice(0, 17), { ...rows[0], symbol: 'AAPL' }], now), /unexpected or duplicate symbol AAPL/);
});

test('cron gate: before the session and past the capture window the handler never fetches', async () => {
  const realFetch = globalThis.fetch;
  let calls = 0;
  try {
    const gateRun = async iso => {
      calls = 0;
      globalThis.fetch = async () => { calls++; throw new Error('unexpected fetch at ' + iso); };
      const kv = fakeKV();
      const waits = [];
      await worker.scheduled({ scheduledTime: Date.parse(iso) }, env(kv), { waitUntil: p => waits.push(p) });
      await Promise.all(waits);
      assert.equal(calls, 0);
      assert.equal(kv.m.size, 0);
    };
    await gateRun('2026-10-21T13:29:00Z'); // 9:29 AM EDT, before the open
    await gateRun('2026-10-21T20:25:00Z'); // 4:25 PM EDT, past the 20-minute capture window
    // positive control: the same wiring does fetch inside the session, so the zeros above are real
    globalThis.fetch = async (url, init) => fetchReturning(tdBody('2026-10-21T14:44:30Z'))(url, init);
    const kv = fakeKV();
    const waits = [];
    await worker.scheduled({ scheduledTime: Date.parse('2026-10-21T15:00:00Z') }, env(kv), { waitUntil: p => waits.push(p) });
    await Promise.all(waits);
    assert.equal(await (await worker.fetch(new Request('https://x/api/quotes'), env(kv))).json().then(s => s.quotes.length), 18);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('a failing KV put never lets the refresh claim success', async () => {
  const kv = fakeKV();
  await refresh(env(kv), new Date('2026-10-21T15:00:00Z'), fetchReturning(tdBody('2026-10-21T14:44:30Z')));
  const good = JSON.parse(kv.m.get('quotes:latest')).quotes;
  const goodBytes = kv.m.get('quotes:latest');

  // put fails every time: refresh rejects instead of returning ok:true, stored bytes untouched
  const down = { m: kv.m, get: kv.get, put: async () => { throw new Error('kv write failed'); } };
  await assert.rejects(refresh(env(down), new Date('2026-10-21T15:01:00Z'), fetchReturning(tdBody('2026-10-21T14:45:30Z', 1))), /kv write failed/);
  assert.equal(kv.m.get('quotes:latest'), goodBytes);

  // only the snapshot write fails: the handler reports failure, it does not claim success
  let failed = false;
  const failOnce = { m: kv.m, get: kv.get, put: async (k, v) => {
    if (!failed) { failed = true; throw new Error('kv write failed'); }
    kv.m.set(k, v);
  } };
  const r = await refresh(env(failOnce), new Date('2026-10-21T15:02:00Z'), fetchReturning(tdBody('2026-10-21T14:46:30Z', 2)));
  assert.equal(r.ok, false);
  assert.match(r.error, /kv write failed/);
  const stored = JSON.parse(kv.m.get('quotes:latest'));
  assert.deepEqual(stored.quotes, good);
  assert.equal(stored.health.ok, false);
});
