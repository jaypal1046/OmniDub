import React, { useState, useEffect } from 'react';
import { 
  Play, 
  Square, 
  Settings2, 
  FolderOpen, 
  Sparkles, 
  FileVideo, 
  Cpu, 
  Volume2, 
  Layout, 
  AlertCircle,
  HelpCircle,
  Flame,
  ArrowUpRight,
  RotateCcw,
  ListPlus,
  Layers,
  CheckCircle2,
  Clock,
  Languages,
  Trash2,
  PlayCircle
} from 'lucide-react';
import { api } from '../services/api';
import { generateProjectNameFromUrl } from '../utils/nameGenerator';
import TranslationModal from './TranslationModal';

export default function StudioRunner({ 
  initialEngine = 'manhwa', 
  onJobStarted, 
  isRunning, 
  onStopJob, 
  pipelineStatus,
  activeProjectName
}) {
  const [engine, setEngine] = useState(() => {
    try {
      return localStorage.getItem('omnidub_engine') || initialEngine;
    } catch (_) {
      return initialEngine;
    }
  });

  const [modeType, setModeType] = useState(() => {
    try {
      return localStorage.getItem('omnidub_modeType') || 'single';
    } catch (_) {
      return 'single';
    }
  });
  
  // Single mode state - persisted so tab switching never cleans the URL
  const initialUrl = 'https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1';
  const [source, setSource] = useState(() => {
    try {
      const saved = localStorage.getItem('omnidub_source');
      return (saved !== null && saved !== undefined) ? saved : initialUrl;
    } catch (_) {
      return initialUrl;
    }
  });

  const [projectName, setProjectName] = useState(() => {
    try {
      const savedName = localStorage.getItem('omnidub_projectName');
      if (savedName) return savedName;
      const savedSource = localStorage.getItem('omnidub_source') || initialUrl;
      return generateProjectNameFromUrl(savedSource);
    } catch (_) {
      return generateProjectNameFromUrl(initialUrl);
    }
  });

  const [isCustomName, setIsCustomName] = useState(() => {
    try {
      return localStorage.getItem('omnidub_isCustomName') === 'true';
    } catch (_) {
      return false;
    }
  });

  // Batch mode state
  const [batchInput, setBatchInput] = useState(() => {
    try {
      const savedBatch = localStorage.getItem('omnidub_batchInput');
      return savedBatch || "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1\nhttps://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/2";
    } catch (_) {
      return "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1\nhttps://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/2";
    }
  });
  const [batchQueue, setBatchQueue] = useState([]);
  const [batchRunningIndex, setBatchRunningIndex] = useState(-1);

  // Shared config
  const [aspect, setAspect] = useState('16:9');
  const [voice, setVoice] = useState('en-US-ChristopherNeural');
  const [workers, setWorkers] = useState(8);
  const [mode, setMode] = useState(4);
  const [burnSubtitles, setBurnSubtitles] = useState(true);
  const [force, setForce] = useState(false);
  const [customPrompt, setCustomPrompt] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Translation Modal State
  const [translatingProject, setTranslatingProject] = useState(null);

  // Persist state to localStorage so URL is never lost
  useEffect(() => {
    try {
      localStorage.setItem('omnidub_engine', engine);
      localStorage.setItem('omnidub_modeType', modeType);
      localStorage.setItem('omnidub_source', source);
      localStorage.setItem('omnidub_projectName', projectName);
      localStorage.setItem('omnidub_isCustomName', String(isCustomName));
      localStorage.setItem('omnidub_batchInput', batchInput);
    } catch (_) {}
  }, [engine, modeType, source, projectName, isCustomName, batchInput]);

  // Parse batch input into queue items
  useEffect(() => {
    if (modeType === 'batch') {
      const lines = batchInput.split('\n').map(l => l.trim()).filter(l => l.length > 0);
      const newQueue = lines.map((url, idx) => ({
        id: idx + 1,
        url,
        projectName: generateProjectNameFromUrl(url),
        status: 'QUEUED', // 'QUEUED' | 'RUNNING' | 'AWAITING_TRANSLATION' | 'COMPLETED' | 'FAILED'
      }));
      setBatchQueue(newQueue);
    }
  }, [batchInput, modeType]);

  // Update source and auto-derive project name if not manually modified
  const updateSource = (newSource) => {
    setSource(newSource);
    if (!isCustomName) {
      setProjectName(generateProjectNameFromUrl(newSource));
    }
  };

  const handleResetToAutoName = () => {
    setIsCustomName(false);
    setProjectName(generateProjectNameFromUrl(source));
  };

  const handleSelectLocalFile = async () => {
    try {
      const selected = await api.selectFile({
        isFolder: false,
        filters: engine === 'manhwa' 
          ? [{ name: 'Comics & PDFs', extensions: ['pdf', 'zip', 'cbz'] }, { name: 'All Files', extensions: ['*'] }]
          : [{ name: 'Video Files', extensions: ['mp4', 'mkv', 'webm', 'mov'] }, { name: 'All Files', extensions: ['*'] }]
      });
      if (selected) {
        updateSource(selected);
      }
    } catch (err) {
      console.error('File dialog error:', err);
    }
  };

  // Run Single Task (Stage 1 or Stage 2)
  const handleRunSingle = async (autoContinue = false) => {
    setErrorMsg('');

    if (!source || !source.trim()) {
      setErrorMsg('Please enter a valid URL or local file path.');
      return;
    }

    const config = {
      engine,
      source: source.trim(),
      projectName: projectName.trim() || undefined,
      aspect,
      voice,
      workers: Number(workers),
      mode: Number(mode),
      burnSubtitles,
      force,
      autoContinue, // false on first run so it stops after transcribe!
      customPrompt: customPrompt.trim() || undefined
    };

    const res = await api.runPipeline(config);
    if (!res.success) {
      setErrorMsg(res.error || 'Failed to start pipeline.');
    } else {
      if (onJobStarted) {
        onJobStarted(config);
      }
    }
  };

  // Run Batch Item
  const runBatchTask = async (index, autoContinue = false) => {
    if (index >= batchQueue.length) return;
    const item = batchQueue[index];
    setBatchRunningIndex(index);

    // Update queue status
    setBatchQueue(prev => prev.map((task, i) => i === index ? { ...task, status: 'RUNNING' } : task));

    const config = {
      engine,
      source: item.url,
      projectName: item.projectName,
      aspect,
      voice,
      workers: Number(workers),
      mode: Number(mode),
      burnSubtitles,
      force,
      autoContinue,
      customPrompt: customPrompt.trim() || undefined
    };

    const res = await api.runPipeline(config);
    if (res.success) {
      if (onJobStarted) onJobStarted(config);
    } else {
      setBatchQueue(prev => prev.map((task, i) => i === index ? { ...task, status: 'FAILED' } : task));
      setErrorMsg(`Failed on task ${index + 1}: ${res.error}`);
    }
  };

  // Listen for pipelineStatus updates to update batch queue
  useEffect(() => {
    if (pipelineStatus === 'AWAITING_TRANSLATION' && batchRunningIndex >= 0) {
      setBatchQueue(prev => prev.map((task, i) => i === batchRunningIndex ? { ...task, status: 'AWAITING_TRANSLATION' } : task));
    } else if (pipelineStatus === 'COMPLETED' && batchRunningIndex >= 0) {
      setBatchQueue(prev => prev.map((task, i) => i === batchRunningIndex ? { ...task, status: 'COMPLETED' } : task));
    }
  }, [pipelineStatus, batchRunningIndex]);

  const isPausedAwaitingTranslation = pipelineStatus === 'AWAITING_TRANSLATION';

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      {/* Studio Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff' }}>
            Pipeline Studio & Launchpad
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
            Configure recap generation, run batch URLs, and manage subtitle translation pauses.
          </p>
        </div>

        {/* Engine Switcher */}
        <div className="nav-tabs">
          <button 
            type="button" 
            className={`nav-tab-btn ${engine === 'manhwa' ? 'active' : ''}`}
            onClick={() => setEngine('manhwa')}
          >
            🎨 Manhwa 16:9
          </button>
          <button 
            type="button" 
            className={`nav-tab-btn ${engine === 'retimed' ? 'active' : ''}`}
            onClick={() => setEngine('retimed')}
          >
            🎥 Retimed Natural
          </button>
          <button 
            type="button" 
            className={`nav-tab-btn ${engine === 'standard' ? 'active' : ''}`}
            onClick={() => setEngine('standard')}
          >
            ⚡ Fast Fixed
          </button>
        </div>
      </div>

      {/* Mode Selector (Single vs Batch) */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
        <button
          type="button"
          className={`nav-tab-btn ${modeType === 'single' ? 'active' : ''}`}
          onClick={() => setModeType('single')}
          style={{ padding: '0.5rem 1.25rem' }}
        >
          Single URL / File Mode
        </button>
        <button
          type="button"
          className={`nav-tab-btn ${modeType === 'batch' ? 'active' : ''}`}
          onClick={() => setModeType('batch')}
          style={{ padding: '0.5rem 1.25rem' }}
        >
          <ListPlus size={16} />
          Multiple URLs / Batch Mode ({batchQueue.length})
        </button>
      </div>

      {/* Awaiting Translation Alert Banner */}
      {isPausedAwaitingTranslation && (
        <div style={{
          padding: '1.25rem 1.5rem',
          borderRadius: 'var(--radius-md)',
          background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(139, 92, 246, 0.2))',
          border: '1px solid rgba(245, 158, 11, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <div style={{
              width: '40px',
              height: '40px',
              borderRadius: '50%',
              background: 'rgba(245, 158, 11, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#f59e0b'
            }}>
              <Languages size={22} />
            </div>
            <div>
              <div style={{ fontWeight: 800, color: '#fff', fontSize: '1rem' }}>
                ⏸️ Step 2/3 Finished: Pipeline Paused for English Translation!
              </div>
              <div style={{ color: '#fde68a', fontSize: '0.85rem' }}>
                Transcription complete. Add or review English translations for project: <strong>{activeProjectName || projectName}</strong>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              className="btn-secondary"
              onClick={() => setTranslatingProject(activeProjectName || projectName)}
              style={{ padding: '0.6rem 1.2rem', borderColor: '#f59e0b', color: '#fff' }}
            >
              <Languages size={16} />
              Open Translation Editor
            </button>
            <button
              className="btn-primary"
              onClick={() => handleRunSingle(true)}
              style={{ padding: '0.6rem 1.4rem' }}
            >
              <Play size={16} />
              Continue to Final Video (Step 4)
            </button>
          </div>
        </div>
      )}

      {errorMsg && (
        <div style={{
          padding: '0.85rem 1.25rem',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(244, 63, 94, 0.15)',
          border: '1px solid rgba(244, 63, 94, 0.3)',
          color: '#fda4af',
          fontSize: '0.85rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem'
        }}>
          <AlertCircle size={18} color="#f43f5e" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Main Form Container */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        
        {/* MODE 1: SINGLE URL */}
        {modeType === 'single' ? (
          <>
            {/* Source Input */}
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">
                <span>
                  {engine === 'manhwa' ? 'Comic Chapter URL or Local PDF / Image Folder' : 'Video Source URL or Local MP4 / MKV File'}
                </span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Supports AsuraScans, Bilibili, YouTube, Douyin, local files
                </span>
              </label>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <input 
                  type="text" 
                  className="input-text"
                  placeholder={engine === 'manhwa' ? 'https://asurascans.com/... or C:/novel/chapter1.pdf' : 'https://www.bilibili.com/video/... or C:/videos/clip.mp4'}
                  value={source}
                  onChange={(e) => updateSource(e.target.value)}
                  required
                />
                <button 
                  type="button" 
                  className="btn-secondary"
                  onClick={handleSelectLocalFile}
                  title="Browse local file"
                  style={{ whiteSpace: 'nowrap' }}
                >
                  <FolderOpen size={16} />
                  Browse...
                </button>
              </div>
            </div>

            {/* Project Name & Voice Narrator */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
              
              <div className="form-group" style={{ margin: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <label className="form-label" style={{ margin: 0 }}>
                    <span>Project Folder Name</span>
                  </label>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    {isCustomName ? (
                      <button
                        type="button"
                        onClick={handleResetToAutoName}
                        title="Click to reset and sync name from URL"
                        style={{
                          background: 'rgba(139, 92, 246, 0.15)',
                          border: '1px solid rgba(139, 92, 246, 0.3)',
                          color: 'var(--accent-purple)',
                          fontSize: '0.7rem',
                          padding: '0.15rem 0.5rem',
                          borderRadius: 'var(--radius-pill)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem'
                        }}
                      >
                        <RotateCcw size={10} /> Reset to auto
                      </button>
                    ) : (
                      <span style={{
                        background: 'rgba(6, 182, 212, 0.15)',
                        border: '1px solid rgba(6, 182, 212, 0.3)',
                        color: 'var(--accent-cyan)',
                        fontSize: '0.7rem',
                        padding: '0.15rem 0.5rem',
                        borderRadius: 'var(--radius-pill)',
                        fontWeight: 600,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.25rem'
                      }}>
                        ⚡ Auto from URL
                      </span>
                    )}
                  </div>
                </div>

                <input 
                  type="text" 
                  className="input-text"
                  placeholder="e.g. my_chapter1_recap"
                  value={projectName}
                  onChange={(e) => {
                    setProjectName(e.target.value);
                    setIsCustomName(true);
                  }}
                />
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  {isCustomName ? 'Customized manually. Click "Reset to auto" to re-derive from URL.' : 'Generated automatically from the input URL. You can edit this anytime.'}
                </span>
              </div>

              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label">
                  <span>AI Narrator Voice (Edge-TTS)</span>
                </label>
                <select 
                  className="input-select"
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                >
                  <option value="en-US-ChristopherNeural">Christopher (Male - Deep & Dramatic)</option>
                  <option value="en-US-AriaNeural">Aria (Female - Crisp & Expressive)</option>
                  <option value="en-US-GuyNeural">Guy (Male - Conversational & Natural)</option>
                  <option value="en-US-JennyNeural">Jenny (Female - Clear & Friendly)</option>
                  <option value="en-US-EricNeural">Eric (Male - Strong Action Tone)</option>
                  <option value="en-US-MichelleNeural">Michelle (Female - Professional Storyteller)</option>
                </select>
              </div>

            </div>
          </>
        ) : (
          /* MODE 2: MULTI-URL BATCH QUEUE */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">
                <span>Enter Multiple URLs (One URL per line)</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Each URL automatically derives its own project folder name
                </span>
              </label>
              <textarea
                className="input-textarea"
                rows={4}
                value={batchInput}
                onChange={(e) => setBatchInput(e.target.value)}
                placeholder="https://asurascans.com/.../chapter/1&#10;https://asurascans.com/.../chapter/2&#10;https://asurascans.com/.../chapter/3"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}
              />
            </div>

            {/* Batch Queue Table */}
            <div style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              overflow: 'hidden'
            }}>
              <div style={{
                padding: '0.75rem 1rem',
                background: 'rgba(255, 255, 255, 0.04)',
                borderBottom: '1px solid var(--border-subtle)',
                fontSize: '0.8rem',
                fontWeight: 700,
                color: 'var(--text-secondary)',
                display: 'grid',
                gridTemplateColumns: '40px 1fr 220px 140px 120px',
                gap: '1rem',
                alignItems: 'center'
              }}>
                <span>#</span>
                <span>Source URL</span>
                <span>Derived Project Name</span>
                <span>Status</span>
                <span style={{ textAlign: 'right' }}>Actions</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', maxHeight: '300px', overflowY: 'auto' }}>
                {batchQueue.map((item, idx) => (
                  <div 
                    key={idx}
                    style={{
                      padding: '0.75rem 1rem',
                      borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                      display: 'grid',
                      gridTemplateColumns: '40px 1fr 220px 140px 120px',
                      gap: '1rem',
                      alignItems: 'center',
                      fontSize: '0.85rem'
                    }}
                  >
                    <span style={{ color: 'var(--text-muted)', fontWeight: 700 }}>{idx + 1}</span>
                    <span style={{ color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.url}>
                      {item.url}
                    </span>
                    <input 
                      type="text" 
                      className="input-text"
                      value={item.projectName}
                      onChange={(e) => {
                        const newName = e.target.value;
                        setBatchQueue(prev => prev.map((t, i) => i === idx ? { ...t, projectName: newName } : t));
                      }}
                      style={{ padding: '0.35rem 0.6rem', fontSize: '0.8rem' }}
                    />
                    <div>
                      {item.status === 'RUNNING' && (
                        <span className="status-pill" style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}>
                          <span className="status-dot" /> Running
                        </span>
                      )}
                      {item.status === 'AWAITING_TRANSLATION' && (
                        <span style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: 'var(--radius-pill)',
                          background: 'rgba(245, 158, 11, 0.2)',
                          color: '#f59e0b',
                          fontSize: '0.7rem',
                          fontWeight: 700
                        }}>
                          ⏸️ Paused (Translate)
                        </span>
                      )}
                      {item.status === 'COMPLETED' && (
                        <span style={{ color: 'var(--accent-emerald)', fontSize: '0.75rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <CheckCircle2 size={13} /> Completed
                        </span>
                      )}
                      {item.status === 'QUEUED' && (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Queued</span>
                      )}
                      {item.status === 'FAILED' && (
                        <span style={{ color: 'var(--accent-rose)', fontSize: '0.75rem' }}>Failed</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                      {item.status === 'AWAITING_TRANSLATION' ? (
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => setTranslatingProject(item.projectName)}
                          style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
                          title="Translate subtitles"
                        >
                          <Languages size={13} />
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => runBatchTask(idx, item.status === 'AWAITING_TRANSLATION')}
                        disabled={isRunning}
                        style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
                        title="Run this task"
                      >
                        <Play size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Engine-Specific Parameters */}
        {engine === 'manhwa' ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
            
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">
                <span>Video Aspect Ratio</span>
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <button
                  type="button"
                  className={`btn-secondary ${aspect === '16:9' ? 'active' : ''}`}
                  onClick={() => setAspect('16:9')}
                  style={{
                    borderColor: aspect === '16:9' ? 'var(--accent-cyan)' : 'var(--border-subtle)',
                    background: aspect === '16:9' ? 'rgba(6, 182, 212, 0.15)' : 'transparent',
                    color: aspect === '16:9' ? '#fff' : 'var(--text-secondary)'
                  }}
                >
                  📺 16:9 YouTube Landscape
                </button>
                <button
                  type="button"
                  className={`btn-secondary ${aspect === '9:16' ? 'active' : ''}`}
                  onClick={() => setAspect('9:16')}
                  style={{
                    borderColor: aspect === '9:16' ? 'var(--accent-cyan)' : 'var(--border-subtle)',
                    background: aspect === '9:16' ? 'rgba(6, 182, 212, 0.15)' : 'transparent',
                    color: aspect === '9:16' ? '#fff' : 'var(--text-secondary)'
                  }}
                >
                  📱 9:16 TikTok / Shorts
                </button>
              </div>
            </div>

            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">
                <span>Parallel Worker Threads</span>
                <span style={{ color: 'var(--accent-cyan)', fontWeight: 700 }}>{workers} Workers</span>
              </label>
              <input 
                type="range" 
                min="2" 
                max="16" 
                step="2"
                value={workers} 
                onChange={(e) => setWorkers(e.target.value)}
                style={{ width: '100%', accentColor: '#06b6d4', marginTop: '0.5rem' }}
              />
            </div>

          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
            
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">
                <span>Output Merge Mode</span>
              </label>
              <select 
                className="input-select"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="4">Mode 4: Voiceover + Background Music + Burned Subtitles (Full Production)</option>
                <option value="3">Mode 3: Voiceover + Burned Subtitles (No BGM)</option>
                <option value="2">Mode 2: Voiceover + Original Audio Mix</option>
                <option value="1">Mode 1: Voiceover Track Only</option>
              </select>
            </div>

            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">
                <span>Subtitle Settings</span>
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.4rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', color: '#fff' }}>
                  <input 
                    type="checkbox" 
                    checked={burnSubtitles} 
                    onChange={(e) => setBurnSubtitles(e.target.checked)}
                    style={{ accentColor: '#06b6d4', width: '18px', height: '18px' }}
                  />
                  <span style={{ fontSize: '0.85rem' }}>Burn formatted subtitles onto video frames</span>
                </label>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  ⏸️ Pipeline automatically stops after Whisper transcription so you can review/translate subtitles before final rendering.
                </span>
              </div>
            </div>

          </div>
        )}

        {/* Custom AI Prompt (Optional) */}
        {engine === 'manhwa' && (
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">
              <span>Custom Gemini Vision AI Directives (Optional)</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Guides story tone & narrator personality</span>
            </label>
            <input 
              type="text" 
              className="input-text"
              placeholder="e.g. Focus on high suspense, describe sword techniques, emphasize main character emotional conflict"
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
            />
          </div>
        )}

        {/* Advanced Toggles */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', paddingTop: '0.5rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            <input 
              type="checkbox" 
              checked={force} 
              onChange={(e) => setForce(e.target.checked)}
              style={{ accentColor: '#06b6d4' }}
            />
            <span>Force Re-run all steps (Bypass cached transcription/slices)</span>
          </label>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Output directory: <code style={{ color: 'var(--accent-cyan)' }}>output/{modeType === 'single' ? (projectName || '<project_name>') : '[each_task]'}</code>
          </div>

          <div style={{ display: 'flex', gap: '1rem' }}>
            {isRunning ? (
              <button 
                type="button" 
                className="btn-danger" 
                onClick={onStopJob}
              >
                <Square size={16} />
                Stop Execution
              </button>
            ) : modeType === 'single' ? (
              <button 
                type="button" 
                className="btn-primary"
                onClick={() => handleRunSingle(false)}
                style={{ padding: '0.85rem 2rem', fontSize: '1rem' }}
              >
                <Play size={18} />
                Start Generation Pipeline
              </button>
            ) : (
              <button 
                type="button" 
                className="btn-primary"
                onClick={() => runBatchTask(0, false)}
                style={{ padding: '0.85rem 2rem', fontSize: '1rem' }}
              >
                <Play size={18} />
                Start Batch Queue ({batchQueue.length} URLs)
              </button>
            )}
          </div>
        </div>

      </div>

      {/* Translation Modal */}
      {translatingProject && (
        <TranslationModal
          projectName={translatingProject}
          onClose={() => setTranslatingProject(null)}
          onContinuePipeline={() => {
            setTranslatingProject(null);
            handleRunSingle(true);
          }}
        />
      )}

    </div>
  );
}
