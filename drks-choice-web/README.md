# Dr.K's choice

한국 주식시장의 시가총액 3,000억원 이상 종목을 대상으로 조건 교집합을 계산하고, 선택한 종목의 일봉·주봉 30개 가격 흐름을 분석하는 웹 대시보드입니다.

## 주요 기능

- KOSPI·KOSDAQ 시가총액 3,000억원 이상 종목 수집
- 순서형 워크플로 노드와 모든 조건의 교집합 검색
- 검색 결과 종목의 일봉·주봉 30봉 차트 및 통계 분석
- 실제 데이터 업데이트와 종목 검색
- 데스크톱·모바일 반응형 화면

## 로컬 실행

Node.js 22.13 이상이 필요합니다.

```bash
npm install
npm run dev
```

프로덕션 빌드는 다음 명령으로 확인할 수 있습니다.

```bash
npm run build
```

## 배포 참고

이 프로젝트는 `app/api` 서버 라우트를 사용하므로 정적 파일만 제공하는 GitHub Pages에서는 실제 데이터 기능이 실행되지 않습니다. Node.js 서버 또는 Cloudflare Workers 호환 환경에 배포해야 전체 기능을 사용할 수 있습니다.

Cloudflare Workers 무료 배포 설정은 `wrangler.jsonc`에 포함되어 있습니다. Cloudflare 로그인 후 다음 명령으로 빌드와 배포를 한 번에 실행할 수 있습니다.

```bash
npx wrangler login
npx vinext deploy --name drks-choice-analytics
```

현재 무료 운영 사이트: <https://drks-choice-analytics.promokorea.workers.dev/>

교육·분석용 프로젝트이며 투자 자문이나 수익을 보장하지 않습니다.
