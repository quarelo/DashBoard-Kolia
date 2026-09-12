import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      // Bind mount do host (Windows/Docker Desktop) para dentro do container:
      // eventos inotify não atravessam o mount, então o watcher padrão do
      // chokidar nunca vê a mudança e o Vite continua servindo o módulo
      // antigo do cache mesmo com o arquivo já atualizado no disco.
      // Confirmado direto: `curl localhost:5173/src/pages/Dashboard.tsx`
      // ainda trazia o componente anterior bem depois do arquivo ter mudado.
      usePolling: true,
    },
  },
})
