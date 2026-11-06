import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: requests to /api go to the FastAPI backend (port 8000 unless CG_API says otherwise).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': process.env.CG_API || 'http://localhost:8000' } },
})
