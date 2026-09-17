const { app, BrowserWindow, ipcMain, shell, dialog, protocol, net } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, execSync } = require('child_process');

let mainWindow = null;
let activeProcess = null;

const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'output');
const ENV_FILE = path.join(PROJECT_ROOT, '.env');

// Register custom protocol for streaming local media
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'media',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      bypassCSP: true,
      stream: true
    }
  }
]);

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1340,
    height: 880,
    minWidth: 1050,
    minHeight: 700,
    backgroundColor: '#0a0d14',
    title: 'OmniDub AI - Manhwa & Video Recap Studio',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false, // Allows local media fetching via media:// protocol
    },
    autoHideMenuBar: true,
  });

  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  const devServerUrl = 'http://localhost:5173';

  if (isDev) {
    mainWindow.loadURL(devServerUrl);
    // Open DevTools in dev mode if needed
    // mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  // Handle media:// protocol to safely stream local video/audio/images
  protocol.handle('media', (request) => {
    try {
      let rawPath = request.url.replace(/^media:\/\//, '');
      // Handle windows drive paths (e.g. c:/Jay/... or c%3A/Jay/...)
      rawPath = decodeURIComponent(rawPath);
      // Remove leading slash if it became /C:/...
      if (/^\/[a-zA-Z]:/.test(rawPath)) {
        rawPath = rawPath.slice(1);
      }
      const safePath = path.normalize(rawPath);
      return net.fetch('file:///' + safePath.replace(/\\/g, '/'));
    } catch (err) {
      console.error('Error handling media protocol:', err);
      return new Response('Not found', { status: 404 });
    }
  });

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (activeProcess) {
      try {
        process.platform === 'win32'
          ? execSync(`taskkill /pid ${activeProcess.pid} /T /F`)
          : activeProcess.kill('SIGKILL');
      } catch (_) {}
    }
    app.quit();
  }
});

// IPC: Run Python Recap Pipeline
ipcMain.handle('run-pipeline', async (_event, config) => {
  if (activeProcess) {
    return { success: false, error: 'A pipeline job is already active! Stop it first.' };
  }

  const {
    engine, // 'manhwa' | 'retimed' | 'standard'
    source, // URL or local file path
    projectName,
    aspect, // '16:9' | '9:16'
    voice,
    workers,
    mode,
    burnSubtitles,
    force,
    customPrompt
  } = config;

  let scriptName = 'app_manhwa.py';
  const args = [];

  if (engine === 'manhwa') {
    scriptName = 'app_manhwa.py';
    args.push(source);
    if (projectName) args.push('-o', projectName);
    if (aspect) args.push('--aspect', aspect);
    if (voice) args.push('-v', voice);
    if (workers) args.push('-w', String(workers));
    if (force) args.push('--force');
    if (customPrompt) args.push('--prompt', customPrompt);
  } else if (engine === 'retimed') {
    scriptName = 'app_retimed.py';
    args.push(source);
    if (projectName) args.push('-name', projectName);
    if (voice) args.push('-v', voice);
    if (burnSubtitles) args.push('--burn-subtitles');
    args.push('--auto-continue');
    args.push('-mode', String(mode || 4));
    if (force) args.push('--force');
  } else {
    // standard
    scriptName = 'app.py';
    args.push(source);
    if (projectName) args.push('-name', projectName);
    if (voice) args.push('-v', voice);
    if (burnSubtitles) args.push('--burn-subtitles');
    args.push('--auto-continue');
    args.push('-mode', String(mode || 4));
    if (force) args.push('--force');
  }

  const pythonBin = process.platform === 'win32' ? 'python' : 'python3';

  try {
    const child = spawn(pythonBin, [scriptName, ...args], {
      cwd: PROJECT_ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    activeProcess = child;

    child.stdout.on('data', (data) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pipeline-log', {
          type: 'stdout',
          text: data.toString()
        });
      }
    });

    child.stderr.on('data', (data) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pipeline-log', {
          type: 'stderr',
          text: data.toString()
        });
      }
    });

    child.on('close', (code) => {
      activeProcess = null;
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pipeline-exit', code);
      }
    });

    child.on('error', (err) => {
      activeProcess = null;
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pipeline-log', {
          type: 'error',
          text: `Failed to spawn process: ${err.message}\n`
        });
        mainWindow.webContents.send('pipeline-exit', 1);
      }
    });

    return { success: true, pid: child.pid };
  } catch (err) {
    activeProcess = null;
    return { success: false, error: err.message };
  }
});

// IPC: Stop running process
ipcMain.handle('stop-pipeline', async () => {
  if (!activeProcess) {
    return { success: true, message: 'No pipeline running' };
  }
  try {
    const pid = activeProcess.pid;
    if (process.platform === 'win32') {
      execSync(`taskkill /pid ${pid} /T /F`);
    } else {
      activeProcess.kill('SIGKILL');
    }
    activeProcess = null;
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

// IPC: List projects in output/
ipcMain.handle('list-projects', async () => {
  try {
    if (!fs.existsSync(OUTPUT_DIR)) {
      fs.mkdirSync(OUTPUT_DIR, { recursive: true });
      return [];
    }

    const entries = fs.readdirSync(OUTPUT_DIR, { withFileTypes: true });
    const projects = [];

    for (const ent of entries) {
      if (ent.isDirectory()) {
        const projPath = path.join(OUTPUT_DIR, ent.name);
        const files = fs.readdirSync(projPath);

        // Check key output artifacts
        const hasManhwaVideo = files.includes('FINAL_MANHWA_RECAP.mp4');
        const hasVideoRecap = files.includes('FINAL_RECAP.mp4');
        const hasMasterAudio = files.includes('master_audio.mp3') || files.includes('synced_voiceover.mp3');
        const hasScript = files.includes('master_script.txt');
        const hasOCR = files.includes('ocr_results.json');
        const hasState = files.includes('state.json');

        let videoFile = null;
        if (hasManhwaVideo) videoFile = path.join(projPath, 'FINAL_MANHWA_RECAP.mp4');
        else if (hasVideoRecap) videoFile = path.join(projPath, 'FINAL_RECAP.mp4');

        let audioFile = null;
        if (files.includes('master_audio.mp3')) audioFile = path.join(projPath, 'master_audio.mp3');
        else if (files.includes('synced_voiceover.mp3')) audioFile = path.join(projPath, 'synced_voiceover.mp3');

        let stateData = null;
        if (hasState) {
          try {
            stateData = JSON.parse(fs.readFileSync(path.join(projPath, 'state.json'), 'utf8'));
          } catch (_) {}
        }

        const stats = fs.statSync(projPath);

        projects.push({
          name: ent.name,
          path: projPath,
          updatedAt: stats.mtimeMs,
          hasVideo: !!videoFile,
          videoPath: videoFile,
          hasAudio: !!audioFile,
          audioPath: audioFile,
          hasScript,
          hasOCR,
          state: stateData,
          totalFiles: files.length,
          files: files.slice(0, 15),
        });
      }
    }

    // Sort newest first
    projects.sort((a, b) => b.updatedAt - a.updatedAt);
    return projects;
  } catch (err) {
    console.error('Error listing projects:', err);
    return [];
  }
});

// IPC: Get project detail content
ipcMain.handle('get-project-details', async (_event, projectName) => {
  try {
    const projDir = path.join(OUTPUT_DIR, projectName);
    if (!fs.existsSync(projDir)) return null;

    let scriptText = '';
    const scriptPath = path.join(projDir, 'master_script.txt');
    if (fs.existsSync(scriptPath)) {
      scriptText = fs.readFileSync(scriptPath, 'utf8');
    }

    let ocrData = null;
    const ocrPath = path.join(projDir, 'ocr_results.json');
    if (fs.existsSync(ocrPath)) {
      try {
        ocrData = JSON.parse(fs.readFileSync(ocrPath, 'utf8'));
      } catch (_) {}
    }

    // Check panel images
    const manhwaSlicesDir = path.join(projDir, 'images', 'manhwa_slices');
    let sampleImages = [];
    if (fs.existsSync(manhwaSlicesDir)) {
      const sliceFiles = fs.readdirSync(manhwaSlicesDir)
        .filter(f => f.match(/\.(png|jpg|jpeg|webp)$/i))
        .slice(0, 16)
        .map(f => path.join(manhwaSlicesDir, f));
      sampleImages = sliceFiles;
    }

    return {
      name: projectName,
      scriptText,
      ocrData,
      sampleImages,
    };
  } catch (err) {
    console.error('Error getting project details:', err);
    return null;
  }
});

// IPC: Open folder or file in native OS Explorer
ipcMain.handle('open-path', async (_event, targetPath) => {
  if (!targetPath) return { success: false };
  const fullPath = path.resolve(targetPath);
  if (fs.existsSync(fullPath)) {
    await shell.openPath(fullPath);
    return { success: true };
  }
  return { success: false, error: 'Path does not exist' };
});

// IPC: Native File/Folder picker dialog
ipcMain.handle('select-file', async (_event, options = {}) => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: options.isFolder ? ['openDirectory'] : ['openFile'],
    filters: options.filters || [
      { name: 'Media Files', extensions: ['mp4', 'mkv', 'avi', 'mov', 'pdf', 'zip'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
});

// IPC: Check system status (python, ffmpeg, env keys)
ipcMain.handle('get-system-status', async () => {
  let pythonOk = false;
  let pythonVersion = '';
  try {
    const py = execSync('python --version', { encoding: 'utf8' }).trim();
    pythonOk = true;
    pythonVersion = py;
  } catch (_) {}

  let ffmpegOk = false;
  let ffmpegVersion = '';
  try {
    const ff = execSync('ffmpeg -version', { encoding: 'utf8' });
    ffmpegOk = true;
    ffmpegVersion = ff.split('\n')[0];
  } catch (_) {}

  let hasGeminiKey = false;
  let hasAimlKey = false;
  if (fs.existsSync(ENV_FILE)) {
    const envContent = fs.readFileSync(ENV_FILE, 'utf8');
    hasGeminiKey = envContent.includes('GEMINI_API_KEY=') && !envContent.includes('GEMINI_API_KEY=\n');
    hasAimlKey = envContent.includes('AIMLAPI=');
  }

  return {
    python: { ok: pythonOk, version: pythonVersion },
    ffmpeg: { ok: ffmpegOk, version: ffmpegVersion },
    env: { hasGeminiKey, hasAimlKey, envPath: ENV_FILE }
  };
});

// IPC: Save or update .env variables
ipcMain.handle('save-env', async (_event, envVars) => {
  try {
    let current = '';
    if (fs.existsSync(ENV_FILE)) {
      current = fs.readFileSync(ENV_FILE, 'utf8');
    }
    const lines = current.split('\n').filter(l => l.trim().length > 0);
    const parsed = {};
    for (const l of lines) {
      const idx = l.indexOf('=');
      if (idx > -1) {
        parsed[l.slice(0, idx).trim()] = l.slice(idx + 1).trim();
      }
    }
    Object.assign(parsed, envVars);
    const newContent = Object.entries(parsed)
      .map(([k, v]) => `${k}=${v}`)
      .join('\n') + '\n';
    fs.writeFileSync(ENV_FILE, newContent, 'utf8');
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});
