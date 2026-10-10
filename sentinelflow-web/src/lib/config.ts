// =============================================================================
// SentinelFlow Frontend Configuration
// =============================================================================
// Centralized configuration for API endpoints and environment settings

// Next.js only inlines `process.env.NEXT_PUBLIC_*` into the browser bundle when
// each variable is accessed literally; a dynamic `process.env[key]` lookup is
// always undefined on the client and silently falls back to the default.
const env = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL,
  wsUrl: process.env.NEXT_PUBLIC_WS_URL,
  enableAiChat: process.env.NEXT_PUBLIC_ENABLE_AI_CHAT,
  enableNetworkGraph: process.env.NEXT_PUBLIC_ENABLE_NETWORK_GRAPH,
  enableAuth: process.env.NEXT_PUBLIC_ENABLE_AUTH,
}

export const config = {
  // API Configuration
  api: {
    baseUrl: env.apiUrl || "http://127.0.0.1:8000",
    wsUrl: env.wsUrl || "ws://127.0.0.1:8000",
  },

  // API Endpoints
  endpoints: {
    // System
    health: "/api/v1/system/health",
    stats: "/api/v1/system/stats",

    // Alerts
    alerts: "/api/v1/alerts",
    alertDetail: (id: string) => `/api/v1/alerts/${id}`,
    alertDismiss: (id: string) => `/api/v1/alerts/${id}/dismiss`,

    // Cases
    cases: "/api/v1/cases",
    caseDetail: (id: string) => `/api/v1/cases/${id}`,

    // Transactions
    transactions: "/api/v1/transactions",

    // Auth
    login: "/api/v1/auth/login",
    register: "/api/v1/auth/register",
    me: "/api/v1/auth/me",
    refresh: "/api/v1/auth/refresh",

    // ML
    predict: "/api/v1/risk/score",
    modelInfo: "/api/v1/ml/models",
    mlFeatures: "/api/v1/ml/features",

    // KYC
    kycScreen: "/api/v1/kyc/screen",

    // Chat
    chat: "/api/v1/chat",

    // Graph (single source; see backend routes/graph.py)
    graphData: "/api/v1/graph/data",
    graphRings: "/api/v1/graph/rings",
    graphAccount: (iban: string) => `/api/v1/graph/account/${iban}`,

    // WebSocket
    wsAlerts: "/ws/alerts",
  },

  // Feature Flags
  features: {
    enableAiChat: env.enableAiChat !== "false",
    enableNetworkGraph: env.enableNetworkGraph !== "false",
    // The backend always requires a JWT on data routes, so auth is on unless
    // explicitly disabled.
    enableAuth: env.enableAuth !== "false",
  },

  // UI Settings
  ui: {
    alertRefreshInterval: 2000, // ms
    statsRefreshInterval: 2000, // ms
    wsReconnectDelay: 3000, // ms
    wsPingInterval: 10000, // ms
    maxAlertsInFeed: 50,
  },
} as const

// Helper functions
export function getApiUrl(endpoint: string): string {
  return `${config.api.baseUrl}${endpoint}`
}

export function getWsUrl(endpoint: string): string {
  return `${config.api.wsUrl}${endpoint}`
}

// Type exports
export type Config = typeof config
