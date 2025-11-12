/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    // Tránh Next.js server phải tự fetch ảnh từ backend (hay bị block qua ngrok/localhost)
    unoptimized: true,
  },
};

module.exports = nextConfig;