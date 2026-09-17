import React, { useState, useEffect } from 'react';
import { 
  Sparkles, 
  Play, 
  Terminal, 
  Folder, 
  Settings, 
  Cpu, 
  Layers, 
  Zap,
  Film,
  BookOpen
} from 'lucide-react';
import { api } from './services/api';
import FeaturesSection from './components/FeaturesSection';
import StudioRunner from './components/StudioRunner';
import LiveConsole from './components/LiveConsole';
import ProjectGallery from './components/ProjectGallery';
import SystemStatus from './components/SystemStatus';

export default function App() {
  const [activeTab, setActiveTab] = useState('features'); // 'features' | 'studio' | 'console' | 'projects' | 'system'
  const [studioInitialEngine, setStudioInitialEngine] = useState('manhwa');
  const [isRunning, setIsRunning] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState('IDLE'); // 'IDLE' | 'RUNNING' | 'AWAITING_TRANSLATION' | 'COMPLETED' | 'FAILED'
  const [activeJobConfig, setActiveJobConfig] = useState(null);
  const [logs, setLogs] = useState([]);

  // Subscribe to real-time process logs & status from backend server / Electron IPC
  useEffect(() => {
    const unsub = api.subscribeLogs({
      onLog: (logData) => {
        setLogs((prev) => [...prev, logData]);
      },
      onStatus: (statusData) => {
        if (statusData.status) setPipelineStatus(statusData.status);
        if (typeof statusData.isRunning === 'boolean') setIsRunning(statusData.isRunning);
        if (statusData.activeJob) setActiveJobConfig(statusData.activeJob);
      },
      onExit: (code, status) => {
        setIsRunning(false);
        if (status) setPipelineStatus(status);
        setLogs((prev) => [
          ...prev, 
          { 
            type: code === 0 ? 'stdout' : 'stderr', 
            text: `\n[PROCESS FINISHED] Exit code: ${code} ${status === 'AWAITING_TRANSLATION' ? '⏸️ Paused for subtitle translation.' : (code === 0 ? '🎉 Completed successfully!' : '⚠️ Stopped or failed.')}\n` 
          }
        ]);
      }
    });

    return () => {
      unsub();
    };
  }, []);

  const handleLaunchStudioFromFeature = (engineType) => {
    setStudioInitialEngine(engineType);
    setActiveTab('studio');
  };

  const handleJobStarted = (config) => {
    setIsRunning(true);
    setPipelineStatus('RUNNING');
    setActiveJobConfig(config);
    setLogs([
      { type: 'stdout', text: `=========================================================================\n` },
      { type: 'stdout', text: `🚀 LAUNCHING PIPELINE: ${config.engine.toUpperCase()}\n` },
      { type: 'stdout', text: `Target Source: ${config.source}\n` },
      { type: 'stdout', text: `Timestamp: ${new Date().toLocaleTimeString()}\n` },
      { type: 'stdout', text: `=========================================================================\n\n` }
    ]);
    setActiveTab('console');
  };

  const handleStopJob = async () => {
    await api.stopPipeline();
    setIsRunning(false);
    setPipelineStatus('IDLE');
  };

  return (
    <div className="app-container">
      
      {/* Top Glassmorphic Navigation Bar */}
      <nav className="navbar">
        <div className="brand-group">
          <div className="brand-logo-icon">
            <Sparkles size={20} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="brand-title">OmniDub AI</span>
              <span className="brand-badge">Desktop Studio</span>
            </div>
          </div>
        </div>

        {/* Tab Controls */}
        <div className="nav-tabs">
          <button 
            className={`nav-tab-btn ${activeTab === 'features' ? 'active' : ''}`}
            onClick={() => setActiveTab('features')}
          >
            <Sparkles size={16} /> Features & Engines
          </button>
          <button 
            className={`nav-tab-btn ${activeTab === 'studio' ? 'active' : ''}`}
            onClick={() => setActiveTab('studio')}
          >
            <Zap size={16} /> Studio Runner
          </button>
          <button 
            className={`nav-tab-btn ${activeTab === 'console' ? 'active' : ''}`}
            onClick={() => setActiveTab('console')}
          >
            <Terminal size={16} /> Live Console
            {isRunning && (
              <span style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: '#06b6d4',
                boxShadow: '0 0 8px #06b6d4'
              }} />
            )}
          </button>
          <button 
            className={`nav-tab-btn ${activeTab === 'projects' ? 'active' : ''}`}
            onClick={() => setActiveTab('projects')}
          >
            <Folder size={16} /> Projects & Media
          </button>
          <button 
            className={`nav-tab-btn ${activeTab === 'system' ? 'active' : ''}`}
            onClick={() => setActiveTab('system')}
          >
            <Settings size={16} /> Diagnostics
          </button>
        </div>

        {/* Status Indicator */}
        <div className="header-actions">
          {pipelineStatus === 'AWAITING_TRANSLATION' ? (
            <div className="status-pill" style={{ background: 'rgba(245, 158, 11, 0.2)', borderColor: 'rgba(245, 158, 11, 0.4)', color: '#f59e0b' }}>
              <span className="status-dot" style={{ background: '#f59e0b', boxShadow: '0 0 8px #f59e0b' }} />
              ⏸️ Awaiting Translation
            </div>
          ) : isRunning ? (
            <div className="status-pill" style={{ background: 'rgba(6, 182, 212, 0.15)', borderColor: 'rgba(6, 182, 212, 0.3)', color: 'var(--accent-cyan)' }}>
              <span className="status-dot" style={{ background: '#06b6d4', boxShadow: '0 0 8px #06b6d4' }} />
              Rendering in Progress
            </div>
          ) : (
            <div className="status-pill">
              <span className="status-dot" />
              Engine Ready
            </div>
          )}
        </div>
      </nav>

      {/* Main Viewport - Kept mounted to preserve all URL and form states when switching tabs */}
      <main className="main-viewport">
        <div style={{ display: activeTab === 'features' ? 'block' : 'none' }}>
          <FeaturesSection onLaunchStudio={handleLaunchStudioFromFeature} />
        </div>

        <div style={{ display: activeTab === 'studio' ? 'block' : 'none' }}>
          <StudioRunner 
            initialEngine={studioInitialEngine}
            onJobStarted={handleJobStarted}
            isRunning={isRunning}
            onStopJob={handleStopJob}
            pipelineStatus={pipelineStatus}
            activeProjectName={activeJobConfig?.projectName}
          />
        </div>

        <div style={{ display: activeTab === 'console' ? 'block' : 'none' }}>
          <LiveConsole 
            logs={logs}
            isRunning={isRunning}
            onStopJob={handleStopJob}
            activeJobConfig={activeJobConfig}
            pipelineStatus={pipelineStatus}
          />
        </div>

        <div style={{ display: activeTab === 'projects' ? 'block' : 'none' }}>
          <ProjectGallery />
        </div>

        <div style={{ display: activeTab === 'system' ? 'block' : 'none' }}>
          <SystemStatus />
        </div>
      </main>

    </div>
  );
}
