const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const FAST_PERIOD = 5;
const FAST_LAG = 2;
const SLOW_PERIOD = 20;
const SLOW_LAG = 9;
const RSI_PERIOD = 30;
const RSI_LEVEL = 70;

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

function exponentialMovingAverage(values: number[], period: number) {
  const averages = Array<number>(values.length).fill(Number.NaN);
  const first = values.findIndex(Number.isFinite);
  if (first < 0) return averages;
  const alpha = 2 / (period + 1);
  averages[first] = values[first];
  for (let index = first + 1; index < values.length; index += 1) {
    if (!Number.isFinite(values[index])) continue;
    averages[index] = values[index] * alpha + averages[index - 1] * (1 - alpha);
  }
  return averages;
}

function zeroLagEma(closes: number[], period: number, lag: number) {
  const adjusted = closes.map((close, index) => (
    index >= lag ? close + (close - closes[index - lag]) : Number.NaN
  ));
  return exponentialMovingAverage(adjusted, period);
}

function wilderRsi(closes: number[], period: number) {
  const rsi = Array<number>(closes.length).fill(Number.NaN);
  if (closes.length <= period) return rsi;
  let averageGain = 0;
  let averageLoss = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = closes[index] - closes[index - 1];
    averageGain += Math.max(change, 0);
    averageLoss += Math.max(-change, 0);
  }
  averageGain /= period;
  averageLoss /= period;
  rsi[period] = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
  for (let index = period + 1; index < closes.length; index += 1) {
    const change = closes[index] - closes[index - 1];
    averageGain = (averageGain * (period - 1) + Math.max(change, 0)) / period;
    averageLoss = (averageLoss * (period - 1) + Math.max(-change, 0)) / period;
    rsi[index] = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
  }
  return rsi;
}

const crossedUp = (current: number, previous: number, currentReference: number, previousReference: number) => (
  [current, previous, currentReference, previousReference].every(Number.isFinite)
  && current > currentReference
  && previous <= previousReference
);

function evaluateZlema(symbol: string, candles: Candle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
  ));
  if (valid.length < RSI_PERIOD + 4) return null;

  const closes = valid.map((item) => item.close);
  const zlema5 = zeroLagEma(closes, FAST_PERIOD, FAST_LAG);
  const zlema20 = zeroLagEma(closes, SLOW_PERIOD, SLOW_LAG);
  const rsi30 = wilderRsi(closes, RSI_PERIOD);
  const last = valid.length - 1;

  const goldenCrossToday = crossedUp(zlema5[last], zlema5[last - 1], zlema20[last], zlema20[last - 1]);
  const goldenCrossYesterday = crossedUp(zlema5[last - 1], zlema5[last - 2], zlema20[last - 1], zlema20[last - 2]);
  const rsiBreakoutToday = crossedUp(rsi30[last], rsi30[last - 1], RSI_LEVEL, RSI_LEVEL);
  const rsiBreakoutYesterday = crossedUp(rsi30[last - 1], rsi30[last - 2], RSI_LEVEL, RSI_LEVEL);

  if (!(goldenCrossToday || goldenCrossYesterday) || !(rsiBreakoutToday || rsiBreakoutYesterday)) return null;

  const goldenCrossBarsAgo = goldenCrossToday ? 0 : 1;
  const rsiBreakoutBarsAgo = rsiBreakoutToday ? 0 : 1;
  return {
    symbol,
    tradingDate: valid[last].date,
    close: Math.round(valid[last].close),
    zlema5: Number(zlema5[last].toFixed(2)),
    zlema20: Number(zlema20[last].toFixed(2)),
    rsi30: Number(rsi30[last].toFixed(2)),
    goldenCrossBarsAgo,
    rsiBreakoutBarsAgo,
    goldenCrossDate: valid[last - goldenCrossBarsAgo].date,
    rsiBreakoutDate: valid[last - rsiBreakoutBarsAgo].date,
    signalType: "ZLEMA 골든크로스 · RSI(30) 70 돌파",
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
  const candles = payload.flatMap((item) => (
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
  )).sort((left, right) => left.date.localeCompare(right.date));
  return evaluateZlema(symbol, candles);
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
  start.setUTCDate(start.getUTCDate() - 360);
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
    rule: {
      zlema5: "EMA(C + (C - C[2]), 5)",
      zlema20: "EMA(C + (C - C[9]), 20)",
      rsi: "Wilder RSI(30)",
      rsiBreakoutLevel: RSI_LEVEL,
      lookbackBars: 2,
    },
    evaluated,
    results: results.sort((left, right) => (
      left.goldenCrossBarsAgo + left.rsiBreakoutBarsAgo
      - right.goldenCrossBarsAgo - right.rsiBreakoutBarsAgo
    )),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
