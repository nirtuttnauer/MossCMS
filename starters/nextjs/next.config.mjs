import path from 'node:path';
import { fileURLToPath } from 'node:url';

const starterDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(starterDir, '../..');

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Turbopack resolves modules inside this directory. The delivery client lives at shared/delivery.mjs.
  turbopack: {
    root: repoRoot,
  },
  outputFileTracingRoot: repoRoot,
};

export default nextConfig;
