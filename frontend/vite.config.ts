import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Binds to 0.0.0.0 (not just localhost) so other machines on the LAN can reach the dev
  // server at this machine's 192.168.x.x address, not just from the host itself.
  server: {
    host: true,
  },
})
