const MAX_SYMBOLS = 20;
const MAX_CONCURRENCY = 5;
const MAX_GRAHAM_DODD_INDEX = 22.55;
const PER_YEAR = "2027/12";
const PBR_YEAR = "2026/12";

type FinancialHeader = {
  YYMM?: string;
  CD?: string;
  EP_CHK?: string | null;
};

type FinancialRow = {
  NAME?: string;
  [key: string]: string | number | null | undefined;
};

type PerformanceTrend = {
  header?: FinancialHeader[];
  data?: FinancialRow[];
};

function extractJsonObject(source: string, marker: string) {
  const markerIndex = source.indexOf(marker);
  if (markerIndex < 0) return null;
  const start = source.indexOf("{", markerIndex + marker.length);
  if (start < 0) return null;

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < source.length; index += 1) {
    const character = source[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      continue;
    }
    if (character === '"') {
      inString = true;
      continue;
    }
    if (character === "{") depth += 1;
    if (character === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  return null;
}

const toPositiveNumber = (value: unknown) => {
  const parsed = typeof value === "number" ? value : Number(String(value ?? "").replaceAll(",", ""));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

async function evaluateSymbol(symbol: string) {
  const response = await fetch(`https://wcomp.fnguide.com/CompanyInfo/Consensus?cmp_cd=${symbol}`, {
    cache: "no-store",
    headers: {
      Accept: "text/html,application/xhtml+xml",
      "Accept-Language": "ko-KR,ko;q=0.9",
      "User-Agent": "Mozilla/5.0 (compatible; DrKsChoice/1.0)",
    },
  });
  if (!response.ok) throw new Error(`${symbol}: ${response.status}`);

  const html = await response.text();
  const serialized = extractJsonObject(html, "perforTrend:");
  if (!serialized) return { symbol, status: "missing" as const };

  const trend = JSON.parse(serialized) as PerformanceTrend;
  const perColumn = trend.header?.find((item) => item.YYMM === PER_YEAR && item.EP_CHK === "E")?.CD;
  const pbrColumn = trend.header?.find((item) => item.YYMM === PBR_YEAR && item.EP_CHK === "E")?.CD;
  const perRow = trend.data?.find((item) => item.NAME?.trim() === "PER");
  const pbrRow = trend.data?.find((item) => item.NAME?.trim() === "PBR");
  const expectedPer2027 = perColumn ? toPositiveNumber(perRow?.[perColumn]) : null;
  const expectedPbr2026 = pbrColumn ? toPositiveNumber(pbrRow?.[pbrColumn]) : null;

  if (expectedPer2027 == null || expectedPbr2026 == null) {
    return { symbol, status: "missing" as const };
  }

  const grahamDoddIndex = expectedPer2027 * expectedPbr2026;
  return {
    symbol,
    status: "evaluated" as const,
    expectedPer2027: Number(expectedPer2027.toFixed(2)),
    expectedPbr2026: Number(expectedPbr2026.toFixed(2)),
    grahamDoddIndex: Number(grahamDoddIndex.toFixed(2)),
    matched: grahamDoddIndex <= MAX_GRAHAM_DODD_INDEX,
  };
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const symbols = [...new Set(
    (url.searchParams.get("symbols") ?? "")
      .split(",")
      .map((symbol) => symbol.trim())
      .filter((symbol) => /^\d{6}$/.test(symbol)),
  )].slice(0, MAX_SYMBOLS);

  if (symbols.length === 0) {
    return Response.json({ error: "올바른 종목 코드를 입력해 주세요." }, { status: 400 });
  }

  const evaluatedResults: Array<Awaited<ReturnType<typeof evaluateSymbol>> & { status: "evaluated" }> = [];
  const missing: string[] = [];
  const failed: string[] = [];
  let nextSymbol = 0;

  const worker = async () => {
    while (nextSymbol < symbols.length) {
      const symbol = symbols[nextSymbol];
      nextSymbol += 1;
      try {
        const result = await evaluateSymbol(symbol);
        if (result.status === "evaluated") evaluatedResults.push(result);
        else missing.push(symbol);
      } catch {
        failed.push(symbol);
      }
    }
  };

  await Promise.all(Array.from({ length: Math.min(MAX_CONCURRENCY, symbols.length) }, () => worker()));

  return Response.json({
    source: "FnGuide Company Guide",
    updatedAt: new Date().toISOString(),
    rule: {
      perYear: PER_YEAR,
      pbrYear: PBR_YEAR,
      maximumIndex: MAX_GRAHAM_DODD_INDEX,
      positiveValuesOnly: true,
    },
    evaluated: evaluatedResults.length,
    valuations: evaluatedResults
      .sort((left, right) => left.grahamDoddIndex - right.grahamDoddIndex),
    results: evaluatedResults
      .filter((item) => item.matched)
      .sort((left, right) => left.grahamDoddIndex - right.grahamDoddIndex),
    missing,
    failed,
  }, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}
