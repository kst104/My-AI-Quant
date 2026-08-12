const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const ATR_LENGTH = 100;
const BODY_MIN_PERCENT = 70;
const SEARCH_FACTOR = 1.3;
const SLOW_LENGTH = 20;
const FAST_LENGTH = 8;

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

function simpleMovingAverage(values: number[], length: number) {
  const averages = Array<number>(values.length).fill(Number.NaN);
  let sum = 0;
  for (let index = 0; index < values.length; index += 1) {
    sum += values[index];
    if (index >= length) sum -= values[index - length];
    if (index >= length - 1) averages[index] = sum / length;
  }
  return averages;
}

function wilderAtr(candles: Candle[], length: number) {
  const trueRanges = candles.map((candle, index) => {
    if (index === 0) return candle.high - candle.low;
    const previousClose = candles[index - 1].close;
    return Math.max(
      candle.high - candle.low,
      Math.abs(candle.high - previousClose),
      Math.abs(candle.low - previousClose),
    );
  });
  const atr = Array<number>(candles.length).fill(Number.NaN);
  if (candles.length < length) return atr;

  atr[length - 1] = trueRanges.slice(0, length).reduce((sum, value) => sum + value, 0) / length;
  for (let index = length; index < candles.length; index += 1) {
    atr[index] = (atr[index - 1] * (length - 1) + trueRanges[index]) / length;
  }
  return atr;
}

function calculateFastDirection(fastAverages: number[]) {
  let direction = 0;
  for (let index = 1; index < fastAverages.length; index += 1) {
    const current = fastAverages[index];
    const previous = fastAverages[index - 1];
    if (!Number.isFinite(current) || !Number.isFinite(previous)) continue;
    if (current > previous) direction = 1;
    if (current < previous) direction = -1;
  }
  return direction;
}

function evaluateElephantCandle(symbol: string, candles: Candle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
  ));
  if (valid.length < ATR_LENGTH + 1) return null;

  const current = valid.at(-1)!;
  const bodySize = Math.abs(current.close - current.open);
  const barRange = Math.abs(current.high - current.low);
  if (barRange <= 0 || current.close <= current.open) return null;

  const closes = valid.map((item) => item.close);
  const fastAverages = simpleMovingAverage(closes, FAST_LENGTH);
  const slowAverages = simpleMovingAverage(closes, SLOW_LENGTH);
  const atrValues = wilderAtr(valid, ATR_LENGTH);
  const previousAtr100 = atrValues.at(-2)!;
  const fastDirection = calculateFastDirection(fastAverages);
  const bodyPercent = bodySize * 100 / barRange;
  const atrFactor = bodySize / previousAtr100;

  if (
    !Number.isFinite(previousAtr100)
    || previousAtr100 <= 0
    || bodyPercent < BODY_MIN_PERCENT
    || bodySize < previousAtr100 * SEARCH_FACTOR
    || fastDirection <= 0
  ) {
    return null;
  }

  return {
    symbol,
    tradingDate: current.date,
    close: Math.round(current.close),
    bodySize: Math.round(bodySize),
    bodyPercent: Number(bodyPercent.toFixed(2)),
    previousAtr100: Number(previousAtr100.toFixed(2)),
    atrFactor: Number(atrFactor.toFixed(2)),
    fastSma8: Number(fastAverages.at(-1)!.toFixed(2)),
    slowSma20: Number(slowAverages.at(-1)!.toFixed(2)),
    fastDirection: "up",
    searchMode: 1,
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
  return evaluateElephantCandle(symbol, candles);
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
  start.setUTCDate(start.getUTCDate() - 520);
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
      atrLength: ATR_LENGTH,
      bodyMinPercent: BODY_MIN_PERCENT,
      searchFactor: SEARCH_FACTOR,
      slowLength: SLOW_LENGTH,
      fastLength: FAST_LENGTH,
      searchMode: 1,
      direction: "bull",
    },
    evaluated,
    results: results.sort((left, right) => right.atrFactor - left.atrFactor),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
