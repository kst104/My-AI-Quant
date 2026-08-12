type Interval = "day" | "week";

type NaverCandle = {
  localDate?: string;
  openPrice?: number;
  highPrice?: number;
  lowPrice?: number;
  closePrice?: number;
  accumulatedTradingVolume?: number;
};

const dateTime = (date: Date, endOfDay = false) => {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}${month}${day}${endOfDay ? "2359" : "0000"}`;
};

export async function GET(request: Request) {
  const url = new URL(request.url);
  const symbol = (url.searchParams.get("symbol") ?? "").trim().toUpperCase();
  const requestedInterval = url.searchParams.get("interval");
  const interval: Interval = requestedInterval === "week" ? "week" : "day";

  if (!/^[0-9A-Z]{6}$/.test(symbol)) {
    return Response.json({ error: "올바른 종목 코드를 입력해 주세요." }, { status: 400 });
  }

  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (interval === "day" ? 180 : 900));

  try {
    const response = await fetch(
      `https://api.stock.naver.com/chart/domestic/item/${symbol}/${interval}?startDateTime=${dateTime(start)}&endDateTime=${dateTime(end, true)}`,
      {
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "User-Agent": "Mozilla/5.0 (compatible; DrKsChoice/1.0)",
        },
      },
    );
    if (!response.ok) throw new Error(`${response.status}`);
    const payload = await response.json() as NaverCandle[];
    const candles = payload
      .filter((item) => (
        item.localDate
        && item.openPrice != null
        && item.highPrice != null
        && item.lowPrice != null
        && item.closePrice != null
      ))
      .slice(-30)
      .map((item) => ({
        date: item.localDate!,
        open: item.openPrice!,
        high: item.highPrice!,
        low: item.lowPrice!,
        close: item.closePrice!,
        volume: item.accumulatedTradingVolume ?? 0,
      }));

    if (candles.length === 0) {
      return Response.json({ error: "해당 종목의 차트 데이터가 없습니다." }, { status: 404 });
    }

    return Response.json({
      source: "NAVER Finance",
      symbol,
      interval,
      count: candles.length,
      updatedAt: new Date().toISOString(),
      candles,
    }, {
      headers: { "Cache-Control": "no-store, max-age=0" },
    });
  } catch {
    return Response.json(
      { error: "차트 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}
