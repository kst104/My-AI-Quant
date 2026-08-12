const MAX_SYMBOLS = 20;
const MAX_CONCURRENCY = 5;

type NaverWeeklyCandle = {
  localDate?: string;
  closePrice?: number;
};

const dateTime = (date: Date, endOfDay = false) => {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}${month}${day}${endOfDay ? "2359" : "0000"}`;
};

const currentKoreanWeekStart = () => {
  const koreanNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const weekStart = new Date(koreanNow);
  weekStart.setUTCHours(0, 0, 0, 0);
  weekStart.setUTCDate(weekStart.getUTCDate() - weekStart.getUTCDay());
  return dateTime(weekStart).slice(0, 8);
};

async function fetchPreviousFridayClose(symbol: string, start: Date, end: Date, weekStart: string) {
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
  const candles = await response.json() as NaverWeeklyCandle[];
  const reference = candles
    .filter((item) => item.localDate && item.localDate < weekStart && item.closePrice != null)
    .at(-1);
  if (!reference?.closePrice) throw new Error(`${symbol}: no weekly reference`);
  return { symbol, previousFridayClose: reference.closePrice, referenceWeekStart: reference.localDate! };
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
  start.setUTCDate(start.getUTCDate() - 120);
  const weekStart = currentKoreanWeekStart();
  const references: Array<{ symbol: string; previousFridayClose: number; referenceWeekStart: string }> = [];
  const failed: string[] = [];
  let nextSymbol = 0;

  const worker = async () => {
    while (nextSymbol < symbols.length) {
      const symbol = symbols[nextSymbol];
      nextSymbol += 1;
      try {
        references.push(await fetchPreviousFridayClose(symbol, start, end, weekStart));
      } catch {
        failed.push(symbol);
      }
    }
  };

  await Promise.all(Array.from({ length: Math.min(MAX_CONCURRENCY, symbols.length) }, () => worker()));

  if (references.length === 0) {
    return Response.json({ error: "전주 금요일 종가를 불러오지 못했습니다.", failed }, { status: 502 });
  }

  return Response.json({
    source: "NAVER Finance",
    updatedAt: new Date().toISOString(),
    weekStart,
    references,
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
