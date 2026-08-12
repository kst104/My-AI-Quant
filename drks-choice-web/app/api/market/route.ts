const ALLOWED_SYMBOLS = new Set([
  "005930", "000660", "035420", "005380", "012450", "373220",
  "207940", "000270", "055550", "105560", "035720", "068270",
]);

type NaverQuote = {
  itemCode?: string;
  stockName?: string;
  closePriceRaw?: string;
  fluctuationsRatioRaw?: string;
  openPriceRaw?: string;
  highPriceRaw?: string;
  lowPriceRaw?: string;
  accumulatedTradingVolumeRaw?: string;
  marketStatus?: string;
  localTradedAt?: string;
  stockExchangeType?: { name?: string };
};

const toNumber = (value?: string) => {
  if (!value) return null;
  const parsed = Number(value.replaceAll(",", ""));
  return Number.isFinite(parsed) ? parsed : null;
};

export async function GET(request: Request) {
  const url = new URL(request.url);
  const requested = (url.searchParams.get("symbols") ?? "")
    .split(",")
    .map((symbol) => symbol.trim())
    .filter((symbol) => /^\d{6}$/.test(symbol) && ALLOWED_SYMBOLS.has(symbol));
  const symbols = [...new Set(requested)].slice(0, 12);

  if (symbols.length === 0) {
    return Response.json({ error: "지원하는 종목 코드를 하나 이상 입력해 주세요." }, { status: 400 });
  }

  const settled = await Promise.allSettled(
    symbols.map(async (symbol) => {
      const response = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/stock/${symbol}`, {
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "User-Agent": "Mozilla/5.0 (compatible; DrKsChoice/1.0)",
        },
      });
      if (!response.ok) throw new Error(`${symbol}: ${response.status}`);
      const payload = await response.json() as { datas?: NaverQuote[]; time?: string };
      const quote = payload.datas?.[0];
      if (!quote) throw new Error(`${symbol}: empty`);
      return {
        symbol: quote.itemCode ?? symbol,
        name: quote.stockName ?? symbol,
        market: quote.stockExchangeType?.name ?? "KRX",
        price: toNumber(quote.closePriceRaw),
        change: toNumber(quote.fluctuationsRatioRaw),
        open: toNumber(quote.openPriceRaw),
        high: toNumber(quote.highPriceRaw),
        low: toNumber(quote.lowPriceRaw),
        volume: toNumber(quote.accumulatedTradingVolumeRaw),
        marketStatus: quote.marketStatus ?? "UNKNOWN",
        tradedAt: quote.localTradedAt ?? null,
      };
    }),
  );

  const quotes = settled.flatMap((result) => result.status === "fulfilled" ? [result.value] : []);
  const failed = settled.flatMap((result, index) => result.status === "rejected" ? [symbols[index]] : []);

  if (quotes.length === 0) {
    return Response.json({ error: "실제 시세를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.", failed }, { status: 502 });
  }

  return Response.json({
    source: "NAVER Finance",
    updatedAt: new Date().toISOString(),
    quotes,
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
