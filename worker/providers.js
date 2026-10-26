// Quote-feed adapters. Each returns portfolio-quotes.v1 rows for every symbol or throws.
// The club's symbols use "BRK/B"; providers want "BRK.B".
//
// Only feeds whose licence can cover showing prices to other people belong here.
// Checked 2026-10-21: Alpaca ("cannot redistribute"), Finnhub ("strictly for personal use"),
// Massive/Polygon, Alpha Vantage, FMP, EODHD, Yahoo and Google Finance do not, so there is
// deliberately no adapter for them.
//   twelvedata: needs a Venture plan ("External display data access") or a non-profit grant
//               that explicitly covers public display. Basic is "Internal non-display".
//   tiingo:     needs the EOD + IEX "Display Redistribution" tier, not Starter/Power.

const toProvider = s => s.replace('/', '.');
const iso = ms => new Date(ms).toISOString().replace('.000Z', 'Z');

async function getJson(url, init, fetchImpl) {
  const res = await fetchImpl(url, { ...init, redirect: 'error', signal: AbortSignal.timeout(8000) });
  const text = await res.text();
  if (!res.ok) throw new Error(`${new URL(url).host} HTTP ${res.status}: ${text.slice(0, 200)}`);
  return JSON.parse(text);
}

// Twelve Data /quote batch: one request, one credit per symbol (18 per refresh).
export const twelvedata = {
  id: 'twelvedata',
  attribution: 'Data provided by Twelve Data',
  attributionUrl: 'https://twelvedata.com',
  async fetch(symbols, env, fetchImpl = fetch) {
    const url = `https://api.twelvedata.com/quote?symbol=${symbols.map(toProvider).join(',')}&prepost=false`;
    const body = await getJson(url, { headers: { Authorization: `apikey ${env.TWELVEDATA_KEY}` } }, fetchImpl);
    if (body.status === 'error') throw new Error(`twelvedata: ${body.message || 'error'}`);
    const retrieved = iso(Date.now());
    return symbols.map(sym => {
      const q = symbols.length === 1 ? body : body[toProvider(sym)];
      if (!q || q.status === 'error' || !q.close || !q.previous_close || !q.last_quote_at) {
        throw new Error(`twelvedata: incomplete quote for ${sym}${q?.message ? `: ${q.message}` : ''}`);
      }
      return {
        symbol: sym, price: String(q.close), previous_close: String(q.previous_close), currency: q.currency || 'USD',
        provider_update_at_utc: iso(Number(q.last_quote_at) * 1000), retrieved_at_utc: retrieved,
        provider: 'Twelve Data', source_url: 'https://twelvedata.com', session: q.is_market_open ? 'regular' : 'closed',
      };
    });
  },
};

// Tiingo IEX endpoint: one request for all tickers. IEX-only prices.
export const tiingo = {
  id: 'tiingo',
  attribution: 'Data sourced by Tiingo (IEX)',
  attributionUrl: 'https://www.tiingo.com',
  async fetch(symbols, env, fetchImpl = fetch) {
    const url = `https://api.tiingo.com/iex/?tickers=${symbols.map(s => toProvider(s).toLowerCase()).join(',')}`;
    const body = await getJson(url, { headers: { Authorization: `Token ${env.TIINGO_KEY}` } }, fetchImpl);
    const retrieved = iso(Date.now());
    const by = new Map((Array.isArray(body) ? body : []).map(q => [String(q.ticker).toUpperCase(), q]));
    return symbols.map(sym => {
      const q = by.get(toProvider(sym));
      const price = q?.last ?? q?.tngoLast;
      const t = q?.lastSaleTimestamp || q?.timestamp;
      if (!price || !q?.prevClose || !t) throw new Error(`tiingo: incomplete quote for ${sym}`);
      return {
        symbol: sym, price: String(price), previous_close: String(q.prevClose), currency: 'USD',
        provider_update_at_utc: iso(Date.parse(t)), retrieved_at_utc: retrieved,
        provider: 'Tiingo', source_url: 'https://www.tiingo.com', session: 'regular',
      };
    });
  },
};

export const PROVIDERS = { twelvedata, tiingo };
