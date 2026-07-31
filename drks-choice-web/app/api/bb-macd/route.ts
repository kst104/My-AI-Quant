const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const FAST_PERIOD = 8;
const SLOW_PERIOD = 26;
const SIGNAL_PERIOD = 9;
const STANDARD_DEVIATION_MULTIPLIER = 0.8;

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

function rollingStandardDeviation(values: number[], period: number) {
  const deviations = Array<number>(values.length).fill(Number.NaN);
  for (let index = period - 1; index < values.length; index += 1) {
    const window = values.slice(index - period + 1, index + 1);
    const average = window.reduce((sum, value) => sum + value, 0) / period;
    const variance = window.reduce((sum, value) => sum + ((value - average) ** 2), 0) / period;
    deviations[index] = Math.sqrt(variance);
  }
  return deviations;
}

function evaluateBbMacd(symbol: string, candles: Candle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
  ));
  if (valid.length < SLOW_PERIOD + SIGNAL_PERIOD) return null;

  const closes = valid.map((item) => item.close);
  const fastEma = exponentialMovingAverage(closes, FAST_PERIOD);
  const slowEma = exponentialMovingAverage(closes, SLOW_PERIOD);
  const bbMacd = fastEma.map((value, index) => value - slowEma[index]);
  const average9 = exponentialMovingAverage(bbMacd, SIGNAL_PERIOD);
  const standardDeviation9 = rollingStandardDeviation(bbMacd, SIGNAL_PERIOD);
  const upperBand = average9.map((value, index) => value + STANDARD_DEVIATION_MULTIPLIER * standardDeviation9[index]);
  const lowerBand = average9.map((value, index) => value - STANDARD_DEVIATION_MULTIPLIER * standardDeviation9[index]);

  const today = valid.at(-1)!;
  const currentMacd = bbMacd.at(-1)!;
  const previousMacd = bbMacd.at(-2)!;
  const currentAverage = average9.at(-1)!;
  const currentDeviation = standardDeviation9.at(-1)!;
  const currentUpperBand = upperBand.at(-1)!;
  const previousUpperBand = upperBand.at(-2)!;
  const currentLowerBand = lowerBand.at(-1)!;

  if (![currentMacd, previousMacd, currentAverage, currentDeviation, currentUpperBand, previousUpperBand, currentLowerBand].every(Number.isFinite)) {
    return null;
  }

  const upperBreakout = (
    currentMacd > currentUpperBand
    && previousMacd <= previousUpperBand
    && (currentMacd < 0 || previousMacd < 0)
  );
  if (!upperBreakout) return null;

  const zScore = currentDeviation > 0 ? (currentMacd - currentAverage) / currentDeviation : 0;
  const bandGap = currentMacd - currentUpperBand;

  return {
    symbol,
    tradingDate: today.date,
    close: Math.round(today.close),
    bbMacd: Number(currentMacd.toFixed(2)),
    average9: Number(currentAverage.toFixed(2)),
    standardDeviation9: Number(currentDeviation.toFixed(2)),
    upperBand: Number(currentUpperBand.toFixed(2)),
    lowerBand: Number(currentLowerBand.toFixed(2)),
    bandGap: Number(bandGap.toFixed(2)),
    zScore: Number(zScore.toFixed(2)),
    signalType: "MACD 상단밴드 돌파",
    color: "Green",
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
  return evaluateBbMacd(symbol, candles);
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
      standardDeviationPeriod: SIGNAL_PERIOD,
      standardDeviationMultiplier: STANDARD_DEVIATION_MULTIPLIER,
      breakout: "upper",
      negativeZoneRequired: true,
    },
    evaluated,
    results: results.sort((left, right) => left.zScore - right.zScore),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
