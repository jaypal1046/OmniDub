/**
 * OmniDub AI - Local Backend Server (Node.js)
 * Provides REST API & Server-Sent Events (SSE) for running Python recap pipelines,
 * streaming live logs, managing subtitle translations, and serving media.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn, execSync, exec } = require('child_process');
const { URL } = require('url');

const PORT = process.env.PORT || 5055;
const PROJECT_ROOT = path.resolve(__dirname, '..');
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'output');
const ENV_FILE = path.join(PROJECT_ROOT, '.env');

let activeProcess = null;
let activeJobConfig = null;
let currentJobStatus = 'IDLE'; // 'IDLE' | 'RUNNING' | 'AWAITING_TRANSLATION' | 'COMPLETED' | 'FAILED'
const sseClients = new Set();
let logHistory = [];

function broadcastSSE(type, data) {
  const payload = `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const client of sseClients) {
    try {
      client.write(payload);
    } catch (_) {
      sseClients.delete(client);
    }
  }
}

function appendLog(logEntry) {
  logHistory.push(logEntry);
  if (logHistory.length > 3000) logHistory.shift();
  broadcastSSE('log', logEntry);
}

// Helper for JSON responses
function sendJSON(res, data, statusCode = 200) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  });
  res.end(JSON.stringify(data));
}

// Media streaming with Range headers
function serveMediaFile(filePath, req, res) {
  if (!fs.existsSync(filePath)) {
    res.writeHead(404);
    return res.end('File not found');
  }

  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const range = req.headers.range;

  const ext = path.extname(filePath).toLowerCase();
  const mimeTypes = {
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.vtt': 'text/vtt',
    '.srt': 'text/plain',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.json': 'application/json',
    '.txt': 'text/plain'
  };
  const contentType = mimeTypes[ext] || 'application/octet-stream';

  if (range) {
    const parts = range.replace(/bytes=/, '').split('-');
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
    const chunksize = end - start + 1;
    const file = fs.createReadStream(filePath, { start, end });

    res.writeHead(206, {
      'Content-Range': `bytes ${start}-${end}/${fileSize}`,
      'Accept-Ranges': 'bytes',
      'Content-Length': chunksize,
      'Content-Type': contentType,
      'Access-Control-Allow-Origin': '*',
    });
    file.pipe(res);
  } else {
    res.writeHead(200, {
      'Content-Length': fileSize,
      'Content-Type': contentType,
      'Access-Control-Allow-Origin': '*',
    });
    fs.createReadStream(filePath).pipe(res);
  }
}

// Parse request body
function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk.toString(); });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
  });
}

const server = http.createServer(async (req, res) => {
  // CORS Preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Range',
    });
    return res.end();
  }

  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost:5001'}`);
  const pathname = parsedUrl.pathname;

  // 1. SSE Stream: /api/pipeline/logs
  if (pathname === '/api/pipeline/logs') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    });

    // Send initial handshake and recent logs
    res.write(`event: status\ndata: ${JSON.stringify({ isRunning: !!activeProcess, status: currentJobStatus, activeJob: activeJobConfig })}\n\n`);
    for (const log of logHistory.slice(-150)) {
      res.write(`event: log\ndata: ${JSON.stringify(log)}\n\n`);
    }

    sseClients.add(res);
    req.on('close', () => {
      sseClients.delete(res);
    });
    return;
  }

  // 2. Start Pipeline: POST /api/pipeline/start
  if (pathname === '/api/pipeline/start' && req.method === 'POST') {
    if (activeProcess) {
      return sendJSON(res, { success: false, error: 'A recap pipeline is already running! Please wait or stop it first.' }, 400);
    }

    try {
      const config = await parseBody(req);
      const {
        engine = 'manhwa',
        source,
        projectName,
        aspect = '16:9',
        voice = 'en-US-ChristopherNeural',
        workers = 8,
        mode = 4,
        burnSubtitles = true,
        force = false,
        autoContinue = false,
        customPrompt
      } = config;

      if (!source) {
        return sendJSON(res, { success: false, error: 'Source URL or file path is required.' }, 400);
      }

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
        if (autoContinue) args.push('--auto-continue');
        args.push('-mode', String(mode || 4));
        if (force) args.push('--force');
      } else {
        // standard
        scriptName = 'app.py';
        args.push(source);
        if (projectName) args.push('-name', projectName);
        if (voice) args.push('-v', voice);
        if (burnSubtitles) args.push('--burn-subtitles');
        if (autoContinue) args.push('--auto-continue');
        args.push('-mode', String(mode || 4));
        if (force) args.push('--force');
      }

      const pythonBin = process.platform === 'win32' ? 'python' : 'python3';
      
      logHistory = [];
      activeJobConfig = { ...config, projectName };
      currentJobStatus = 'RUNNING';

      const child = spawn(pythonBin, [scriptName, ...args], {
        cwd: PROJECT_ROOT,
        env: { ...process.env, PYTHONUNBUFFERED: '1' }
      });

      activeProcess = child;
      broadcastSSE('status', { isRunning: true, status: 'RUNNING', activeJob: activeJobConfig });

      child.stdout.on('data', (data) => {
        const text = data.toString();
        // Detect pipeline pause for translation
        if (text.includes('PIPELINE PAUSED FOR SUBTITLE TRANSLATION') || text.includes('AWAITING_TRANSLATION')) {
          currentJobStatus = 'AWAITING_TRANSLATION';
          broadcastSSE('status', { isRunning: true, status: 'AWAITING_TRANSLATION', activeJob: activeJobConfig });
        }
        appendLog({ type: 'stdout', text });
      });

      child.stderr.on('data', (data) => {
        const text = data.toString();
        appendLog({ type: 'stderr', text });
      });

      child.on('close', (code) => {
        activeProcess = null;
        if (currentJobStatus !== 'AWAITING_TRANSLATION') {
          currentJobStatus = code === 0 ? 'COMPLETED' : 'FAILED';
        }
        broadcastSSE('status', { isRunning: false, status: currentJobStatus, activeJob: activeJobConfig });
        broadcastSSE('exit', { code, status: currentJobStatus });
      });

      child.on('error', (err) => {
        activeProcess = null;
        currentJobStatus = 'FAILED';
        appendLog({ type: 'error', text: `Process error: ${err.message}\n` });
        broadcastSSE('status', { isRunning: false, status: 'FAILED', activeJob: activeJobConfig });
        broadcastSSE('exit', { code: 1, status: 'FAILED' });
      });

      return sendJSON(res, { success: true, pid: child.pid, status: 'RUNNING' });
    } catch (err) {
      activeProcess = null;
      currentJobStatus = 'FAILED';
      return sendJSON(res, { success: false, error: err.message }, 500);
    }
  }

  // 3. Stop Pipeline: POST /api/pipeline/stop
  if (pathname === '/api/pipeline/stop' && req.method === 'POST') {
    if (!activeProcess) {
      return sendJSON(res, { success: true, message: 'No pipeline running.' });
    }
    try {
      const pid = activeProcess.pid;
      if (process.platform === 'win32') {
        execSync(`taskkill /pid ${pid} /T /F`);
      } else {
        activeProcess.kill('SIGKILL');
      }
      activeProcess = null;
      currentJobStatus = 'IDLE';
      broadcastSSE('status', { isRunning: false, status: 'IDLE', activeJob: null });
      return sendJSON(res, { success: true });
    } catch (err) {
      return sendJSON(res, { success: false, error: err.message }, 500);
    }
  }

  // 4. Status Check: GET /api/pipeline/status
  if (pathname === '/api/pipeline/status') {
    return sendJSON(res, {
      isRunning: !!activeProcess,
      status: currentJobStatus,
      activeJob: activeJobConfig
    });
  }

  // 5. List Projects: GET /api/projects
  if (pathname === '/api/projects') {
    try {
      if (!fs.existsSync(OUTPUT_DIR)) {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
        return sendJSON(res, []);
      }

      const entries = fs.readdirSync(OUTPUT_DIR, { withFileTypes: true });
      const projects = [];

      for (const ent of entries) {
        if (ent.isDirectory()) {
          const projPath = path.join(OUTPUT_DIR, ent.name);
          const files = fs.readdirSync(projPath);

          const hasManhwaVideo = files.includes('FINAL_MANHWA_RECAP.mp4');
          const hasVideoRecap = files.includes('FINAL_RECAP.mp4');
          const hasMasterAudio = files.includes('master_audio.mp3') || files.includes('synced_voiceover.mp3');
          const hasScript = files.includes('master_script.txt');
          const hasOCR = files.includes('ocr_results.json');
          const hasState = files.includes('state.json');

          let videoFile = null;
          if (hasManhwaVideo) videoFile = `/api/media/${ent.name}/FINAL_MANHWA_RECAP.mp4`;
          else if (hasVideoRecap) videoFile = `/api/media/${ent.name}/FINAL_RECAP.mp4`;

          let audioFile = null;
          if (files.includes('master_audio.mp3')) audioFile = `/api/media/${ent.name}/master_audio.mp3`;
          else if (files.includes('synced_voiceover.mp3')) audioFile = `/api/media/${ent.name}/synced_voiceover.mp3`;

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
            videoUrl: videoFile,
            hasAudio: !!audioFile,
            audioUrl: audioFile,
            hasScript,
            hasOCR,
            state: stateData,
            status: stateData?.status || (videoFile ? 'COMPLETED' : 'IN_PROGRESS'),
            totalFiles: files.length,
          });
        }
      }

      projects.sort((a, b) => b.updatedAt - a.updatedAt);
      return sendJSON(res, projects);
    } catch (err) {
      return sendJSON(res, { error: err.message }, 500);
    }
  }

  // 6. Subtitles Fetch: GET /api/project/:name/subtitles
  const subMatch = pathname.match(/^\/api\/project\/([^/]+)\/subtitles$/);
  if (subMatch && req.method === 'GET') {
    const projName = decodeURIComponent(subMatch[1]);
    const projDir = path.join(OUTPUT_DIR, projName);
    if (!fs.existsSync(projDir)) return sendJSON(res, { error: 'Project not found' }, 404);

    const origSubPath = path.join(projDir, 'audio.vtt');
    let origSubContent = '';
    if (fs.existsSync(origSubPath)) {
      origSubContent = fs.readFileSync(origSubPath, 'utf8');
    }

    // Check Translated folder
    const translatedDir = path.join(projDir, 'Translated');
    const translatedAlt = path.join(projDir, 'translated');
    const targetTransDir = fs.existsSync(translatedDir) ? translatedDir : (fs.existsSync(translatedAlt) ? translatedAlt : null);

    const chunkFiles = [];
    if (targetTransDir) {
      const files = fs.readdirSync(targetTransDir).filter(f => f.endsWith('.vtt') || f.endsWith('.srt'));
      for (const f of files) {
        chunkFiles.push({
          filename: f,
          content: fs.readFileSync(path.join(targetTransDir, f), 'utf8')
        });
      }
    }

    return sendJSON(res, {
      projectName: projName,
      hasOriginal: !!origSubContent,
      originalVtt: origSubContent,
      hasTranslated: chunkFiles.length > 0,
      chunkFiles,
      translatedDir: targetTransDir || path.join(projDir, 'Translated')
    });
  }

  // 7. Subtitles Save: POST /api/project/:name/subtitles
  if (subMatch && req.method === 'POST') {
    const projName = decodeURIComponent(subMatch[1]);
    const projDir = path.join(OUTPUT_DIR, projName);
    if (!fs.existsSync(projDir)) return sendJSON(res, { error: 'Project not found' }, 404);

    const body = await parseBody(req);
    const { filename = 'audio.vtt', content } = body;

    const translatedDir = path.join(projDir, 'Translated');
    if (!fs.existsSync(translatedDir)) {
      fs.mkdirSync(translatedDir, { recursive: true });
    }

    const savePath = path.join(translatedDir, filename);
    fs.writeFileSync(savePath, content, 'utf8');

    return sendJSON(res, { success: true, savedPath: savePath });
  }

  // 8. Open Folder: POST /api/open-folder
  if (pathname === '/api/open-folder' && req.method === 'POST') {
    const body = await parseBody(req);
    const folderPath = body.path;
    if (folderPath && fs.existsSync(folderPath)) {
      if (process.platform === 'win32') {
        exec(`start "" "${folderPath}"`);
      } else if (process.platform === 'darwin') {
        exec(`open "${folderPath}"`);
      } else {
        exec(`xdg-open "${folderPath}"`);
      }
      return sendJSON(res, { success: true });
    }
    return sendJSON(res, { success: false, error: 'Path not found' }, 404);
  }

  // 9. Media Streaming: GET /api/media/*
  if (pathname.startsWith('/api/media/')) {
    const relPath = decodeURIComponent(pathname.replace('/api/media/', ''));
    const safePath = path.normalize(path.join(OUTPUT_DIR, relPath));
    if (safePath.startsWith(OUTPUT_DIR)) {
      return serveMediaFile(safePath, req, res);
    }
    res.writeHead(403);
    return res.end('Access denied');
  }

  // 10. System Status: GET /api/system
  if (pathname === '/api/system') {
    let pythonOk = false;
    let pythonVersion = '';
    try {
      pythonVersion = execSync('python --version', { encoding: 'utf8' }).trim();
      pythonOk = true;
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

    return sendJSON(res, {
      python: { ok: pythonOk, version: pythonVersion },
      ffmpeg: { ok: ffmpegOk, version: ffmpegVersion },
      env: { hasGeminiKey, hasAimlKey, envPath: ENV_FILE }
    });
  }

  // Default 404
  res.writeHead(404, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
  res.end(JSON.stringify({ error: 'Endpoint not found' }));
});

server.listen(PORT, () => {
  console.log(`[OmniDub API Server] Running on http://localhost:${PORT}`);
});
