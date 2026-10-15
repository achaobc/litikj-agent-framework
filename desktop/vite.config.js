import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { spawn } from 'child_process';
import net from 'net';
import path from 'path';

function checkPort(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(400);
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.once('error', () => {
      socket.destroy();
      resolve(false);
    });
    socket.connect(port, '127.0.0.1');
  });
}

function pythonSidecarPlugin() {
  let pyProcess = null;
  return {
    name: 'python-sidecar-dev',
    async configureServer() {
      const inUse = await checkPort(8765);
      if (inUse) {
        console.log('⚡ [Vite] 8765 端口已有 Python 微内核在运行，保持复用。');
        return;
      }
      const rootDir = path.resolve(__dirname, '..');
      const scriptPath = path.resolve(rootDir, 'apps/server/headless_server.py');
      console.log('🚀 [Vite] 正在伴生启动 Python AI 微内核 (Port 8765)...');
      pyProcess = spawn('python', [scriptPath, '--port', '8765', '--host', '127.0.0.1'], {
        cwd: rootDir,
        shell: true,
        stdio: 'inherit'
      });
      pyProcess.on('error', (err) => {
        console.error('⚠️ [Vite] 伴生拉起 Python 微内核失败:', err);
      });
      process.on('exit', () => {
        if (pyProcess) pyProcess.kill();
      });
    }
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue(), pythonSidecarPlugin()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ['**/src-tauri/**']
    }
  }
});
