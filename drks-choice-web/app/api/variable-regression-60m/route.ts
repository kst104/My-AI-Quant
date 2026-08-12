const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 3;
const REGRESSION_PERIOD = 50;

type YahooChart = {
  chart?: {
    result?: Array<{
      timestamp?: number[];
      indicators?: {
        quote?: Array<{
          close?: Array<number | null>;
        }>;
      };
    }>;
    error?: { description?: string } | null;
  };
};

function linearRegressionValue(values: number[], period: number) {
  const output = Array<number>(values.length).fill(Number.NaN);
  const sumX = period * (period - 1) / 2;
  const sumXX = period * (period - 1) * (2 * period - 1) / 6;
  const denominator = period * sumXX - sumX * sumX;

  for (let index = period - 1; index < values.length; index += 1) {
    const window = values.slice(index - period + 1, index + 1);
    if (!window.every(Number.isFinite)) continue;
    const sumY = window.reduce((sum, value) => sum + value, 0);
    const sumXY = window.reduce((sum, value, x) => sum + x * value, 0);
    const slope = (period * sumXY - sumX * sumY) / denominator;
    const intercept = (sumY - slope * sumX) / period;
    output[index] = intercept + slope * (period - 1);
  }
  return output;
}

async function scanTicker(ticker: string) {
  const response = await fetch(
    `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?interval=60m&range=1mo&includePrePost=false&events=div%2Csplits`,
    {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; DrKsChoice/1.0)",
      },
    },
  );
  if (!response.ok) throw new Error(`${ticker}: ${response.status}`);
  const payload = await response.json() as YahooChart;
  const chart = payload.chart?.result?.[0];
  const timestamps = chart?.timestamp ?? [];
  const closes = chart?.indicators?.quote?.[0]?.close ?? [];
  const bars = timestamps.flatMap((timestamp, index) => {
    const close = closes[index];
    return close != null && Number.isFinite(close) ? [{ timestamp, close: Number(close) }] : [];
  });
  if (bars.length < REGRESSION_PERIOD * 2 + 1) return null;

  const closeValues = bars.map((bar) => bar.close);
  const regression = linearRegressionValue(closeValues, REGRESSION_PERIOD);
  const regressionAgain = linearRegressionValue(regression, REGRESSION_PERIOD);
  const variableLine = regression.map((value, index) => (
    Number.isFinite(value) && Number.isFinite(regressionAgain[index])
      ? value + (value - regressionAgain[index])
      : Number.NaN
  ));
  const last = bars.length - 1;
  const close = closeValues[last];
  const currentVl = variableLine[last];
  const previousVl = variableLine[last - 1];
  const twoBarsAgoVl = variableLine[last - 2];
  if (![close, currentVl, previousVl, twoBarsAgoVl].every(Number.isFinite)) return null;

  const firstUpturn = currentVl > previousVl && previousVl <= twoBarsAgoVl;
  if (!(close > currentVl && firstUpturn)) return null;

  const symbol = ticker.replace(/\.(KS|KQ)$/i, "");
  return {
    symbol,
    ticker,
    tradingDateTime: new Date(bars[last].timestamp * 1000).toISOString(),
    close: Math.round(close),
    regression50: Number(regression[last].toFixed(2)),
    regressionAgain50: Number(regressionAgain[last].toFixed(2)),
    equilibrium: Number((regression[last] - regressionAgain[last]).toFixed(2)),
    variableLine: Number(currentVl.toFixed(2)),
    previousVariableLine: Number(previousVl.toFixed(2)),
    twoBarsAgoVariableLine: Number(twoBarsAgoVl.toFixed(2)),
    distancePercent: Number((((close / currentVl) - 1) * 100).toFixed(3)),
    signalType: "60분 VL 첫 상승 변곡 · 종가 상단",
  };
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const tickers = [...new Set(
    (url.searchParams.get("tickers") ?? "")
      .split(",")
      .map((ticker) => ticker.trim().toUpperCase())
      .filter((ticker) => /^[0-9A-Z]{6}\.(KS|KQ)$/.test(ticker)),
  )].slice(0, MAX_SYMBOLS);

  if (tickers.length === 0) {
    return Response.json({ error: "올바른 KOSPI·KOSDAQ 종목 코드를 입력해 주세요." }, { status: 400 });
  }

  const results: NonNullable<Awaited<ReturnType<typeof scanTicker>>>[] = [];
  const failed: string[] = [];
  let evaluated = 0;
  let nextTicker = 0;

  const worker = async () => {
    while (nextTicker < tickers.length) {
      const ticker = tickers[nextTicker];
      nextTicker += 1;
      try {
        const result = await scanTicker(ticker);
        evaluated += 1;
        if (result) results.push(result);
      } catch {
        failed.push(ticker.replace(/\.(KS|KQ)$/i, ""));
      }
    }
  };

  await Promise.all(Array.from({ length: Math.min(MAX_CONCURRENCY, tickers.length) }, () => worker()));

  return Response.json({
    source: "Yahoo Finance 60-minute chart",
    updatedAt: new Date().toISOString(),
    rule: {
      period: REGRESSION_PERIOD,
      formula: "A=LRV(C,50,0); A1=LRV(A,50,0); eq=A-A1; VL=A+eq",
      priceCondition: "Close > VL",
      inflectionCondition: "VL[0] > VL[1] AND VL[1] <= VL[2]",
      minimumMarketCapKrw: 300_000_000_000,
    },
    evaluated,
    results: results.sort((left, right) => left.distancePercent - right.distancePercent),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
