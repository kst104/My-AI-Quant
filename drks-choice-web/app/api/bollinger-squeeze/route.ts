const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const BOLLINGER_PERIOD = 20;
const BOLLINGER_STD = 2;
const BANDWIDTH_LOOKBACK = 40;
const SQUEEZE_RATIO_MAX = 70;
const EMA_PERIOD = 20;
const TOUCH_TOLERANCE = 0.003;

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

function rollingBollingerBandwidth(values: number[], period: number, standardDeviations: number) {
  const bandwidths = Array<number>(values.length).fill(Number.NaN);
  for (let index = period - 1; index < values.length; index += 1) {
    const window = values.slice(index - period + 1, index + 1);
    const mean = window.reduce((sum, value) => sum + value, 0) / period;
    const variance = window.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / (period - 1);
    const standardDeviation = Math.sqrt(variance);
    bandwidths[index] = standardDeviation * standardDeviations * 2;
  }
  return bandwidths;
}

function rollingAverage(values: number[], period: number) {
  const averages = Array<number>(values.length).fill(Number.NaN);
  for (let index = period - 1; index < values.length; index += 1) {
    const window = values.slice(index - period + 1, index + 1);
    if (!window.every(Number.isFinite)) continue;
    averages[index] = window.reduce((sum, value) => sum + value, 0) / period;
  }
  return averages;
}

function evaluateBollingerSqueeze(symbol: string, candles: Candle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
  ));
  if (valid.length < BOLLINGER_PERIOD + BANDWIDTH_LOOKBACK) return null;

  const closes = valid.map((item) => item.close);
  const ema20 = exponentialMovingAverage(closes, EMA_PERIOD);
  const bandwidths = rollingBollingerBandwidth(closes, BOLLINGER_PERIOD, BOLLINGER_STD);
  const bandwidthAverages = rollingAverage(bandwidths, BANDWIDTH_LOOKBACK);
  const today = valid.at(-1)!;
  const yesterday = valid.at(-2)!;
  const todayEma20 = ema20.at(-1)!;
  const yesterdayEma20 = ema20.at(-2)!;
  const bandwidth = bandwidths.at(-1)!;
  const bandwidthAverage40 = bandwidthAverages.at(-1)!;

  if (
    ![todayEma20, yesterdayEma20, bandwidth, bandwidthAverage40].every(Number.isFinite)
    || bandwidthAverage40 <= 0
    || today.close <= today.open
  ) {
    return null;
  }

  const squeezeRatio = bandwidth / bandwidthAverage40 * 100;
  if (squeezeRatio > SQUEEZE_RATIO_MAX) return null;

  const emaBreakout = yesterday.close < yesterdayEma20 && today.close > todayEma20;
  const tolerance = todayEma20 * TOUCH_TOLERANCE;
  const emaTouch = (
    today.low <= todayEma20 + tolerance
    && today.low >= todayEma20 - tolerance
    && today.close >= todayEma20
  );
  if (!emaBreakout && !emaTouch) return null;

  const signalTypes = [
    ...(emaBreakout ? ["EMA20 돌파"] : []),
    ...(emaTouch ? ["EMA20 터치"] : []),
  ];

  return {
    symbol,
    tradingDate: today.date,
    close: Math.round(today.close),
    ema20: Number(todayEma20.toFixed(2)),
    bandwidth: Number(bandwidth.toFixed(2)),
    bandwidthAverage40: Number(bandwidthAverage40.toFixed(2)),
    squeezeRatio: Number(squeezeRatio.toFixed(1)),
    signalType: signalTypes.join(" + "),
    emaBreakout,
    emaTouch,
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
  return evaluateBollingerSqueeze(symbol, candles);
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
      bollingerPeriod: BOLLINGER_PERIOD,
      standardDeviations: BOLLINGER_STD,
      bandwidthLookback: BANDWIDTH_LOOKBACK,
      squeezeRatioMax: SQUEEZE_RATIO_MAX,
      emaPeriod: EMA_PERIOD,
      touchTolerancePercent: TOUCH_TOLERANCE * 100,
      bullishOnly: true,
    },
    evaluated,
    results: results.sort((left, right) => left.squeezeRatio - right.squeezeRatio),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
