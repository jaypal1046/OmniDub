// Unified API layer connecting to the OmniDub backend server and Electron IPC

const isElectron = typeof window !== 'undefined' && !!window.electronAPI;
const API_BASE = ''; // Uses Vite proxy to http://localhost:5001

export const api = {
  isElectron,

  async runPipeline(config) {
    if (isElectron) {
      return await window.electronAPI.runPipeline(config);
    }
    try {
      const res = await fetch(`${API_BASE}/api/pipeline/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      return await res.json();
    } catch (err) {
      return { success: false, error: 'Cannot connect to backend server: ' + err.message };
    }
  },

  async stopPipeline() {
    if (isElectron) {
      return await window.electronAPI.stopPipeline();
    }
    try {
      const res = await fetch(`${API_BASE}/api/pipeline/stop`, { method: 'POST' });
      return await res.json();
    } catch (err) {
      return { success: false, error: err.message };
    }
  },

  // Connects to Server-Sent Events (SSE) or Electron IPC
  subscribeLogs({ onLog, onStatus, onExit }) {
    if (isElectron) {
      const unsubLog = window.electronAPI.onPipelineLog(onLog);
      const unsubExit = window.electronAPI.onPipelineExit(onExit);
      return () => {
        unsubLog();
        unsubExit();
      };
    }

    // Web SSE connection
    try {
      const evtSource = new EventSource(`${API_BASE}/api/pipeline/logs`);
      
      evtSource.addEventListener('log', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (onLog) onLog(data);
        } catch (_) {}
      });

      evtSource.addEventListener('status', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (onStatus) onStatus(data);
        } catch (_) {}
      });

      evtSource.addEventListener('exit', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (onExit) onExit(data.code, data.status);
        } catch (_) {}
      });

      evtSource.onerror = (err) => {
        console.warn('[SSE] Connection error:', err);
      };

      return () => {
        evtSource.close();
      };
    } catch (err) {
      console.error('Failed to subscribe SSE:', err);
      return () => {};
    }
  },

  async listProjects() {
    if (isElectron) {
      return await window.electronAPI.listProjects();
    }
    try {
      const res = await fetch(`${API_BASE}/api/projects`);
      return await res.json();
    } catch (err) {
      console.error('Failed to list projects:', err);
      return [];
    }
  },

  async getProjectDetails(projectName) {
    if (isElectron) {
      return await window.electronAPI.getProjectDetails(projectName);
    }
    try {
      // Subtitles and metadata
      const subRes = await fetch(`${API_BASE}/api/project/${encodeURIComponent(projectName)}/subtitles`);
      const subData = await subRes.json();
      return {
        name: projectName,
        scriptText: subData.originalVtt || '',
        ocrData: null,
        sampleImages: [],
        subtitles: subData
      };
    } catch (err) {
      return null;
    }
  },

  async getSubtitles(projectName) {
    try {
      const res = await fetch(`${API_BASE}/api/project/${encodeURIComponent(projectName)}/subtitles`);
      return await res.json();
    } catch (err) {
      return { error: err.message };
    }
  },

  async saveSubtitles(projectName, filename, content) {
    try {
      const res = await fetch(`${API_BASE}/api/project/${encodeURIComponent(projectName)}/subtitles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, content })
      });
      return await res.json();
    } catch (err) {
      return { success: false, error: err.message };
    }
  },

  async openPath(path) {
    if (isElectron) {
      return await window.electronAPI.openPath(path);
    }
    try {
      const res = await fetch(`${API_BASE}/api/open-folder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      return await res.json();
    } catch (err) {
      alert('Could not open folder: ' + err.message);
      return { success: false };
    }
  },

  async selectFile(options) {
    if (isElectron) {
      return await window.electronAPI.selectFile(options);
    }
    // Web fallback prompt
    const input = prompt('Enter the absolute path to your local file:');
    return input ? input.trim() : null;
  },

  async getSystemStatus() {
    if (isElectron) {
      return await window.electronAPI.getSystemStatus();
    }
    try {
      const res = await fetch(`${API_BASE}/api/system`);
      return await res.json();
    } catch (err) {
      return {
        python: { ok: false, version: 'Server disconnected' },
        ffmpeg: { ok: false, version: 'Server disconnected' },
        env: { hasGeminiKey: false, hasAimlKey: false }
      };
    }
  },

  async saveEnv(envVars) {
    if (isElectron) {
      return await window.electronAPI.saveEnv(envVars);
    }
    return { success: true };
  },

  formatMediaUrl(filePathOrUrl) {
    if (!filePathOrUrl) return '';
    if (filePathOrUrl.startsWith('/api/media')) return filePathOrUrl;
    if (isElectron) {
      const normalized = filePathOrUrl.replace(/\\/g, '/');
      return `media://${normalized}`;
    }
    return filePathOrUrl;
  }
};
