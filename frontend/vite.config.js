import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import path from 'node:path'
import { execSync } from 'node:child_process'

// --- Hash court du commit compilé (affiché avec la version, voir src/version.js)
// 1) Sur Render, la variable RENDER_GIT_COMMIT contient le hash complet du
//    commit en cours de déploiement : on en garde les 7 premiers caractères.
// 2) En local, on le demande à git.
// 3) Sinon (pas de git), "dev".
function hashCommitCourt() {
  if (process.env.RENDER_GIT_COMMIT) return process.env.RENDER_GIT_COMMIT.slice(0, 7)
  try {
    return execSync('git rev-parse --short=7 HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim()
  } catch {
    return 'dev'
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  // Valeurs calculées à CHAQUE compilation et remplacées telles quelles dans
  // le code (lues par src/version.js) : impossible d'oublier de les mettre à jour.
  define: {
    'import.meta.env.VITE_COMMIT_BUILD': JSON.stringify(hashCommitCourt()),
    'import.meta.env.VITE_DATE_BUILD': JSON.stringify(new Date().toISOString()),
  },
  server: {
    host: true,
    port: 5173,
  },
})
