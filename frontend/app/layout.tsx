import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SAMC 수입식품 검역 AI",
  description: "수입식품 검역 자동화 파이프라인 플랫폼",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
