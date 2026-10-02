import type { NextConfig } from "next";

// Trình duyệt chỉ nói chuyện với origin của frontend; Next proxy /api và /auth sang backend.
// Nhờ vậy cookie phiên HttpOnly SameSite=Lax luôn là first-party (ADC-008), kể cả khi deploy
// frontend (Vercel) và backend (Render) ở 2 domain khác nhau.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/auth/:path*", destination: `${backend}/auth/:path*` },
    ];
  },
};

export default nextConfig;
