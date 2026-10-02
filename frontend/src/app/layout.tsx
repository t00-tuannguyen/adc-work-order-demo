import type { Metadata } from "next";
import { Fira_Code, Fira_Sans } from "next/font/google";

import "./globals.css";

const firaSans = Fira_Sans({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-fira-sans",
});
const firaCode = Fira_Code({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-fira-code" });

export const metadata: Metadata = {
  title: "ADC Control Tower",
  description: "Điều phối lệnh chiếu xạ 2 line",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className={`${firaSans.variable} ${firaCode.variable}`}>
      <body>{children}</body>
    </html>
  );
}
