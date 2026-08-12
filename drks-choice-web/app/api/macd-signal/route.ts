const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const FAST_PERIOD = 12;
const SLOW_PERIOD = 26;
const SIGNAL_PERIOD = 9;

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
  if (values.length === 0) return averages;
  const alpha = 2 / (period + 1);
  averages[0] = values[0];
  for (let index = 1; index < values.length; index += 1) {
    averages[index] = values[index] * alpha + averages[index - 1] * (1 - alpha);
  }
  return averages;
}

function evaluateMacdSignal(symbol: string, candles: Candle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
  ));
  if (valid.length < SLOW_PERIOD + SIGNAL_PERIOD) return null;

  const closes = valid.map((item) => item.close);
  const fastEma = exponentialMovingAverage(closes, FAST_PERIOD);
  const slowEma = exponentialMovingAverage(closes, SLOW_PERIOD);
  const macd = fastEma.map((value, index) => value - slowEma[index]);
  const signal9 = exponentialMovingAverage(macd, SIGNAL_PERIOD);

  const today = valid.at(-1)!;
  const currentMacd = macd.at(-1)!;
  const previousMacd = macd.at(-2)!;
  const currentSignal = signal9.at(-1)!;
  const previousSignal = signal9.at(-2)!;

  if (![currentMacd, previousMacd, currentSignal, previousSignal].every(Number.isFinite)) return null;

  const signalBreakout = (
    currentMacd <= 0
    && currentMacd > currentSignal
    && previousMacd <= previousSignal
  );
  if (!signalBreakout) return null;

  const histogram = currentMacd - currentSignal;
  const signalGapPercent = (histogram / today.close) * 100;

  return {
    symbol,
    tradingDate: today.date,
    close: Math.round(today.close),
    macd: Number(currentMacd.toFixed(2)),
    signal9: Number(currentSignal.toFixed(2)),
    histogram: Number(histogram.toFixed(2)),
    signalGapPercent: Number(signalGapPercent.toFixed(4)),
    previousMacd: Number(previousMacd.toFixed(2)),
    previousSignal9: Number(previousSignal.toFixed(2)),
    signalType: "0선 이하 MACD 시그널 상향돌파",
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
  return evaluateMacdSignal(symbol, candles);
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
      fastEma: FAST_PERIOD,
      slowEma: SLOW_PERIOD,
      signalEma: SIGNAL_PERIOD,
      maximumMacd: 0,
      breakout: "MACD CrossUp Signal",
    },
    evaluated,
    results: results.sort((left, right) => left.signalGapPercent - right.signalGapPercent),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
