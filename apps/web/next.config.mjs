/** @type {import('next').NextConfig} */

// When the frontend and backend are served through one origin (e.g. a public
// tunnel), API calls are same-origin relative paths that Next proxies to the
// backend — no CORS, one shareable URL. Set BACKEND_ORIGIN to point the proxy
// at the running FastAPI server (default localhost:8000).
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_ORIGIN}/api/:path*` },
      { source: "/health", destination: `${BACKEND_ORIGIN}/health` },
    ];
  },
};

export default nextConfig;
