const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const BASIS_TYPE = 3;
const LENGTH = 20;
const TIME_MODE = 2;
const DAILY_WIDTH_FACTOR = 7;
const UPPER_PERCENT = 4.65;
const LOWER_PERCENT = 4.18;
const SIGNAL_MODE = 1;

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

function simpleMovingAverage(values: number[], period: number) {
  const averages = Array<number>(values.length).fill(Number.NaN);
  let sum = 0;
  for (let index = 0; index < values.length; index += 1) {
    sum += values[index];
    if (index >= period) sum -= values[index - period];
    if (index >= period - 1) averages[index] = sum / period;
  }
  return averages;
}

function exponentialMovingAverage(values: number[], period: number, seed: number[]) {
  const averages = Array<number>(values.length).fill(Number.NaN);
  if (values.length < period) return averages;
  const alpha = 2 / (period + 1);
  averages[period - 1] = seed[period - 1];
  for (let index = period; index < values.length; index += 1) {
    averages[index] = values[index] * alpha + averages[index - 1] * (1 - alpha);
  }
  return averages;
}

function runningMovingAverage(values: number[], period: number, seed: number[]) {
  const averages = Array<number>(values.length).fill(Number.NaN);
  if (values.length < period) return averages;
  averages[period - 1] = seed[period - 1];
  for (let index = period; index < values.length; index += 1) {
    averages[index] = (averages[index - 1] * (period - 1) + values[index]) / period;
  }
  return averages;
}

function evaluateMultiEnvelope(symbol: string, candles: Candle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
  ));
  if (valid.length < LENGTH + 1) return null;

  const closes = valid.map((item) => item.close);
  const basisSma = simpleMovingAverage(closes, LENGTH);
  const basisEma = exponentialMovingAverage(closes, LENGTH, basisSma);
  const basisRma = runningMovingAverage(closes, LENGTH, basisSma);
  const basis = BASIS_TYPE === 1 ? basisSma : BASIS_TYPE === 2 ? basisEma : basisRma;
  const devScale = TIME_MODE === 2 ? DAILY_WIDTH_FACTOR : 1;
  const upperMultiplier = 1 + (UPPER_PERCENT * devScale) / 100;
  const lowerMultiplier = 1 - (LOWER_PERCENT * devScale) / 100;
  const upper8 = basis.map((value) => value * upperMultiplier);
  const lower8 = basis.map((value) => value * lowerMultiplier);

  const today = valid.at(-1)!;
  const yesterday = valid.at(-2)!;
  const todayBasis = basis.at(-1)!;
  const yesterdayBasis = basis.at(-2)!;
  const todayUpper8 = upper8.at(-1)!;
  const yesterdayUpper8 = upper8.at(-2)!;
  const todayLower8 = lower8.at(-1)!;
  const yesterdayLower8 = lower8.at(-2)!;

  if (![todayBasis, yesterdayBasis, todayUpper8, yesterdayUpper8, todayLower8, yesterdayLower8].every(Number.isFinite)) {
    return null;
  }

  const crossUp = yesterday.close <= yesterdayLower8 && today.close > todayLower8;
  const crossDown = yesterday.close >= yesterdayUpper8 && today.close < todayUpper8;
  const buySignal = (today.low < todayLower8 || yesterday.low < yesterdayLower8) && crossUp;
  const sellSignal = (today.high > todayUpper8 || yesterday.high > yesterdayUpper8) && crossDown;
  const isMatch = SIGNAL_MODE === 1
    ? buySignal
    : SIGNAL_MODE === 2
      ? sellSignal
      : buySignal || sellSignal;
  if (!isMatch) return null;

  const recoveryPercent = (today.close / todayLower8 - 1) * 100;
  const lowPenetrationPercent = Math.min(
    (today.low / todayLower8 - 1) * 100,
    (yesterday.low / yesterdayLower8 - 1) * 100,
  );

  return {
    symbol,
    tradingDate: today.date,
    close: Math.round(today.close),
    basis: Number(todayBasis.toFixed(2)),
    upper8: Number(todayUpper8.toFixed(2)),
    lower8: Number(todayLower8.toFixed(2)),
    recoveryPercent: Number(recoveryPercent.toFixed(2)),
    lowPenetrationPercent: Number(lowPenetrationPercent.toFixed(2)),
    signalType: buySignal ? "하단선 상향돌파" : "상단선 하향돌파",
    buySignal,
    sellSignal,
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
  return evaluateMultiEnvelope(symbol, candles);
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
  start.setUTCDate(start.getUTCDate() - 300);
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
      basisType: BASIS_TYPE,
      basisName: "RMA",
      length: LENGTH,
      timeMode: TIME_MODE,
      timeframe: "day",
      dailyWidthFactor: DAILY_WIDTH_FACTOR,
      upperPercent: UPPER_PERCENT,
      lowerPercent: LOWER_PERCENT,
      effectiveUpperPercent: UPPER_PERCENT * DAILY_WIDTH_FACTOR,
      effectiveLowerPercent: LOWER_PERCENT * DAILY_WIDTH_FACTOR,
      signalMode: SIGNAL_MODE,
      signalName: "buy",
    },
    evaluated,
    results: results.sort((left, right) => left.recoveryPercent - right.recoveryPercent),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
