import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const origin = `${protocol}://${host}`;

  return {
    title: "Dr.K's choice | 데이터로 단단한 투자 판단",
    description: "시가총액 3,000억원 이상 한국 종목을 워크플로 조건과 일봉·주봉 30봉 데이터로 분석하는 증권 분석 대시보드입니다.",
    openGraph: {
      title: "Dr.K's choice",
      description: "데이터로 단단한 투자 판단",
      type: "website",
      locale: "ko_KR",
      images: [{ url: `${origin}/og.png`, width: 1536, height: 1024, alt: "Dr.K's choice 증권 분석 대시보드" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "Dr.K's choice",
      description: "데이터로 단단한 투자 판단",
      images: [`${origin}/og.png`],
    },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
