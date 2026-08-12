const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const RECENT_BARS = 90;
const ADX_PERIOD = 11;
const ADX_MIN = 25;

type NaverCandle = {
  localDate?: string;
  openPrice?: number;
  highPrice?: number;
  lowPrice?: number;
  closePrice?: number;
  accumulatedTradingVolume?: number;
};

type Candle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

const dateTime = (date: Date, endOfDay = false) => {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}${month}${day}${endOfDay ? "2359" : "0000"}`;
};

function calculateAdx(candles: Candle[], period = ADX_PERIOD) {
  const length = candles.length;
  const tr = Array<number>(length).fill(Number.NaN);
  const positiveDm = Array<number>(length).fill(Number.NaN);
  const negativeDm = Array<number>(length).fill(Number.NaN);

  for (let index = 1; index < length; index += 1) {
    const current = candles[index];
    const previous = candles[index - 1];
    tr[index] = Math.max(
      current.high - current.low,
      Math.abs(current.high - previous.close),
      Math.abs(current.low - previous.close),
    );
    const upward = current.high - previous.high;
    const downward = previous.low - current.low;
    positiveDm[index] = upward > downward && upward > 0 ? upward : 0;
    negativeDm[index] = downward > upward && downward > 0 ? downward : 0;
  }

  const smoothedTr = Array<number>(length).fill(Number.NaN);
  const smoothedPositiveDm = Array<number>(length).fill(Number.NaN);
  const smoothedNegativeDm = Array<number>(length).fill(Number.NaN);
  if (length > period) {
    smoothedTr[period] = tr.slice(1, period + 1).reduce((sum, value) => sum + value, 0);
    smoothedPositiveDm[period] = positiveDm.slice(1, period + 1).reduce((sum, value) => sum + value, 0);
    smoothedNegativeDm[period] = negativeDm.slice(1, period + 1).reduce((sum, value) => sum + value, 0);
    for (let index = period + 1; index < length; index += 1) {
      smoothedTr[index] = smoothedTr[index - 1] - smoothedTr[index - 1] / period + tr[index];
      smoothedPositiveDm[index] = smoothedPositiveDm[index - 1] - smoothedPositiveDm[index - 1] / period + positiveDm[index];
      smoothedNegativeDm[index] = smoothedNegativeDm[index - 1] - smoothedNegativeDm[index - 1] / period + negativeDm[index];
    }
  }

  const dx = Array<number>(length).fill(Number.NaN);
  for (let index = period; index < length; index += 1) {
    if (!Number.isFinite(smoothedTr[index]) || smoothedTr[index] <= 0) continue;
    const positiveDi = 100 * smoothedPositiveDm[index] / smoothedTr[index];
    const negativeDi = 100 * smoothedNegativeDm[index] / smoothedTr[index];
    const sum = positiveDi + negativeDi;
    if (sum > 0) dx[index] = 100 * Math.abs(positiveDi - negativeDi) / sum;
  }

  const adx = Array<number>(length).fill(Number.NaN);
  const first = 2 * period - 1;
  if (length > first) {
    const initialDx = dx.slice(period, first + 1).filter(Number.isFinite);
    if (initialDx.length > 0) {
      adx[first] = initialDx.reduce((sum, value) => sum + value, 0) / initialDx.length;
      for (let index = first + 1; index < length; index += 1) {
        if (Number.isFinite(adx[index - 1]) && Number.isFinite(dx[index])) {
          adx[index] = (adx[index - 1] * (period - 1) + dx[index]) / period;
        }
      }
    }
  }
  return adx;
}

function evaluateResistanceBreakout(symbol: string, candles: Candle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
  ));
  if (valid.length < RECENT_BARS + 2) return null;

  const bearish = valid.slice(-RECENT_BARS).filter((item) => item.close < item.open);
  if (bearish.length === 0) return null;
  const resistanceCandle = bearish.reduce((highestScore, item) => {
    const score = ((item.open + item.close + item.high + item.low) / 4) * item.volume;
    return score > highestScore.score ? { item, score } : highestScore;
  }, { item: bearish[0], score: Number.NEGATIVE_INFINITY }).item;

  const resistance = resistanceCandle.open;
  const today = valid.at(-1)!;
  const previous = valid.at(-2)!;
  if (today.close <= resistance || previous.close > resistance) return null;

  const adxNow = calculateAdx(valid, ADX_PERIOD).at(-1)!;
  if (!Number.isFinite(adxNow) || adxNow <= ADX_MIN) return null;

  return {
    symbol,
    close: Math.round(today.close),
    previousChange: previous.close > 0 ? Number((((today.close / previous.close) - 1) * 100).toFixed(2)) : 0,
    resistance: Math.round(resistance),
    resistanceDistance: Number((((today.close / resistance) - 1) * 100).toFixed(2)),
    resistanceDate: resistanceCandle.date,
    adx11: Number(adxNow.toFixed(1)),
    tradingDate: today.date,
  };
}

async function scanSymbol(symbol: string, start: Date, end: Date) {
  const response = await fetch(
    `https://api.stock.naver.com/chart/domestic/item/${symbol}/day?startDateTime=${dateTime(start)}&endDateTime=${dateTime(end, true)}`,
    {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; DrKsChoice/1.0)",
      },
    },
  );
  if (!response.ok) throw new Error(`${symbol}: ${response.status}`);
  const payload = await response.json() as NaverCandle[];
  const candles = payload
    .flatMap((item) => (
      item.localDate
      && item.openPrice != null
      && item.highPrice != null
      && item.lowPrice != null
      && item.closePrice != null
        ? [{
          date: item.localDate,
          open: Number(item.openPrice),
          high: Number(item.highPrice),
          low: Number(item.lowPrice),
          close: Number(item.closePrice),
          volume: Number(item.accumulatedTradingVolume ?? 0),
        }]
        : []
    ))
    .sort((left, right) => left.date.localeCompare(right.date));
  return evaluateResistanceBreakout(symbol, candles);
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const symbols = [...new Set(
    (url.searchParams.get("symbols") ?? "")
      .split(",")
      .map((symbol) => symbol.trim().toUpperCase())
      .filter((symbol) => /^[0-9A-Z]{6}$/.test(symbol)),
  )].slice(0, MAX_SYMBOLS);

  if (symbols.length === 0) {
    return Response.json({ error: "올바른 종목 코드를 입력해 주세요." }, { status: 400 });
  }

  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 320);
  const results: NonNullable<Awaited<ReturnType<typeof scanSymbol>>>[] = [];
  const failed: string[] = [];
  let evaluated = 0;
  let nextSymbol = 0;

  const worker = async () => {
    while (nextSymbol < symbols.length) {
      const symbol = symbols[nextSymbol];
      nextSymbol += 1;
      try {
        const result = await scanSymbol(symbol, start, end);
        evaluated += 1;
        if (result) results.push(result);
      } catch {
        failed.push(symbol);
      }
    }
  };

  await Promise.all(Array.from({ length: Math.min(MAX_CONCURRENCY, symbols.length) }, () => worker()));

  return Response.json({
    source: "NAVER Finance",
    updatedAt: new Date().toISOString(),
    rule: { recentBars: RECENT_BARS, adxPeriod: ADX_PERIOD, adxMin: ADX_MIN },
    evaluated,
    results: results.sort((left, right) => left.resistanceDistance - right.resistanceDistance),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
