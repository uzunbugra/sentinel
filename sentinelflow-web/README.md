# SentinelFlow Web Dashboard

Modern Real-Time Fraud Detection Dashboard built with Next.js, Tailwind CSS, and WebSockets.

## Features

- 🛡️ **Cyber/SOC Aesthetic**: Designed for security analysts.
- ⚡ **Real-Time**: Live updates via WebSockets.
- 📊 **Visualizations**: Fraud rings, transaction volume, and severity feeds.

## Getting Started

Requires **Node.js 22** (`>=22.12`, see `engines` in `package.json` and `.nvmrc`);
some dependencies (e.g. `camera-controls`) do not support Node 20. The Docker
image (`node:22-alpine`) and CI use the same line. With nvm: `nvm use`.

1.  **Install dependencies** (from the lockfile):
    ```bash
    npm ci
    ```

2.  **Run the development server**:
    ```bash
    npm run dev
    ```

3.  **Open [http://localhost:3000](http://localhost:3000)** with your browser.

## Backend Connection

This frontend connects to the SentinelFlow API at `ws://localhost:8000/ws/alerts`.
Ensure the backend is running before starting the frontend.
