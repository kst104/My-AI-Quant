"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type View = "dashboard" | "screener" | "workflow";
type ChartInterval = "day" | "week";

type Candle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type Stock = {
  symbol: string;
  name: string;
  market: string;
  price: number;
  change: number;
  target: number;
  score: number;
  per: string;
  pbr: string;
  roe: string;
  chart: number[];
  thesis: [string, string, string];
};

type LiveQuote = {
  symbol: string;
  name: string;
  market: string;
  price: number | null;
  change: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  marketStatus: string;
  tradedAt: string | null;
};

type UniverseStock = Pick<LiveQuote, "symbol" | "name" | "market" | "price" | "change" | "volume" | "marketStatus" | "tradedAt"> & {
  marketCap: number | null;
  tradingValue: number | null;
  previousFridayClose: number | null;
  weeklyChange: number | null;
  consensusUpgrade: boolean;
  consensusReportCount: number;
  candleResistanceBreakout: boolean;
  candleResistance: number | null;
  candleResistanceDistance: number | null;
  candleResistanceDate: string | null;
  candleResistanceAdx11: number | null;
  weeklyBodyReversal: boolean;
  weeklyBodyDrawdown: number | null;
  weeklyBodyHigh: number | null;
  weeklyBodyLengths: number[] | null;
  weeklyBodyCurrentDate: string | null;
  elephantCandle: boolean;
  elephantBodyPercent: number | null;
  elephantAtrFactor: number | null;
  elephantPreviousAtr100: number | null;
  elephantFastSma8: number | null;
  elephantSlowSma20: number | null;
  elephantTradingDate: string | null;
};

type ConsensusSnapshot = {
  generatedAt: string;
  lookbackTradingDays: string[];
  reportDates: string[];
  stocks: Array<{ symbol: string; name: string; reportCount: number }>;
};

type PipelineNode = {
  id: string;
  name: string;
  category: string;
  detail: string;
  rule: string;
  isSource?: boolean;
};

type UniverseStats = {
  medianTradingValue: number;
  top20TradingValue: number;
};

const stocks: Stock[] = [
  {
    symbol: "005930",
    name: "삼성전자",
    market: "KOSPI",
    price: 84600,
    change: 1.44,
    target: 96000,
    score: 82,
    per: "18.4x",
    pbr: "1.72x",
    roe: "12.8%",
    chart: [70, 72, 69, 75, 73, 78, 76, 81, 79, 85, 83, 88, 86, 92],
    thesis: [
      "HBM 믹스 개선과 메모리 가격 회복으로 하반기 이익 추정치가 상향 중입니다.",
      "12개월 선행 PBR은 업사이클 대비 부담이 제한적인 구간입니다.",
      "파운드리 수율 회복 지연과 환율 변동은 계속 확인해야 할 변수입니다.",
    ],
  },
  {
    symbol: "000660",
    name: "SK하이닉스",
    market: "KOSPI",
    price: 241500,
    change: 2.38,
    target: 278000,
    score: 88,
    per: "11.9x",
    pbr: "2.14x",
    roe: "19.6%",
    chart: [62, 67, 65, 70, 72, 69, 75, 80, 78, 84, 87, 85, 91, 95],
    thesis: [
      "AI 서버용 HBM 수요가 제품 믹스와 수익성 개선을 동시에 견인하고 있습니다.",
      "이익 성장률을 감안하면 동종 업계 대비 밸류에이션 확장 여지가 남아 있습니다.",
      "고객사 투자 속도와 메모리 공급 증가는 실적 변동성을 높일 수 있습니다.",
    ],
  },
  {
    symbol: "035420",
    name: "NAVER",
    market: "KOSPI",
    price: 182300,
    change: -0.65,
    target: 215000,
    score: 74,
    per: "21.2x",
    pbr: "1.31x",
    roe: "8.9%",
    chart: [84, 82, 85, 81, 79, 83, 80, 86, 84, 88, 85, 87, 90, 89],
    thesis: [
      "커머스와 핀테크 수익화가 광고 성장 둔화를 보완하고 있습니다.",
      "AI 투자비 증가를 반영한 실적 가시성 회복 여부가 재평가의 핵심입니다.",
      "콘텐츠 자회사 실적과 플랫폼 규제 논의는 단기 변동 요인입니다.",
    ],
  },
  {
    symbol: "005380",
    name: "현대차",
    market: "KOSPI",
    price: 287000,
    change: 0.92,
    target: 322000,
    score: 79,
    per: "6.8x",
    pbr: "0.74x",
    roe: "13.7%",
    chart: [74, 76, 73, 78, 81, 79, 83, 82, 86, 84, 89, 88, 91, 93],
    thesis: [
      "고부가 차종 믹스와 북미 판매가 견조한 현금흐름을 뒷받침합니다.",
      "주주환원 확대에도 역사적 밴드 하단에 가까운 멀티플을 유지하고 있습니다.",
      "관세 정책과 원화 강세 전환은 수익성 민감도를 높이는 변수입니다.",
    ],
  },
];

const screenerRows = [
  { symbol: "000660", name: "SK하이닉스", style: "성장", score: 88, vcp: "통과", flow: "+642억", rank: "A" },
  { symbol: "012450", name: "한화에어로스페이스", style: "모멘텀", score: 86, vcp: "통과", flow: "+318억", rank: "A" },
  { symbol: "005930", name: "삼성전자", style: "수급", score: 82, vcp: "관찰", flow: "+1,204억", rank: "A-" },
  { symbol: "005380", name: "현대차", style: "가치", score: 79, vcp: "통과", flow: "+176억", rank: "B+" },
  { symbol: "035420", name: "NAVER", style: "성장", score: 74, vcp: "대기", flow: "-84억", rank: "B" },
  { symbol: "373220", name: "LG에너지솔루션", style: "모멘텀", score: 71, vcp: "관찰", flow: "+92억", rank: "B" },
];

const pipelineLibrary: PipelineNode[] = [
  { id: "universe", name: "종목 가져오기", category: "KRX", detail: "KOSPI·KOSDAQ에서 ETF·ETN을 제외하고, 최종 시가총액 3,000억원 이상인 상장 종목을 모두 가져옵니다.", rule: "최종 시가총액 ≥ 3,000억원", isSource: true },
  { id: "vcp", name: "VCP 패턴", category: "TECH", detail: "전체 유니버스에서 당일 변동이 제한적이고 거래가 충분한 가격 수축 후보를 계산합니다.", rule: "|등락률| ≤ 2% · 거래대금 중간값 이상" },
  { id: "flow", name: "큰손 수급", category: "FLOW", detail: "전체 유니버스에서 상승 흐름과 대규모 거래대금이 함께 나타난 종목을 계산합니다.", rule: "등락률 > 0% · 거래대금 상위 20%" },
  { id: "oneil", name: "CAN SLIM", category: "GURU", detail: "전체 유니버스에서 시가총액 규모와 강한 당일 가격 모멘텀이 겹친 종목을 계산합니다.", rule: "시총 ≥ 5,000억원 · 등락률 ≥ 3%" },
  { id: "value", name: "가치+모멘텀", category: "VALUE", detail: "전체 유니버스에서 중소형 시가총액 구간에 있으면서 상승 중인 종목을 계산합니다.", rule: "시총 3,000억원~2조원 · 등락률 > 0%" },
  { id: "c70", name: "조건70 돌파", category: "COND", detail: "전체 유니버스에서 높은 당일 상승률과 충분한 거래대금이 함께 나타난 돌파 후보를 계산합니다.", rule: "등락률 ≥ 5% · 거래대금 중간값 이상" },
  { id: "weekly10", name: "10%이하 주간 상승", category: "WEEK", detail: "시가총액 3,000억원 이상 전체 종목에서 전주 금요일 종가보다 현재 종가가 높고, 주간 상승률이 10% 이하인 종목을 계산합니다.", rule: "0% < 전주 금요일 종가 대비 현재 종가 상승률 ≤ 10%" },
  { id: "consensusUp", name: "컨센서스상향", category: "REPORT", detail: "이 컴퓨터의 증권리포트 폴더에서 최근 5거래일의 목표가상향 파일에 포함된 종목을 추출하고, 시가총액 3,000억원 이상 전체 유니버스와 교차 확인합니다.", rule: "최근 5거래일 · 목표가상향*.* 포함 종목" },
  { id: "candleResistance", name: "캔들볼륨 저항선돌파", category: "BREAK", detail: "최근 90봉 음봉 중 캔들 가격과 거래량의 곱이 가장 큰 봉의 시가를 저항선으로 정하고, 오늘 처음 돌파하면서 ADX(11)가 25를 넘는 종목을 찾습니다.", rule: "금일 종가 > 저항선 ≥ 전일 종가 · ADX(11) > 25" },
  { id: "weeklyBodyReversal", name: "주봉 3주 음봉후 첫 양봉", category: "WEEK", detail: "최근 52주 고점에서 20% 이상 하락한 종목 중 직전 3개 주봉이 모두 음봉이고 몸통 길이가 매주 커진 뒤, 이번 주 처음 양봉으로 전환한 종목을 찾습니다.", rule: "직전 3주 음봉 · 몸통 연속 확대 · 금주 첫 양봉 · 52주 고점 대비 ≤ -20%" },
  { id: "elephantCandle", name: "코끼리캔들", category: "CANDLE", detail: "첨부 검색식의 기본 SearchMode 1을 적용해 몸통이 크고 빠른 이동평균이 상승하는 양봉 코끼리캔들을 찾습니다.", rule: "양봉 · 몸통비율 ≥ 70% · 몸통 ≥ 전일 ATR(100) × 1.3 · SMA(8) 방향 상승" },
  { id: "risk", name: "급락 경고", category: "RISK", detail: "전체 유니버스에서 거래가 충분하면서 당일 낙폭이 큰 위험 관찰 종목을 계산합니다.", rule: "등락률 ≤ -5% · 거래대금 중간값 이상" },
];

const chartIntervals: { id: ChartInterval; label: string }[] = [
  { id: "day", label: "일봉" },
  { id: "week", label: "주봉" },
];
const navItems: { id: View; label: string }[] = [
  { id: "dashboard", label: "종목분석" },
  { id: "screener", label: "스크리너" },
  { id: "workflow", label: "워크플로" },
];

const won = (value: number) => `₩${value.toLocaleString("ko-KR")}`;
const marketCapLabel = (value: number | null) => {
  if (value == null) return "시가총액 확인 필요";
  if (value >= 1_000_000_000_000) return `시총 ${(value / 1_000_000_000_000).toFixed(value >= 10_000_000_000_000 ? 0 : 1)}조`;
  return `시총 ${Math.round(value / 100_000_000).toLocaleString("ko-KR")}억`;
};
const tradingValueLabel = (value: number | null) => {
  if (value == null) return "거래대금 확인 필요";
  return `거래대금 ${Math.round(value / 100_000_000).toLocaleString("ko-KR")}억`;
};

const quantile = (values: number[], ratio: number) => {
  if (values.length === 0) return 0;
  const index = Math.min(values.length - 1, Math.floor((values.length - 1) * ratio));
  return values[index];
};

function buildUniverseStats(items: UniverseStock[]): UniverseStats {
  const tradingValues = items
    .flatMap((item) => item.tradingValue == null ? [] : [item.tradingValue])
    .sort((a, b) => a - b);
  return {
    medianTradingValue: quantile(tradingValues, 0.5),
    top20TradingValue: quantile(tradingValues, 0.8),
  };
}

function matchesNode(nodeId: string, stock: UniverseStock, stats: UniverseStats) {
  const change = stock.change;
  const tradingValue = stock.tradingValue;
  const marketCap = stock.marketCap;
  if (nodeId === "weekly10") return stock.weeklyChange != null && stock.weeklyChange > 0 && stock.weeklyChange <= 10;
  if (nodeId === "consensusUp") return stock.consensusUpgrade;
  if (nodeId === "candleResistance") return stock.candleResistanceBreakout;
  if (nodeId === "weeklyBodyReversal") return stock.weeklyBodyReversal;
  if (nodeId === "elephantCandle") return stock.elephantCandle;
  if (change == null || marketCap == null) return false;

  switch (nodeId) {
    case "vcp": return tradingValue != null && Math.abs(change) <= 2 && tradingValue >= stats.medianTradingValue;
    case "flow": return tradingValue != null && change > 0 && tradingValue >= stats.top20TradingValue;
    case "oneil": return marketCap >= 500_000_000_000 && change >= 3;
    case "value": return marketCap <= 2_000_000_000_000 && change > 0;
    case "c70": return tradingValue != null && change >= 5 && tradingValue >= stats.medianTradingValue;
    case "risk": return tradingValue != null && change <= -5 && tradingValue >= stats.medianTradingValue;
    default: return true;
  }
}

function buildIntersectionResults(items: UniverseStock[], nodes: PipelineNode[], stats: UniverseStats) {
  const matchedBy = nodes.map((node) => node.name);
  const results = items
    .filter((item) => nodes.every((node) => matchesNode(node.id, item, stats)))
    .map((item) => ({ ...item, matchedBy }));
  if (nodes.some((node) => node.id === "elephantCandle")) {
    results.sort((left, right) => (
      (right.elephantAtrFactor ?? Number.NEGATIVE_INFINITY)
      - (left.elephantAtrFactor ?? Number.NEGATIVE_INFINITY)
    ));
  } else if (nodes.some((node) => node.id === "weeklyBodyReversal")) {
    results.sort((left, right) => (
      (left.weeklyBodyDrawdown ?? Number.POSITIVE_INFINITY)
      - (right.weeklyBodyDrawdown ?? Number.POSITIVE_INFINITY)
    ));
  } else if (nodes.some((node) => node.id === "candleResistance")) {
    results.sort((left, right) => (
      (left.candleResistanceDistance ?? Number.POSITIVE_INFINITY)
      - (right.candleResistanceDistance ?? Number.POSITIVE_INFINITY)
    ));
  }
  return results;
}

const candleDateLabel = (value: string) => `${value.slice(4, 6)}.${value.slice(6, 8)}`;

function CandleChart({ candles, name, interval, loading, error }: { candles: Candle[]; name: string; interval: ChartInterval; loading: boolean; error: string }) {
  if (loading) return <div className="chart-state"><i /> 실제 {interval === "day" ? "일봉" : "주봉"} 30개를 불러오는 중입니다.</div>;
  if (error || candles.length === 0) return <div className="chart-state error">{error || "표시할 차트 데이터가 없습니다."}</div>;

  const highest = Math.max(...candles.map((item) => item.high));
  const lowest = Math.min(...candles.map((item) => item.low));
  const range = highest - lowest || 1;
  const maxVolume = Math.max(...candles.map((item) => item.volume), 1);
  const midpoint = Math.round((highest + lowest) / 2);
  const lastClose = candles.at(-1)!.close;
  const lastTop = ((highest - lastClose) / range) * 100;
  const labelIndexes = [0, Math.floor((candles.length - 1) / 2), candles.length - 1];

  return (
    <div className="candle-chart" role="img" aria-label={`${name} 최근 ${candles.length}개 ${interval === "day" ? "일봉" : "주봉"} 차트`}>
      <div className="candle-price-area">
        <div className="candle-grid" />
        {candles.map((item, index) => {
          const x = ((index + 0.5) / candles.length) * 100;
          const wickTop = ((highest - item.high) / range) * 100;
          const wickHeight = Math.max(0.8, ((item.high - item.low) / range) * 100);
          const openTop = ((highest - item.open) / range) * 100;
          const closeTop = ((highest - item.close) / range) * 100;
          const bodyTop = Math.min(openTop, closeTop);
          const bodyHeight = Math.max(1.1, Math.abs(openTop - closeTop));
          const rising = item.close >= item.open;
          return (
            <span className={rising ? "candle rising" : "candle falling"} key={item.date} style={{ left: `${x}%`, width: `${Math.max(1.1, 68 / candles.length)}%` }}>
              <i className="candle-wick" style={{ top: `${wickTop}%`, height: `${wickHeight}%` }} />
              <i className="candle-body" style={{ top: `${bodyTop}%`, height: `${bodyHeight}%` }} />
            </span>
          );
        })}
        <div className="candle-current" style={{ top: `${Math.max(2, Math.min(91, lastTop))}%` }}>{won(lastClose)}</div>
        <div className="candle-y-axis" aria-hidden="true"><span>{won(highest)}</span><span>{won(midpoint)}</span><span>{won(lowest)}</span></div>
      </div>
      <div className="candle-volume-area" aria-hidden="true">
        {candles.map((item, index) => <i key={item.date} className={item.close >= item.open ? "rising" : "falling"} style={{ left: `${((index + 0.5) / candles.length) * 100}%`, width: `${Math.max(1.1, 68 / candles.length)}%`, height: `${Math.max(3, (item.volume / maxVolume) * 100)}%` }} />)}
      </div>
      <div className="candle-axis">{labelIndexes.map((index) => <span key={candles[index].date}>{candleDateLabel(candles[index].date)}</span>)}</div>
    </div>
  );
}

export default function Home() {
  const [view, setView] = useState<View>("dashboard");
  const [selectedSymbol, setSelectedSymbol] = useState(stocks[0].symbol);
  const [chartInterval, setChartInterval] = useState<ChartInterval>("day");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [selectedWorkflowStock, setSelectedWorkflowStock] = useState<UniverseStock | null>(null);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [screenFilter, setScreenFilter] = useState("전체");
  const [selectedNodeId, setSelectedNodeId] = useState("universe");
  const [selectedPipelineIds, setSelectedPipelineIds] = useState<string[]>(["universe"]);
  const [running, setRunning] = useState(false);
  const [runComplete, setRunComplete] = useState(false);
  const [liveQuotes, setLiveQuotes] = useState<Record<string, LiveQuote>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [universeStocks, setUniverseStocks] = useState<UniverseStock[]>([]);
  const [universeCounts, setUniverseCounts] = useState({ KOSPI: 0, KOSDAQ: 0 });
  const [universeUpdatedAt, setUniverseUpdatedAt] = useState<string | null>(null);
  const [universeLoading, setUniverseLoading] = useState(false);
  const [workflowRefreshing, setWorkflowRefreshing] = useState(false);
  const [workflowRefreshedAt, setWorkflowRefreshedAt] = useState<string | null>(null);
  const [weeklyLoading, setWeeklyLoading] = useState(false);
  const [weeklyProgress, setWeeklyProgress] = useState({ completed: 0, total: 0 });
  const [consensusLoading, setConsensusLoading] = useState(false);
  const [consensusDataReady, setConsensusDataReady] = useState(false);
  const [consensusSnapshot, setConsensusSnapshot] = useState<ConsensusSnapshot | null>(null);
  const [candleResistanceLoading, setCandleResistanceLoading] = useState(false);
  const [candleResistanceDataReady, setCandleResistanceDataReady] = useState(false);
  const [candleResistanceProgress, setCandleResistanceProgress] = useState({ completed: 0, total: 0 });
  const [weeklyBodyLoading, setWeeklyBodyLoading] = useState(false);
  const [weeklyBodyDataReady, setWeeklyBodyDataReady] = useState(false);
  const [weeklyBodyProgress, setWeeklyBodyProgress] = useState({ completed: 0, total: 0 });
  const [elephantLoading, setElephantLoading] = useState(false);
  const [elephantDataReady, setElephantDataReady] = useState(false);
  const [elephantProgress, setElephantProgress] = useState({ completed: 0, total: 0 });
  const [intersectionResults, setIntersectionResults] = useState<Array<UniverseStock & { matchedBy: string[] }>>([]);

  const baseStock = stocks.find((item) => item.symbol === selectedSymbol) ?? stocks[0];
  const workflowStock = selectedWorkflowStock?.symbol === selectedSymbol ? selectedWorkflowStock : null;
  const currentLiveQuote = liveQuotes[selectedSymbol];
  const actualSecurity = workflowStock ?? currentLiveQuote;
  const stock: Stock = {
    ...baseStock,
    symbol: selectedSymbol,
    name: actualSecurity?.name ?? baseStock.name,
    market: actualSecurity?.market ?? baseStock.market,
    price: actualSecurity?.price ?? baseStock.price,
    change: actualSecurity?.change ?? baseStock.change,
  };
  const hasActualSecurity = Boolean(actualSecurity);
  const actualTradedAt = actualSecurity?.tradedAt ?? null;
  const chartMetrics = useMemo(() => {
    if (candles.length === 0) return { high: stock.price, low: stock.price, returnRate: 0, averageVolume: 0, averageRange: 0, drawdown: 0, movingAverage: stock.price, score: 50 };
    const first = candles[0].close;
    const last = candles.at(-1)!.close;
    const high = Math.max(...candles.map((item) => item.high));
    const low = Math.min(...candles.map((item) => item.low));
    const averageVolume = candles.reduce((sum, item) => sum + item.volume, 0) / candles.length;
    const averageRange = candles.reduce((sum, item) => sum + ((item.high - item.low) / Math.max(item.close, 1)) * 100, 0) / candles.length;
    const recent = candles.slice(-10);
    const movingAverage = recent.reduce((sum, item) => sum + item.close, 0) / recent.length;
    const returnRate = ((last / first) - 1) * 100;
    const drawdown = ((last / high) - 1) * 100;
    const score = Math.round(Math.max(0, Math.min(100, 50 + returnRate * 1.4 + (last >= movingAverage ? 12 : -12) - averageRange * 1.2)));
    return { high, low, returnRate, averageVolume, averageRange, drawdown, movingAverage, score };
  }, [candles, stock.price]);
  const suggestions = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return stocks;
    return stocks.filter((item) => item.name.toLowerCase().includes(normalized) || item.symbol.includes(normalized));
  }, [query]);
  const filteredRows = screenFilter === "전체" ? screenerRows : screenerRows.filter((row) => row.style === screenFilter);
  const selectedPipeline = selectedPipelineIds.flatMap((id) => {
    const node = pipelineLibrary.find((item) => item.id === id);
    return node ? [node] : [];
  });
  const selectedConditionPipeline = selectedPipeline.filter((node) => !node.isSource);
  const selectedNode = pipelineLibrary.find((node) => node.id === selectedNodeId) ?? pipelineLibrary[0];
  const universeStats = useMemo(() => buildUniverseStats(universeStocks), [universeStocks]);
  const nodeCandidateCounts = useMemo(() => Object.fromEntries(
    pipelineLibrary.map((node) => [
      node.id,
      node.isSource ? universeStocks.length : universeStocks.filter((stock) => matchesNode(node.id, stock, universeStats)).length,
    ]),
  ) as Record<string, number>, [universeStocks, universeStats]);
  const weeklyDataReady = universeStocks.some((item) => item.weeklyChange != null);
  const nodeCandidateLabel = (node: PipelineNode) => {
    if (node.isSource) return universeStocks.length ? `기준 통과 ${universeStocks.length.toLocaleString("ko-KR")}개` : "시총 3,000억 이상";
    if (node.id === "weekly10" && !weeklyDataReady) return weeklyLoading ? `주간 기준 ${weeklyProgress.completed}/${weeklyProgress.total}` : "전주 금요일 종가 새로받기 필요";
    if (node.id === "consensusUp" && !consensusDataReady) return consensusLoading ? "리포트 종목 확인 중" : "리포트 스냅샷 새로받기 필요";
    if (node.id === "candleResistance" && !candleResistanceDataReady) return candleResistanceLoading ? `90봉 계산 ${candleResistanceProgress.completed}/${candleResistanceProgress.total}` : "90봉 데이터 새로받기 필요";
    if (node.id === "weeklyBodyReversal" && !weeklyBodyDataReady) return weeklyBodyLoading ? `주봉 계산 ${weeklyBodyProgress.completed}/${weeklyBodyProgress.total}` : "52주 주봉 데이터 새로받기 필요";
    if (node.id === "elephantCandle" && !elephantDataReady) return elephantLoading ? `일봉 계산 ${elephantProgress.completed}/${elephantProgress.total}` : "ATR(100) 데이터 새로받기 필요";
    return universeStocks.length ? `현재 후보 ${nodeCandidateCounts[node.id].toLocaleString("ko-KR")}개` : "전체 유니버스 계산";
  };

  const fetchQuotes = useCallback(async (symbols: string[]) => {
    const uniqueSymbols = [...new Set(symbols)];
    const response = await fetch(`/api/market?symbols=${uniqueSymbols.join(",")}`, { cache: "no-store" });
    const payload = await response.json() as { quotes?: LiveQuote[]; updatedAt?: string; error?: string };
    if (!response.ok || !payload.quotes?.length) throw new Error(payload.error ?? "실제 시세를 불러오지 못했습니다.");
    setLiveQuotes((current) => ({
      ...current,
      ...Object.fromEntries(payload.quotes!.map((quote) => [quote.symbol, quote])),
    }));
    setLastUpdated(payload.updatedAt ?? new Date().toISOString());
    return payload.quotes;
  }, []);

  const refreshLiveData = useCallback(async () => {
    setRefreshing(true);
    setRefreshError("");
    try {
      await fetchQuotes(stocks.map((item) => item.symbol));
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "시세 업데이트에 실패했습니다.");
    } finally {
      setRefreshing(false);
    }
  }, [fetchQuotes]);

  const fetchUniverse = useCallback(async () => {
    setUniverseLoading(true);
    setRefreshError("");
    try {
      const response = await fetch("/api/universe", { cache: "no-store" });
      const payload = await response.json() as {
        stocks?: UniverseStock[];
        counts?: { KOSPI?: number; KOSDAQ?: number };
        updatedAt?: string;
        error?: string;
      };
      if (!response.ok || !payload.stocks?.length) {
        throw new Error(payload.error ?? "한국 시장 전체 종목을 불러오지 못했습니다.");
      }
      const normalizedStocks = payload.stocks.map((stock) => ({
        ...stock,
        previousFridayClose: stock.previousFridayClose ?? null,
        weeklyChange: stock.weeklyChange ?? null,
        consensusUpgrade: false,
        consensusReportCount: 0,
        candleResistanceBreakout: false,
        candleResistance: null,
        candleResistanceDistance: null,
        candleResistanceDate: null,
        candleResistanceAdx11: null,
        weeklyBodyReversal: false,
        weeklyBodyDrawdown: null,
        weeklyBodyHigh: null,
        weeklyBodyLengths: null,
        weeklyBodyCurrentDate: null,
        elephantCandle: false,
        elephantBodyPercent: null,
        elephantAtrFactor: null,
        elephantPreviousAtr100: null,
        elephantFastSma8: null,
        elephantSlowSma20: null,
        elephantTradingDate: null,
      }));
      setConsensusDataReady(false);
      setConsensusSnapshot(null);
      setCandleResistanceDataReady(false);
      setWeeklyBodyDataReady(false);
      setElephantDataReady(false);
      setUniverseStocks(normalizedStocks);
      setUniverseCounts({ KOSPI: payload.counts?.KOSPI ?? 0, KOSDAQ: payload.counts?.KOSDAQ ?? 0 });
      setUniverseUpdatedAt(payload.updatedAt ?? new Date().toISOString());
      setLastUpdated(payload.updatedAt ?? new Date().toISOString());
      return normalizedStocks;
    } finally {
      setUniverseLoading(false);
    }
  }, []);

  const loadUniverse = useCallback(async () => {
    try {
      await fetchUniverse();
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "전체 종목 가져오기에 실패했습니다.");
    }
  }, [fetchUniverse]);

  const fetchHistory = useCallback(async (symbol: string, interval: ChartInterval) => {
    setHistoryLoading(true);
    setHistoryError("");
    setCandles([]);
    try {
      const response = await fetch(`/api/history?symbol=${symbol}&interval=${interval}`, { cache: "no-store" });
      const payload = await response.json() as { candles?: Candle[]; error?: string };
      if (!response.ok || !payload.candles?.length) throw new Error(payload.error ?? "차트 데이터를 불러오지 못했습니다.");
      setCandles(payload.candles);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "차트 데이터를 불러오지 못했습니다.");
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const fetchWeeklyReferences = useCallback(async (items: UniverseStock[]) => {
    const batchSize = 20;
    const batches = Array.from({ length: Math.ceil(items.length / batchSize) }, (_, index) => items.slice(index * batchSize, (index + 1) * batchSize));
    const references = new Map<string, number>();
    let nextBatch = 0;
    let completed = 0;
    setWeeklyLoading(true);
    setWeeklyProgress({ completed: 0, total: batches.length });
    try {
      const worker = async () => {
        while (nextBatch < batches.length) {
          const batch = batches[nextBatch];
          nextBatch += 1;
          try {
            const response = await fetch(`/api/weekly-reference?symbols=${batch.map((item) => item.symbol).join(",")}`, { cache: "no-store" });
            const payload = await response.json() as { references?: Array<{ symbol: string; previousFridayClose: number }> };
            if (response.ok) payload.references?.forEach((item) => references.set(item.symbol, item.previousFridayClose));
          } finally {
            completed += 1;
            setWeeklyProgress({ completed, total: batches.length });
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(3, batches.length) }, () => worker()));
      if (references.size === 0) throw new Error("전주 금요일 종가 데이터가 없습니다.");
      const enriched = items.map((item) => {
        const previousFridayClose = references.get(item.symbol) ?? null;
        const weeklyChange = item.price != null && previousFridayClose != null && previousFridayClose > 0
          ? ((item.price / previousFridayClose) - 1) * 100
          : null;
        return { ...item, previousFridayClose, weeklyChange };
      });
      setUniverseStocks(enriched);
      return enriched;
    } finally {
      setWeeklyLoading(false);
    }
  }, []);

  const fetchConsensusUpgrades = useCallback(async (items: UniverseStock[]) => {
    setConsensusLoading(true);
    try {
      const response = await fetch(`/data/consensus-upgrades.json?ts=${Date.now()}`, { cache: "no-store" });
      const payload = await response.json() as ConsensusSnapshot & { error?: string };
      if (!response.ok || !Array.isArray(payload.stocks)) throw new Error(payload.error ?? "컨센서스 상향 리포트 목록을 불러오지 못했습니다.");
      const reports = new Map(payload.stocks.map((item) => [item.symbol, item]));
      const enriched = items.map((item) => {
        const report = reports.get(item.symbol);
        return {
          ...item,
          consensusUpgrade: Boolean(report),
          consensusReportCount: report?.reportCount ?? 0,
        };
      });
      setConsensusSnapshot(payload);
      setConsensusDataReady(true);
      setUniverseStocks(enriched);
      return enriched;
    } finally {
      setConsensusLoading(false);
    }
  }, []);

  const fetchCandleResistance = useCallback(async (items: UniverseStock[]) => {
    const batchSize = 10;
    const batches = Array.from({ length: Math.ceil(items.length / batchSize) }, (_, index) => items.slice(index * batchSize, (index + 1) * batchSize));
    const matches = new Map<string, {
      resistance: number;
      resistanceDistance: number;
      resistanceDate: string;
      adx11: number;
    }>();
    let nextBatch = 0;
    let completed = 0;
    let evaluated = 0;
    setCandleResistanceLoading(true);
    setCandleResistanceProgress({ completed: 0, total: batches.length });
    try {
      const worker = async () => {
        while (nextBatch < batches.length) {
          const batch = batches[nextBatch];
          nextBatch += 1;
          try {
            const response = await fetch(`/api/candle-resistance?symbols=${batch.map((item) => item.symbol).join(",")}`, { cache: "no-store" });
            const payload = await response.json() as {
              evaluated?: number;
              results?: Array<{ symbol: string; resistance: number; resistanceDistance: number; resistanceDate: string; adx11: number }>;
            };
            if (response.ok) {
              evaluated += payload.evaluated ?? 0;
              payload.results?.forEach((item) => matches.set(item.symbol, item));
            }
          } finally {
            completed += 1;
            setCandleResistanceProgress({ completed, total: batches.length });
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(3, batches.length) }, () => worker()));
      if (evaluated === 0) throw new Error("캔들볼륨 저항선 계산에 필요한 90봉 데이터가 없습니다.");
      const enriched = items.map((item) => {
        const match = matches.get(item.symbol);
        return {
          ...item,
          candleResistanceBreakout: Boolean(match),
          candleResistance: match?.resistance ?? null,
          candleResistanceDistance: match?.resistanceDistance ?? null,
          candleResistanceDate: match?.resistanceDate ?? null,
          candleResistanceAdx11: match?.adx11 ?? null,
        };
      });
      setCandleResistanceDataReady(true);
      setUniverseStocks(enriched);
      return enriched;
    } finally {
      setCandleResistanceLoading(false);
    }
  }, []);

  const fetchWeeklyBodyReversals = useCallback(async (items: UniverseStock[]) => {
    const batchSize = 10;
    const batches = Array.from({ length: Math.ceil(items.length / batchSize) }, (_, index) => items.slice(index * batchSize, (index + 1) * batchSize));
    const matches = new Map<string, {
      drawdownFromHigh: number;
      high52: number;
      previousBodyLengths: number[];
      currentDate: string;
    }>();
    let nextBatch = 0;
    let completed = 0;
    let evaluated = 0;
    setWeeklyBodyLoading(true);
    setWeeklyBodyProgress({ completed: 0, total: batches.length });
    try {
      const worker = async () => {
        while (nextBatch < batches.length) {
          const batch = batches[nextBatch];
          nextBatch += 1;
          try {
            const response = await fetch(`/api/weekly-body-reversal?symbols=${batch.map((item) => item.symbol).join(",")}`, { cache: "no-store" });
            const payload = await response.json() as {
              evaluated?: number;
              results?: Array<{
                symbol: string;
                drawdownFromHigh: number;
                high52: number;
                previousBodyLengths: number[];
                currentDate: string;
              }>;
            };
            if (response.ok) {
              evaluated += payload.evaluated ?? 0;
              payload.results?.forEach((item) => matches.set(item.symbol, item));
            }
          } finally {
            completed += 1;
            setWeeklyBodyProgress({ completed, total: batches.length });
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(3, batches.length) }, () => worker()));
      if (evaluated === 0) throw new Error("주봉 반전 계산에 필요한 최근 52주 데이터가 없습니다.");
      const enriched = items.map((item) => {
        const match = matches.get(item.symbol);
        return {
          ...item,
          weeklyBodyReversal: Boolean(match),
          weeklyBodyDrawdown: match?.drawdownFromHigh ?? null,
          weeklyBodyHigh: match?.high52 ?? null,
          weeklyBodyLengths: match?.previousBodyLengths ?? null,
          weeklyBodyCurrentDate: match?.currentDate ?? null,
        };
      });
      setWeeklyBodyDataReady(true);
      setUniverseStocks(enriched);
      return enriched;
    } finally {
      setWeeklyBodyLoading(false);
    }
  }, []);

  const fetchElephantCandles = useCallback(async (items: UniverseStock[]) => {
    const batchSize = 10;
    const batches = Array.from({ length: Math.ceil(items.length / batchSize) }, (_, index) => items.slice(index * batchSize, (index + 1) * batchSize));
    const matches = new Map<string, {
      bodyPercent: number;
      atrFactor: number;
      previousAtr100: number;
      fastSma8: number;
      slowSma20: number;
      tradingDate: string;
    }>();
    let nextBatch = 0;
    let completed = 0;
    let evaluated = 0;
    setElephantLoading(true);
    setElephantProgress({ completed: 0, total: batches.length });
    try {
      const worker = async () => {
        while (nextBatch < batches.length) {
          const batch = batches[nextBatch];
          nextBatch += 1;
          try {
            const response = await fetch(`/api/elephant-candle?symbols=${batch.map((item) => item.symbol).join(",")}`, { cache: "no-store" });
            const payload = await response.json() as {
              evaluated?: number;
              results?: Array<{
                symbol: string;
                bodyPercent: number;
                atrFactor: number;
                previousAtr100: number;
                fastSma8: number;
                slowSma20: number;
                tradingDate: string;
              }>;
            };
            if (response.ok) {
              evaluated += payload.evaluated ?? 0;
              payload.results?.forEach((item) => matches.set(item.symbol, item));
            }
          } finally {
            completed += 1;
            setElephantProgress({ completed, total: batches.length });
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(3, batches.length) }, () => worker()));
      if (evaluated === 0) throw new Error("코끼리캔들 계산에 필요한 ATR(100) 일봉 데이터가 없습니다.");
      const enriched = items.map((item) => {
        const match = matches.get(item.symbol);
        return {
          ...item,
          elephantCandle: Boolean(match),
          elephantBodyPercent: match?.bodyPercent ?? null,
          elephantAtrFactor: match?.atrFactor ?? null,
          elephantPreviousAtr100: match?.previousAtr100 ?? null,
          elephantFastSma8: match?.fastSma8 ?? null,
          elephantSlowSma20: match?.slowSma20 ?? null,
          elephantTradingDate: match?.tradingDate ?? null,
        };
      });
      setElephantDataReady(true);
      setUniverseStocks(enriched);
      return enriched;
    } finally {
      setElephantLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshLiveData();
  }, [refreshLiveData]);

  useEffect(() => {
    void fetchHistory(selectedSymbol, chartInterval);
  }, [selectedSymbol, chartInterval, fetchHistory]);

  const changeView = (nextView: View) => {
    setView(nextView);
    if (nextView === "workflow" && universeStocks.length === 0 && !universeLoading) {
      void loadUniverse();
    }
  };

  const selectStock = (symbol: string) => {
    setSelectedWorkflowStock(null);
    setSelectedSymbol(symbol);
    setChartInterval("day");
    setQuery("");
    setSearchOpen(false);
    setView("dashboard");
  };

  const analyzeWorkflowStock = (result: UniverseStock) => {
    setSelectedWorkflowStock(result);
    setSelectedSymbol(result.symbol);
    setChartInterval("day");
    setView("dashboard");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const togglePipelineNode = (node: PipelineNode) => {
    setSelectedNodeId(node.id);
    if (node.isSource) {
      if (!universeLoading) void loadUniverse();
      return;
    }
    setSelectedPipelineIds((current) => current.includes(node.id) ? current.filter((id) => id !== node.id) : [...current, node.id]);
    setRunComplete(false);
    setIntersectionResults([]);
  };

  const runWorkflow = async () => {
    if (running || selectedConditionPipeline.length === 0) return;
    setRunning(true);
    setRunComplete(false);
    setRefreshError("");
    try {
      let universe = universeStocks.length > 0 ? universeStocks : await fetchUniverse();
      if (selectedConditionPipeline.some((node) => node.id === "weekly10") && !universe.some((item) => item.weeklyChange != null)) {
        universe = await fetchWeeklyReferences(universe);
      }
      if (selectedConditionPipeline.some((node) => node.id === "consensusUp") && !consensusDataReady) {
        universe = await fetchConsensusUpgrades(universe);
      }
      if (selectedConditionPipeline.some((node) => node.id === "candleResistance") && !candleResistanceDataReady) {
        universe = await fetchCandleResistance(universe);
      }
      if (selectedConditionPipeline.some((node) => node.id === "weeklyBodyReversal") && !weeklyBodyDataReady) {
        universe = await fetchWeeklyBodyReversals(universe);
      }
      if (selectedConditionPipeline.some((node) => node.id === "elephantCandle") && !elephantDataReady) {
        universe = await fetchElephantCandles(universe);
      }
      const currentStats = buildUniverseStats(universe);
      setIntersectionResults(buildIntersectionResults(universe, selectedConditionPipeline, currentStats));
      setRunComplete(true);
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "교집합 검색에 실패했습니다.");
    } finally {
      setRunning(false);
    }
  };

  const refreshWorkflowData = async () => {
    if (workflowRefreshing || universeLoading || running) return;
    setWorkflowRefreshing(true);
    setRunComplete(false);
    setRefreshError("");
    try {
      const freshUniverse = await fetchUniverse();
      const weeklyUniverse = await fetchWeeklyReferences(freshUniverse);
      const consensusUniverse = await fetchConsensusUpgrades(weeklyUniverse);
      const resistanceUniverse = await fetchCandleResistance(consensusUniverse);
      const reversalUniverse = await fetchWeeklyBodyReversals(resistanceUniverse);
      const universe = await fetchElephantCandles(reversalUniverse);
      const currentStats = buildUniverseStats(universe);
      if (selectedConditionPipeline.length > 0) {
        setIntersectionResults(buildIntersectionResults(universe, selectedConditionPipeline, currentStats));
        setRunComplete(true);
      } else {
        setIntersectionResults([]);
      }
      setWorkflowRefreshedAt(new Date().toISOString());
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "전체 노드 데이터 새로받기에 실패했습니다.");
    } finally {
      setWorkflowRefreshing(false);
    }
  };

  return (
    <div className="site-shell">
      <header className="topbar">
        <button className="brand" type="button" onClick={() => changeView("dashboard")} aria-label="Dr.K's choice 홈">
          <span className="brand-mark"><i /><i /></span>
          <span>Dr.K&apos;s choice</span>
        </button>

        <nav className="primary-nav" aria-label="주요 메뉴">
          {navItems.map((item) => (
            <button
              type="button"
              key={item.id}
              className={view === item.id ? "nav-button active" : "nav-button"}
              onClick={() => changeView(item.id)}
              aria-current={view === item.id ? "page" : undefined}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="top-actions">
          <button type="button" className="live-refresh" onClick={() => void refreshLiveData()} disabled={refreshing}>
            <span aria-hidden="true">↻</span> {refreshing ? "실제 시세 연결 중" : "실제 데이터 업데이트"}
          </button>
          <span className={hasActualSecurity ? "market-pill is-live" : "market-pill"}><i /> {hasActualSecurity ? "실제 시세 연결" : "예제 데이터"}</span>
          <div className="stock-search">
            <span aria-hidden="true">⌕</span>
            <input
              value={query}
              onChange={(event) => { setQuery(event.target.value); setSearchOpen(true); }}
              onFocus={() => setSearchOpen(true)}
              onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
              placeholder="종목 또는 코드 검색"
              aria-label="종목 또는 코드 검색"
            />
            {searchOpen && (
              <div className="search-results">
                {suggestions.length > 0 ? suggestions.map((item) => (
                  <button type="button" key={item.symbol} onMouseDown={() => selectStock(item.symbol)}>
                    <span><b>{item.name}</b><small>{item.symbol} · {item.market}</small></span>
                    <strong className={(liveQuotes[item.symbol]?.change ?? item.change) >= 0 ? "positive" : "negative"}>{(liveQuotes[item.symbol]?.change ?? item.change) >= 0 ? "+" : ""}{liveQuotes[item.symbol]?.change ?? item.change}%</strong>
                  </button>
                )) : <p>검색 결과가 없습니다.</p>}
              </div>
            )}
          </div>
        </div>
      </header>

      {refreshError && <div className="data-alert" role="status"><span>!</span>{refreshError}<button type="button" onClick={() => setRefreshError("")} aria-label="알림 닫기">×</button></div>}

      {view === "dashboard" && (
        <main className="dashboard page-content">
          <section className="hero-grid" aria-label="종목 핵심 지표">
            <article className="bento-card snapshot-card">
              <div className="card-kicker"><span>{hasActualSecurity ? "LIVE EQUITY SNAPSHOT" : "EQUITY SNAPSHOT"}</span><b>{actualTradedAt ? new Date(actualTradedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "최근 차트 데이터"}</b></div>
              <div className="snapshot-body">
                <div>
                  <div className="stock-title"><h1>{stock.name}</h1><span>{stock.symbol} · {stock.market}</span></div>
                  <div className="main-price">{won(stock.price)} <span className={stock.change >= 0 ? "positive" : "negative"}>{stock.change >= 0 ? "▲" : "▼"} {Math.abs(stock.change).toFixed(2)}%</span></div>
                  <p>{hasActualSecurity ? "워크플로 결과와 NAVER 금융의 실제 최근 데이터가 반영되었습니다." : "실제 데이터 업데이트 버튼을 누르면 최근 시세로 교체됩니다."}</p>
                </div>
                <div className="score-orbit" aria-label={`30봉 추세점수 ${chartMetrics.score}점`}><span>{chartMetrics.score}</span><small>/100</small></div>
              </div>
            </article>

            <article className="bento-card metric-card metric-primary">
              <div className="metric-head"><span>30봉 최고가</span><b>PRICE HIGH</b></div>
              <strong>{won(chartMetrics.high)}</strong><p>{chartInterval === "day" ? "최근 30거래일" : "최근 30주"} 기준</p>
            </article>
            <article className="bento-card metric-card">
              <div className="metric-head"><span>30봉 수익률</span><b className="metric-badge">실제</b></div>
              <strong className={chartMetrics.returnRate >= 0 ? "positive" : "negative"}>{chartMetrics.returnRate >= 0 ? "+" : ""}{chartMetrics.returnRate.toFixed(1)}%</strong><p>첫 종가 대비 최근 종가</p>
            </article>
            <article className="bento-card metric-card">
              <div className="metric-head"><span>추세점수</span><b>30 BAR</b></div>
              <strong>{chartMetrics.score}<em>/100</em></strong><p>수익률 · 이동평균 · 변동성</p>
            </article>
          </section>

          <section className="analysis-grid">
            <article className="bento-card chart-card">
              <div className="section-head">
                <div><span className="eyebrow">PRICE ACTION</span><h2>{chartInterval === "day" ? "일봉" : "주봉"} 30봉 가격 흐름</h2><p>시가·고가·저가·종가와 거래량을 실제 데이터로 표시합니다.</p></div>
                <div className="period-switch" aria-label="차트 봉 간격">
                  {chartIntervals.map((item) => <button type="button" key={item.id} onClick={() => setChartInterval(item.id)} aria-pressed={chartInterval === item.id}>{item.label}</button>)}
                </div>
              </div>
              <div className="chart-legend"><span><i /> {stock.name}</span><b>30봉 고가 {won(chartMetrics.high)}</b><b>30봉 저가 {won(chartMetrics.low)}</b></div>
              <CandleChart candles={candles} name={stock.name} interval={chartInterval} loading={historyLoading} error={historyError} />
            </article>

            <aside className="bento-card thesis-card">
              <div className="section-head compact"><div><span className="eyebrow">DR.K SIGNALS</span><h2>30봉 분석</h2><p>현재 차트에서 계산한 핵심 신호입니다.</p></div><span className="signal-pill">{chartInterval === "day" ? "일봉" : "주봉"} 기준</span></div>
              <ol className="thesis-list">
                <li><span>01</span><div><b>추세 모멘텀</b><p>30봉 수익률은 {chartMetrics.returnRate >= 0 ? "+" : ""}{chartMetrics.returnRate.toFixed(1)}%이며, 최근 종가는 10봉 평균 {won(Math.round(chartMetrics.movingAverage))} {(candles.at(-1)?.close ?? stock.price) >= chartMetrics.movingAverage ? "위" : "아래"}에 있습니다.</p></div></li>
                <li><span>02</span><div><b>거래와 변동성</b><p>평균 거래량은 {Math.round(chartMetrics.averageVolume).toLocaleString("ko-KR")}주, 평균 봉 변동폭은 {chartMetrics.averageRange.toFixed(1)}%입니다.</p></div></li>
                <li className="risk"><span>03</span><div><b>가격 리스크</b><p>현재 종가는 30봉 고점 대비 {chartMetrics.drawdown.toFixed(1)}% 위치입니다. 고점과의 거리와 변동폭을 함께 확인하세요.</p></div></li>
              </ol>
            </aside>
          </section>

          <section className="lower-grid">
            <article className="bento-card valuation-card">
              <div className="section-head compact"><div><span className="eyebrow">30 BAR STATISTICS</span><h2>가격·거래 통계</h2><p>선택한 {chartInterval === "day" ? "일봉" : "주봉"} 30개 기준</p></div></div>
              <div className="valuation-metrics">
                <div><span>30봉 최고가</span><strong>{won(chartMetrics.high)}</strong><small>구간 내 장중 고가</small></div>
                <div><span>30봉 최저가</span><strong>{won(chartMetrics.low)}</strong><small>구간 내 장중 저가</small></div>
                <div><span>평균 거래량</span><strong>{Math.round(chartMetrics.averageVolume).toLocaleString("ko-KR")}</strong><small>봉당 평균 주식 수</small></div>
              </div>
            </article>

            <aside className="bento-card watchlist-card">
              <div className="section-head compact"><div><span className="eyebrow">WATCHLIST</span><h2>관심종목</h2><p>행을 눌러 분석 대상을 바꿔보세요.</p></div></div>
              <div className="watchlist">
                {stocks.slice(1).map((item) => (
                  <button type="button" key={item.symbol} onClick={() => selectStock(item.symbol)}>
                    <span><b>{item.name}</b><small>{item.symbol}</small></span>
                    <strong>{won(liveQuotes[item.symbol]?.price ?? item.price)}</strong>
                    <em className={(liveQuotes[item.symbol]?.change ?? item.change) >= 0 ? "positive" : "negative"}>{(liveQuotes[item.symbol]?.change ?? item.change) >= 0 ? "+" : ""}{liveQuotes[item.symbol]?.change ?? item.change}%</em>
                  </button>
                ))}
              </div>
            </aside>
          </section>

          <section className="engine-strip">
            <div><span className="eyebrow">DR.K ENGINE</span><h2>Dr.K&apos;s choice 분석 노드를 하나의 흐름으로</h2><p>VCP · 외국인/기관 수급 · 대가 합의 13스크린 · 백테스트</p></div>
            <button type="button" className="primary-button" onClick={() => changeView("workflow")}>워크플로 구성하기 <span>→</span></button>
          </section>
        </main>
      )}

      {view === "screener" && (
        <main className="page-content subpage">
          <section className="subpage-hero">
            <div><span className="eyebrow">MULTI-FACTOR SCREENER</span><h1>신호를 겹쳐 후보를 좁히세요.</h1><p>Dr.K&apos;s choice의 성장·가치·모멘텀·수급 기준을 비교 가능한 점수로 정리했습니다.</p></div>
            <div className="universe-count"><span>분석 유니버스</span><strong>5,931</strong><small>KR 2,689 · US 3,242</small></div>
          </section>
          <section className="bento-card screener-card">
            <div className="screen-toolbar">
              <div className="filter-buttons" aria-label="스크리너 스타일 필터">
                {["전체", "성장", "가치", "모멘텀", "수급"].map((filter) => <button type="button" key={filter} onClick={() => setScreenFilter(filter)} aria-pressed={screenFilter === filter}>{filter}</button>)}
              </div>
              <span>데모 스냅샷 · 점수 높은 순</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>종목</th><th>스타일</th><th>퀀트점수</th><th>VCP</th><th>20일 수급</th><th>합의등급</th><th /></tr></thead>
                <tbody>{filteredRows.map((row) => (
                  <tr key={row.symbol}>
                    <td><b>{row.name}</b><small>{row.symbol} · KOSPI</small></td>
                    <td><span className="style-chip">{row.style}</span></td>
                    <td><strong className="table-score">{row.score}</strong><span className="score-bar"><i style={{ width: `${row.score}%` }} /></span></td>
                    <td><span className={row.vcp === "통과" ? "status pass" : "status"}>{row.vcp}</span></td>
                    <td className={row.flow.startsWith("+") ? "positive" : "negative"}>{row.flow}</td>
                    <td><b>{row.rank}</b></td>
                    <td><button type="button" className="row-action" onClick={() => stocks.some((item) => item.symbol === row.symbol) ? selectStock(row.symbol) : undefined}>보기 →</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>
          <p className="disclaimer">교육용 스냅샷 데이터입니다. 결과는 투자 자문이나 수익 보장을 의미하지 않습니다.</p>
        </main>
      )}

      {view === "workflow" && (
        <main className="page-content subpage">
          <section className="subpage-hero workflow-hero">
            <div><span className="eyebrow">INTERSECTION NODE WORKFLOW</span><h1>시총 3,000억 이상 종목에서,<br />모든 조건을 만족한 종목만.</h1><p>1번 노드가 만든 전체 유니버스를 각 조건 노드가 실제 데이터로 다시 평가합니다. 고정된 종목 목록 없이, 선택한 모든 조건을 동시에 통과한 교집합만 보여줍니다.</p></div>
            <div className="workflow-actions">
              <span className={universeStocks.length ? "universe-status ready" : "universe-status"}><i /> {weeklyLoading ? `전주 금요일 종가 ${weeklyProgress.completed}/${weeklyProgress.total} 묶음 수집 중` : consensusLoading ? "컨센서스 상향 종목 확인 중" : candleResistanceLoading ? `캔들 저항선 ${candleResistanceProgress.completed}/${candleResistanceProgress.total} 묶음 계산 중` : weeklyBodyLoading ? `주봉 반전 ${weeklyBodyProgress.completed}/${weeklyBodyProgress.total} 묶음 계산 중` : elephantLoading ? `코끼리캔들 ${elephantProgress.completed}/${elephantProgress.total} 묶음 계산 중` : universeLoading ? "시총 기준 종목 수집 중" : universeStocks.length ? `시총 3천억 이상 ${universeStocks.length.toLocaleString("ko-KR")}개 준비` : "종목 가져오기 실행 대기"}</span>
              <div className="workflow-action-buttons">
                <button type="button" className="workflow-refresh-button" onClick={() => void refreshWorkflowData()} disabled={workflowRefreshing || universeLoading || running} aria-label="전체 노드 데이터를 한 번 새로 받기"><span aria-hidden="true">↻</span>{weeklyLoading ? `주간 데이터 ${weeklyProgress.completed}/${weeklyProgress.total}` : consensusLoading ? "리포트 데이터 확인 중…" : candleResistanceLoading ? `저항선 계산 ${candleResistanceProgress.completed}/${candleResistanceProgress.total}` : weeklyBodyLoading ? `주봉 반전 ${weeklyBodyProgress.completed}/${weeklyBodyProgress.total}` : elephantLoading ? `코끼리캔들 ${elephantProgress.completed}/${elephantProgress.total}` : workflowRefreshing ? "모든 노드 갱신 중…" : universeLoading ? "데이터 받는 중…" : "데이터 새로받기"}</button>
                <button type="button" className="primary-button run-button" onClick={() => void runWorkflow()} disabled={running || universeLoading || workflowRefreshing || selectedConditionPipeline.length === 0}>{running || universeLoading || workflowRefreshing ? "교집합 계산 중…" : "모든 조건 만족 검색"}<span>{running || universeLoading || workflowRefreshing ? "●" : "∩"}</span></button>
              </div>
              <small className={workflowRefreshedAt ? "workflow-refresh-note complete" : "workflow-refresh-note"}>{weeklyLoading ? "전주 금요일 종가를 종목별로 확인해 주간 상승률을 계산하고 있습니다." : consensusLoading ? "최근 5거래일 목표가상향 리포트에서 추출한 종목 스냅샷을 확인하고 있습니다." : candleResistanceLoading ? "전체 유니버스의 일봉 90개와 ADX(11)를 계산하고 있습니다." : weeklyBodyLoading ? "전체 유니버스의 최근 52주 주봉에서 3주 음봉 몸통 확대와 첫 양봉 전환을 계산하고 있습니다." : elephantLoading ? "전체 유니버스의 일봉으로 몸통 비율, 전일 ATR(100), SMA(8) 방향을 계산하고 있습니다." : workflowRefreshing ? "최신 유니버스와 모든 조건 데이터를 1회 받아 전체 노드를 다시 계산합니다." : workflowRefreshedAt ? `전체 노드 갱신 완료 · ${new Date(workflowRefreshedAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}` : "한 번 받은 최신 데이터로 모든 노드의 후보 수와 교집합을 다시 계산합니다."}</small>
            </div>
          </section>
          <section className="workflow-layout">
            <article className="bento-card node-canvas">
              <div className="canvas-head"><div><span className="eyebrow">PIPELINE LIBRARY</span><h2>조건 노드를 순서대로 추가하세요</h2><p>종목 가져오기는 1번에 고정됩니다. 조건 노드는 다시 선택하면 마지막 순서로 이동합니다.</p></div><button type="button" className="clear-pipeline" onClick={() => { setSelectedPipelineIds(["universe"]); setIntersectionResults([]); setRunComplete(false); }}>조건 전체 제거</button></div>
              <div className="pipeline-library">
                {pipelineLibrary.map((node) => {
                  const order = selectedPipelineIds.indexOf(node.id) + 1;
                  return (
                    <button type="button" key={node.id} className={`${order ? "library-node selected" : "library-node"}${node.isSource ? " source-node" : ""}`} onClick={() => togglePipelineNode(node)} aria-pressed={order > 0}>
                      <span className="library-order">{order || "+"}</span>
                      <span><b>{node.name}</b><small>{node.isSource ? "고정 시작 · 시총 3,000억 이상" : `${node.category} · ${nodeCandidateLabel(node)}`}</small></span>
                    </button>
                  );
                })}
              </div>
              <div className="selected-flow-head"><div><span className="eyebrow">SELECTED PIPELINE</span><h2>실행 순서</h2></div><span className={runComplete ? "run-state complete" : "run-state"}><i /> {runComplete ? `교집합 ${intersectionResults.length}개` : `조건 ${selectedConditionPipeline.length}개 선택`}</span></div>
              <div className={running ? "node-track is-running" : "node-track"}>
                {selectedPipeline.length > 0 ? selectedPipeline.map((node, index) => (
                  <div className="node-step-wrap" key={node.id}>
                    <button type="button" className={`${selectedNodeId === node.id ? "node-step active" : "node-step"}${node.isSource ? " source-step" : ""}`} onClick={() => setSelectedNodeId(node.id)}>
                      <span className="node-order">{index + 1}</span><span>{node.category}</span><b>{node.name}</b><small>{nodeCandidateLabel(node)}</small>
                    </button>
                    {index < selectedPipeline.length - 1 && <i className="connector">→</i>}
                  </div>
                )) : <div className="empty-pipeline"><b>조건 노드가 없습니다.</b><span>위 라이브러리에서 분석 조건을 추가하세요.</span></div>}
              </div>
              <div className="node-progress"><i style={{ width: running ? "76%" : runComplete ? "100%" : "0%" }} /></div>
            </article>
            <aside className="bento-card node-inspector">
              <span className="eyebrow">NODE INSPECTOR</span>
              <div className="node-icon">{selectedNode.category.slice(0, 1)}</div>
              <h2>{selectedNode.name}</h2>
              <p>{selectedNode.detail}</p>
              <dl>
                <div><dt>실행 순서</dt><dd>{selectedPipelineIds.includes(selectedNode.id) ? `${selectedPipelineIds.indexOf(selectedNode.id) + 1}번째` : "미선택"}</dd></div>
                <div><dt>검색 방식</dt><dd>{selectedNode.isSource ? "전체 유니버스" : "교집합 AND"}</dd></div>
                <div><dt>후보 풀</dt><dd>{(selectedNode.id === "weekly10" && !weeklyDataReady) || (selectedNode.id === "consensusUp" && !consensusDataReady) || (selectedNode.id === "candleResistance" && !candleResistanceDataReady) || (selectedNode.id === "weeklyBodyReversal" && !weeklyBodyDataReady) || (selectedNode.id === "elephantCandle" && !elephantDataReady) ? "새로받기 또는 검색 필요" : universeStocks.length ? `${nodeCandidateCounts[selectedNode.id].toLocaleString("ko-KR")}개` : "가져오기 전"}</dd></div>
                <div><dt>현재 검색식</dt><dd className="rule-value">{selectedNode.rule}</dd></div>
                {selectedNode.id === "candleResistance" && <div><dt>저항선 산식</dt><dd>(시가+종가+고가+저가)÷4 × 거래량</dd></div>}
                {selectedNode.id === "candleResistance" && <div><dt>결과 순서</dt><dd>저항대비 상승률 낮은 순</dd></div>}
                {selectedNode.id === "weeklyBodyReversal" && <div><dt>고점 기준</dt><dd>최근 52개 주봉의 최고가</dd></div>}
                {selectedNode.id === "weeklyBodyReversal" && <div><dt>몸통 기준</dt><dd>|시가-종가| · 3주 연속 증가</dd></div>}
                {selectedNode.id === "weeklyBodyReversal" && <div><dt>결과 순서</dt><dd>52주 고점대비 하락폭 큰 순</dd></div>}
                {selectedNode.id === "elephantCandle" && <div><dt>검색 방향</dt><dd>SearchMode 1 · 양봉</dd></div>}
                {selectedNode.id === "elephantCandle" && <div><dt>ATR 기준</dt><dd>Wilder ATR(100)의 전일 값</dd></div>}
                {selectedNode.id === "elephantCandle" && <div><dt>이동평균</dt><dd>SMA(8) 상승 · SMA(20) 표시</dd></div>}
                {selectedNode.id === "elephantCandle" && <div><dt>결과 순서</dt><dd>몸통÷전일 ATR 배수 큰 순</dd></div>}
                {selectedNode.id === "consensusUp" && consensusSnapshot && <div><dt>확인한 거래일</dt><dd>{consensusSnapshot.reportDates.join(", ") || "해당 파일 없음"}</dd></div>}
                {selectedNode.id === "consensusUp" && consensusSnapshot && <div><dt>추출 종목</dt><dd>{consensusSnapshot.stocks.length.toLocaleString("ko-KR")}개 · 중복 제거</dd></div>}
                {selectedNode.isSource && <div><dt>시가총액 기준</dt><dd>최종 3,000억원 이상</dd></div>}
                {selectedNode.isSource && <div><dt>시장 구성</dt><dd>{universeStocks.length ? `KOSPI ${universeCounts.KOSPI.toLocaleString("ko-KR")} · KOSDAQ ${universeCounts.KOSDAQ.toLocaleString("ko-KR")}` : "KOSPI + KOSDAQ"}</dd></div>}
                {selectedNode.isSource && universeUpdatedAt && <div><dt>가져온 시각</dt><dd>{new Date(universeUpdatedAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}</dd></div>}
              </dl>
              {selectedNode.isSource ? (
                <button type="button" className="inspector-toggle" disabled={universeLoading} onClick={() => void loadUniverse()}>{universeLoading ? "시총 기준 종목 가져오는 중…" : universeStocks.length ? "시총 기준 종목 새로 가져오기" : "시총 3천억 이상 종목 가져오기"}</button>
              ) : (
                <button type="button" className={selectedPipelineIds.includes(selectedNode.id) ? "inspector-toggle remove" : "inspector-toggle"} onClick={() => togglePipelineNode(selectedNode)}>{selectedPipelineIds.includes(selectedNode.id) ? "파이프라인에서 제거" : "파이프라인에 추가"}</button>
              )}
            </aside>
          </section>
          {runComplete && (
            <section className="bento-card intersection-card">
              <div className="intersection-head"><div><span className="eyebrow">INTERSECTION RESULTS</span><h2>모든 조건 만족 결과</h2><p>{selectedConditionPipeline.map((node) => node.name).join(" ∩ ")} · {intersectionResults.length.toLocaleString("ko-KR")}개</p></div><span className="live-source"><i /> 시총 3천억 이상 · NAVER 금융</span></div>
              {intersectionResults.length > 0 ? <div className="intersection-grid">
                {intersectionResults.map((result) => (
                  <button type="button" key={result.symbol} className="intersection-result" onClick={() => analyzeWorkflowStock(result)} aria-label={`${result.name} 종목분석 열기`}>
                    <div className="intersection-stock"><span><b>{result.name}</b><small>{result.symbol} · {result.market}</small></span><em>{result.marketStatus === "OPEN" ? "장중" : "최근 종가"}</em></div>
                    <div className="intersection-price"><strong>{result.price == null ? "시세 확인 필요" : won(result.price)}</strong>{result.change != null && <span className={result.change >= 0 ? "positive" : "negative"}>{result.change >= 0 ? "+" : ""}{result.change.toFixed(2)}%</span>}</div>
                    <div className="result-data-tags">
                      <span className="market-cap">{marketCapLabel(result.marketCap)}</span>
                      <span className="market-cap">{tradingValueLabel(result.tradingValue)}</span>
                      {result.weeklyChange != null && <span className="market-cap">전주 금요일 대비 {result.weeklyChange > 0 ? "+" : ""}{result.weeklyChange.toFixed(2)}%</span>}
                      {result.consensusUpgrade && <span className="market-cap">목표가 상향 {result.consensusReportCount}건</span>}
                      {result.candleResistanceBreakout && <>
                        <span className="market-cap">저항 {result.candleResistance == null ? "-" : won(result.candleResistance)}</span>
                        <span className="market-cap">저항대비 +{result.candleResistanceDistance?.toFixed(2)}%</span>
                        <span className="market-cap">ADX(11) {result.candleResistanceAdx11?.toFixed(1)}</span>
                        {result.candleResistanceDate && <span className="market-cap">저항봉 {candleDateLabel(result.candleResistanceDate)}</span>}
                      </>}
                      {result.weeklyBodyReversal && <>
                        <span className="market-cap">52주 고점대비 {result.weeklyBodyDrawdown?.toFixed(2)}%</span>
                        <span className="market-cap">52주 고점 {result.weeklyBodyHigh == null ? "-" : won(result.weeklyBodyHigh)}</span>
                        {result.weeklyBodyLengths && <span className="market-cap">3주 몸통 {result.weeklyBodyLengths.map((value) => won(value)).join(" → ")}</span>}
                        {result.weeklyBodyCurrentDate && <span className="market-cap">첫 양봉 {candleDateLabel(result.weeklyBodyCurrentDate)}</span>}
                      </>}
                      {result.elephantCandle && <>
                        <span className="market-cap">몸통비율 {result.elephantBodyPercent?.toFixed(2)}%</span>
                        <span className="market-cap">ATR 배수 {result.elephantAtrFactor?.toFixed(2)}배</span>
                        <span className="market-cap">전일 ATR(100) {result.elephantPreviousAtr100 == null ? "-" : won(Math.round(result.elephantPreviousAtr100))}</span>
                        <span className="market-cap">SMA(8) {result.elephantFastSma8 == null ? "-" : won(Math.round(result.elephantFastSma8))}</span>
                        <span className="market-cap">SMA(20) {result.elephantSlowSma20 == null ? "-" : won(Math.round(result.elephantSlowSma20))}</span>
                        {result.elephantTradingDate && <span className="market-cap">신호일 {candleDateLabel(result.elephantTradingDate)}</span>}
                      </>}
                    </div>
                    <div className="matched-nodes">{result.matchedBy.map((name) => <span key={name}>{name}</span>)}</div>
                    <span className="result-open">종목분석 열기 →</span>
                  </button>
                ))}
              </div> : <div className="empty-intersection"><strong>모든 조건을 동시에 만족한 종목이 없습니다.</strong><p>조건 노드를 하나씩 해제해 교집합을 넓혀보세요.</p></div>}
            </section>
          )}
          <p className="disclaimer">종목 가져오기 노드는 NAVER 금융의 KOSPI·KOSDAQ 상장 종목에서 ETF·ETN을 제외하고 최종 시가총액 3,000억원 이상만 불러옵니다. 캔들볼륨 저항선돌파 노드는 최근 90봉 음봉의 가격·거래량 저항선과 Wilder ADX(11)를 실제 일봉으로 계산합니다. 주봉 3주 음봉후 첫 양봉 노드는 최근 52주 고점 대비 20% 이상 하락, 직전 3주 음봉 몸통 연속 확대, 금주 첫 양봉을 실제 주봉으로 계산합니다. 코끼리캔들 노드는 첨부식의 기본 SearchMode 1에 따라 몸통비율 70% 이상, 몸통이 전일 Wilder ATR(100)의 1.3배 이상, SMA(8) 방향 상승인 양봉을 실제 일봉으로 계산합니다. 컨센서스상향 노드는 로컬 증권리포트의 최근 5거래일 목표가상향 파일에서 종목명·코드만 추출한 공개용 스냅샷을 사용합니다. 모든 조건 노드는 이 전체 유니버스를 대상으로 계산하며, 선택한 조건의 교집합만 표시합니다. 투자 자문이 아닙니다.</p>
        </main>
      )}

      <footer className="site-footer">
        <span><b>Dr.K&apos;s choice</b> · 데이터로 단단한 투자 판단</span>
        <span>{lastUpdated ? `실제 시세 갱신 ${new Date(lastUpdated).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}` : "스타터 예제 데이터"} · 교육용 · 투자 자문 아님</span>
      </footer>
    </div>
  );
}
