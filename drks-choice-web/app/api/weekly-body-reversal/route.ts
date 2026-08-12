const MAX_SYMBOLS = 10;
const MAX_CONCURRENCY = 4;
const HIGH_LOOKBACK_WEEKS = 52;
const MIN_DRAWDOWN_PERCENT = 20;

type NaverWeeklyCandle = {
  localDate?: string;
  openPrice?: number;
  highPrice?: number;
  lowPrice?: number;
  closePrice?: number;
  accumulatedTradingVolume?: number;
};

type WeeklyCandle = {
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

function evaluateWeeklyBodyReversal(symbol: string, candles: WeeklyCandle[]) {
  const valid = candles.filter((item) => (
    item.close > 0
    && [item.open, item.high, item.low, item.close].every(Number.isFinite)
  ));
  if (valid.length < HIGH_LOOKBACK_WEEKS) return null;

  const current = valid.at(-1)!;
  const previousThree = valid.slice(-4, -1);
  if (previousThree.length !== 3 || current.close <= current.open) return null;
  if (previousThree.some((item) => item.close >= item.open)) return null;

  const previousBodyLengths = previousThree.map((item) => Math.abs(item.open - item.close));
  if (!(previousBodyLengths[0] < previousBodyLengths[1] && previousBodyLengths[1] < previousBodyLengths[2])) {
    return null;
  }

  const high52 = Math.max(...valid.slice(-HIGH_LOOKBACK_WEEKS).map((item) => item.high));
  if (!Number.isFinite(high52) || high52 <= 0) return null;
  const drawdownFromHigh = ((current.close / high52) - 1) * 100;
  if (drawdownFromHigh > -MIN_DRAWDOWN_PERCENT) return null;

  return {
    symbol,
    currentDate: current.date,
    currentClose: Math.round(current.close),
    currentBodyLength: Math.round(Math.abs(current.close - current.open)),
    previousDates: previousThree.map((item) => item.date),
    previousBodyLengths: previousBodyLengths.map(Math.round),
    high52: Math.round(high52),
    drawdownFromHigh: Number(drawdownFromHigh.toFixed(2)),
  };
}

async function scanSymbol(symbol: string, start: Date, end: Date) {
  const response = await fetch(
    `https://api.stock.naver.com/chart/domestic/item/${symbol}/week?startDateTime=${dateTime(start)}&endDateTime=${dateTime(end, true)}`,
    {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; DrKsChoice/1.0)",
      },
    },
  );
  if (!response.ok) throw new Error(`${symbol}: ${response.status}`);
  const payload = await response.json() as NaverWeeklyCandle[];
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
  return evaluateWeeklyBodyReversal(symbol, candles);
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
  start.setUTCDate(start.getUTCDate() - 900);
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
      highLookbackWeeks: HIGH_LOOKBACK_WEEKS,
      minDrawdownPercent: MIN_DRAWDOWN_PERCENT,
      previousBearishWeeks: 3,
      bodyExpansion: "strictly increasing",
      currentWeek: "bullish",
    },
    evaluated,
    results: results.sort((left, right) => left.drawdownFromHigh - right.drawdownFromHigh),
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
