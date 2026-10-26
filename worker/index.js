// Cloudflare Worker: serves the TV and web views, and refreshes quotes on a cron.
//   GET /api/quotes   latest complete portfolio-quotes.v1 snapshot (last good on failure)
//   GET /api/history  one closing snapshot per session, oldest first
//   GET /api/health   last refresh attempt, for whoever runs this after handoff
// Cron (UTC) "* 13-21 * * 1-5" covers the NYSE session in both EDT and EST; the
// NYSE calendar below decides whether a given minute actually fetches.

import { marketStatus, etParts } from '../web/core.js';
import calendar from '../data/source/xnys-calendar.json' with { type: 'json' };
import { PROVIDERS } from './providers.js';

export const SYMBOLS = ['AAPL', 'AMD', 'AMZN', 'BRK/B', 'CEG', 'DOCN', 'GOOGL', 'LIN', 'META', 'MKSI',
  'MSFT', 'NFLX', 'NVDA', 'RDDT', 'SOFI', 'SPY', 'TSLA', 'UPS'];
const CLOSE_CAPTURE_MINUTES = 20;   // keep fetching this long after the bell for closing prices
const HISTORY_MAX = 400;            // about 18 months of sessions

const json = (body, status = 200, extra = {}) => new Response(JSON.stringify(body), {
  status,
  headers: { 'content-type': 'application/json', 'cache-control': 'no-store', 'x-robots-tag': 'noindex', ...extra },
});

export function shouldFetch(now) {
  const st = marketStatus(now, calendar);
  if (st.state === 'open') return true;
  if (st.state !== 'after' || st.lastClosedSession !== st.ymd) return false;
  return etParts(now).minutes < st.lastClosedAt + CLOSE_CAPTURE_MINUTES;
}

// One refresh: fetch, validate, store. A failure leaves the stored snapshot untouched.
export async function refresh(env, now = new Date(), fetchImpl = fetch) {
  const provider = PROVIDERS[env.PROVIDER];
  if (!provider) throw new Error(`unknown PROVIDER "${env.PROVIDER}"`);
  const health = { attempted_at_utc: now.toISOString(), provider: provider.id };
  try {
    const rows = await provider.fetch(SYMBOLS, env, fetchImpl);
    validate(rows, now);
    const prev = await env.QUOTES.get('quotes:latest', 'json');
    const prevNewest = prev ? Math.max(...prev.quotes.map(q => Date.parse(q.provider_update_at_utc))) : 0;
    const newest = Math.max(...rows.map(q => Date.parse(q.provider_update_at_utc)));
    if (newest < prevNewest) throw new Error('provider returned older prices than the stored snapshot');
    const snap = {
      schema: 'portfolio-quotes.v1', collected_at_utc: now.toISOString(), quotes: rows,
      meta: {
        provider: provider.id, attribution: provider.attribution, attribution_url: provider.attributionUrl,
        delay_minutes: Number(env.DELAY_MINUTES ?? 15),
        // "partial": single-venue or partial-market prices (Twelve Data's default US feed, Tiingo IEX)
        market_scope: env.MARKET_SCOPE || 'consolidated',
      },
    };
    await env.QUOTES.put('quotes:latest', JSON.stringify({ ...snap, health: { ...health, ok: true } }));
    await maybeAppendClose(env, snap, now);
    return { ok: true, newest: new Date(newest).toISOString() };
  } catch (err) {
    health.ok = false;
    health.error = String(err.message || err).slice(0, 300);
    // Record the failure without replacing good prices: health rides on the stored snapshot.
    const prev = await env.QUOTES.get('quotes:latest', 'json');
    if (prev) await env.QUOTES.put('quotes:latest', JSON.stringify({ ...prev, health }));
    else await env.QUOTES.put('quotes:latest', JSON.stringify({ schema: 'portfolio-quotes.v1', quotes: [], health }));
    return { ok: false, error: health.error };
  }
}

export function validate(rows, now) {
  if (rows.length !== SYMBOLS.length) throw new Error(`expected ${SYMBOLS.length} quotes, got ${rows.length}`);
  const seen = new Set();
  for (const q of rows) {
    if (!SYMBOLS.includes(q.symbol) || seen.has(q.symbol)) throw new Error(`unexpected or duplicate symbol ${q.symbol}`);
    seen.add(q.symbol);
    for (const k of ['price', 'previous_close']) {
      if (!/^\d+(\.\d+)?$/.test(q[k]) || !(Number(q[k]) > 0)) throw new Error(`${q.symbol}: bad ${k} ${q[k]}`);
    }
    const t = Date.parse(q.provider_update_at_utc);
    if (!Number.isFinite(t) || t > now.getTime() + 60000) throw new Error(`${q.symbol}: bad or future timestamp`);
    if (q.currency !== 'USD') throw new Error(`${q.symbol}: currency ${q.currency}`);
  }
}

// After the close, keep one snapshot per session for the chart.
async function maybeAppendClose(env, snap, now) {
  const st = marketStatus(now, calendar);
  if (st.state !== 'after' || st.lastClosedSession !== st.ymd) return;
  const history = (await env.QUOTES.get('history', 'json')) || [];
  const entry = { date: st.ymd, collected_at_utc: snap.collected_at_utc,
    prices: Object.fromEntries(snap.quotes.map(q => [q.symbol, q.price])) };
  const i = history.findIndex(h => h.date === st.ymd);
  if (i >= 0) {
    if (JSON.stringify(history[i].prices) === JSON.stringify(entry.prices)) return; // no new write
    history[i] = entry;
  } else history.push(entry);
  await env.QUOTES.put('history', JSON.stringify(history.slice(-HISTORY_MAX)));
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === '/api/quotes') {
      const snap = await env.QUOTES.get('quotes:latest', 'json');
      if (!snap || !snap.quotes?.length) return json({ error: 'no quotes stored yet' }, 503);
      const { health, ...rest } = snap;
      return json(rest);
    }
    if (pathname === '/api/history') return json((await env.QUOTES.get('history', 'json')) || []);
    if (pathname === '/api/health') {
      const snap = await env.QUOTES.get('quotes:latest', 'json');
      return json({ provider: env.PROVIDER, last_attempt: snap?.health || null,
        newest_quote_utc: snap?.quotes?.length ? new Date(Math.max(...snap.quotes.map(q => Date.parse(q.provider_update_at_utc)))).toISOString() : null,
        market: marketStatus(new Date(), calendar) });
    }
    const res = await env.ASSETS.fetch(request);
    const out = new Response(res.body, res);
    out.headers.set('x-robots-tag', 'noindex');
    out.headers.set('x-frame-options', 'DENY');
    return out;
  },

  async scheduled(controller, env, ctx) {
    const now = new Date(controller.scheduledTime);
    if (!shouldFetch(now)) return;
    ctx.waitUntil(refresh(env, now));
  },
};
