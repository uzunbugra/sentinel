import type { Metadata } from "next"
import { Space_Grotesk, Inter, JetBrains_Mono } from "next/font/google"
import "./globals.css"
import { AuthProvider } from "@/contexts/auth-context"

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display-google",
  display: "swap",
})

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-body-google",
  display: "swap",
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono-google",
  display: "swap",
})

export const metadata: Metadata = {
  title: "SentinelFlow — Real-Time Financial Fraud Detection",
  description:
    "Para hareket ederken dolandırıcılığı yakalar. Kafka, Neo4j, Redis ve LightGBM ile dairesel aklama, imkansız seyahat ve ML dolandırıcılık skoru.",
  keywords: [
    "fraud detection",
    "money laundering",
    "Neo4j",
    "Kafka",
    "Redis",
    "LightGBM",
    "real-time",
    "SOC",
  ],
  openGraph: {
    title: "SentinelFlow — Real-Time Financial Fraud Detection",
    description:
      "Gerçek zamanlı finansal dolandırıcılık tespit sistemi. Graf, konum ve LightGBM tabanlı tespit; her ML alarmı model açıklamasıyla gelir.",
    type: "website",
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="tr" className="dark">
      <body
        className={`${spaceGrotesk.variable} ${inter.variable} ${jetbrainsMono.variable} font-sans bg-base text-zinc-100 antialiased`}
      >
        <AuthProvider>
          <div className="min-h-screen">{children}</div>
        </AuthProvider>
      </body>
    </html>
  )
}
