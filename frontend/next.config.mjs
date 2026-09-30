import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin(
  './src/i18n/request.ts'
);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The local dashboard is commonly opened as 127.0.0.1:3001.  Next 16
  // otherwise rejects its Turbopack HMR socket as cross-origin, leaving a
  // stale client bundle that never refreshes the camera workspace.
  allowedDevOrigins: ["127.0.0.1", "localhost"]
};

export default withNextIntl(nextConfig);
