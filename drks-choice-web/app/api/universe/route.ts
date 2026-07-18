const MARKETS = ["KOSPI", "KOSDAQ"] as const;
const PAGE_SIZE = 100;
const MIN_MARKET_CAP = 300_000_000_000;

type Market = (typeof MARKETS)[number];

type NaverUniverseStock = {
  stockEndType?: string;
  itemCode?: string;
  stockName?: string;
  closePriceRaw?: string;
  fluctuationsRatio?: string;
  accumulatedTradingVolumeRaw?: string;
  accumulatedTradingValueRaw?: string;
  marketValueRaw?: string;
  marketStatus?: string;
  localTradedAt?: string;
  stockExchangeType?: { name?: string };
};

type NaverUniversePage = {
  totalCount?: number;
  stocks?: NaverUniverseStock[];
};

const toNumber = (value?: string) => {
  if (!value) return null;
  const parsed = Number(value.replaceAll(",", ""));
  return Number.isFinite(parsed) ? parsed : null;
};

async function fetchPage(market: Market, page: number) {
  const response = await fetch(
    `https://m.stock.naver.com/api/stocks/marketValue/${market}?page=${page}&pageSize=${PAGE_SIZE}`,
    {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; DrKsChoice/1.0)",
      },
    },
  );
  if (!response.ok) throw new Error(`${market} ${page}: ${response.status}`);
  return response.json() as Promise<NaverUniversePage>;
}

async function fetchMarket(market: Market) {
  const firstPage = await fetchPage(market, 1);
  const pageCount = Math.max(1, Math.ceil((firstPage.totalCount ?? 0) / PAGE_SIZE));
  const pages = [firstPage];

  for (let page = 2; page <= pageCount; page += 1) {
    const previousStocks = pages.at(-1)?.stocks ?? [];
    const previousLowestMarketCap = toNumber(previousStocks.at(-1)?.marketValueRaw);
    if (previousLowestMarketCap != null && previousLowestMarketCap < MIN_MARKET_CAP) break;
    pages.push(await fetchPage(market, page));
  }

  return pages
    .flatMap((page) => page.stocks ?? [])
    .filter((stock) => (
      stock.stockEndType === "stock"
      && /^[0-9A-Z]{6}$/.test(stock.itemCode ?? "")
      && (toNumber(stock.marketValueRaw) ?? 0) >= MIN_MARKET_CAP
    ))
    .map((stock) => ({
      symbol: stock.itemCode!,
      name: stock.stockName ?? stock.itemCode!,
      market: stock.stockExchangeType?.name ?? market,
      price: toNumber(stock.closePriceRaw),
      change: toNumber(stock.fluctuationsRatio),
      volume: toNumber(stock.accumulatedTradingVolumeRaw),
      tradingValue: toNumber(stock.accumulatedTradingValueRaw),
      marketCap: toNumber(stock.marketValueRaw),
      marketStatus: stock.marketStatus ?? "UNKNOWN",
      tradedAt: stock.localTradedAt ?? null,
    }));
}

export async function GET() {
  try {
    const marketStocks = await Promise.all(MARKETS.map((market) => fetchMarket(market)));
    const deduplicated = new Map(
      marketStocks.flat().map((stock) => [stock.symbol, stock]),
    );
    const stocks = [...deduplicated.values()];

    return Response.json({
      source: "NAVER Finance",
      updatedAt: new Date().toISOString(),
      totalCount: stocks.length,
      counts: Object.fromEntries(MARKETS.map((market, index) => [market, marketStocks[index].length])),
      filter: { minMarketCap: MIN_MARKET_CAP, label: "3,000억원 이상" },
      stocks,
    }, {
      headers: {
        "Cache-Control": "no-store, max-age=0",
      },
    });
  } catch {
    return Response.json(
      { error: "한국 시장 전체 종목을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }
}
