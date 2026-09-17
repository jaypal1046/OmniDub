import React, { useState, useEffect, useRef } from 'react';
import { 
  Terminal, 
  Trash2, 
  Copy, 
  Check, 
  ArrowDown, 
  Search, 
  Square, 
  CheckCircle2, 
  Loader2, 
  AlertTriangle,
  Languages
} from 'lucide-react';

export default function LiveConsole({ logs = [], isRunning = false, onStopJob, activeJobConfig, pipelineStatus }) {
  const [filter, setFilter] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const terminalEndRef = useRef(null);

  // Auto-scroll terminal
  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollTop = terminalEndRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleCopyLogs = () => {
    const text = logs.map(l => l.text).join('');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Determine active step from logs
  let currentStep = 0;
  const fullLogString = logs.map(l => l.text).join(' ');
  if (fullLogString.includes('STEP 6') || fullLogString.includes('Step 6') || fullLogString.includes('Concatenating')) currentStep = 6;
  else if (fullLogString.includes('STEP 5') || fullLogString.includes('Step 5') || fullLogString.includes('Rendering video clips')) currentStep = 5;
  else if (fullLogString.includes('STEP 4') || fullLogString.includes('Step 4') || fullLogString.includes('Consolidating') || fullLogString.includes('Generating natural speech')) currentStep = 4;
  else if (fullLogString.includes('STEP 3') || fullLogString.includes('Step 3') || fullLogString.includes('Gemini Vision') || fullLogString.includes('Audio Separation')) currentStep = 3;
  else if (fullLogString.includes('STEP 2') || fullLogString.includes('Step 2') || fullLogString.includes('OCR') || fullLogString.includes('Transcribe')) currentStep = 2;
  else if (fullLogString.includes('STEP 1') || fullLogString.includes('Step 1') || fullLogString.includes('Downloading')) currentStep = 1;

  const manhwaSteps = [
    { num: 1, title: 'Download' },
    { num: 2, title: 'Transcribe / OCR' },
    { num: 3, title: 'Script / BGM' },
    { num: 4, title: 'Voiceover TTS' },
    { num: 5, title: 'Audio Retiming' },
    { num: 6, title: 'Final Video' },
  ];

  const filteredLogs = logs.filter(l => 
    !filter || l.text.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', height: 'calc(100vh - 160px)' }}>
      
      {/* Translation Pause Banner */}
      {pipelineStatus === 'AWAITING_TRANSLATION' && (
        <div style={{
          padding: '0.85rem 1.25rem',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(245, 158, 11, 0.15)',
          border: '1px solid rgba(245, 158, 11, 0.4)',
          color: '#fde68a',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: '0.85rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Languages size={18} color="#f59e0b" />
            <span>
              <strong>Pipeline Paused:</strong> Transcription is complete. Switch to the <strong>Studio Runner</strong> tab to edit or save your English translation before continuing to the final video!
            </span>
          </div>
        </div>
      )}

      {/* Step Tracker Bar */}
      <div className="glass-card" style={{ padding: '1rem 1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#fff' }}>Pipeline Execution Pipeline</span>
            {pipelineStatus === 'AWAITING_TRANSLATION' ? (
              <span style={{
                padding: '0.2rem 0.6rem',
                borderRadius: 'var(--radius-pill)',
                background: 'rgba(245, 158, 11, 0.2)',
                color: '#f59e0b',
                fontSize: '0.75rem',
                fontWeight: 700
              }}>
                ⏸️ Awaiting Translation
              </span>
            ) : isRunning ? (
              <span className="status-pill">
                <span className="status-dot" /> Running...
              </span>
            ) : null}
          </div>
          {activeJobConfig && (
            <div style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>
              Target: {activeJobConfig.projectName || activeJobConfig.engine}
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '0.5rem' }}>
          {manhwaSteps.map(s => {
            const isCompleted = currentStep > s.num;
            const isCurrent = currentStep === s.num && isRunning;
            return (
              <div 
                key={s.num}
                style={{
                  background: isCurrent ? 'rgba(6, 182, 212, 0.15)' : isCompleted ? 'rgba(16, 185, 129, 0.1)' : 'rgba(255, 255, 255, 0.03)',
                  border: `1px solid ${isCurrent ? 'var(--accent-cyan)' : isCompleted ? 'var(--accent-emerald)' : 'var(--border-subtle)'}`,
                  borderRadius: 'var(--radius-sm)',
                  padding: '0.5rem 0.6rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  transition: 'all 0.3s ease'
                }}
              >
                {isCompleted ? (
                  <CheckCircle2 size={14} color="#10b981" />
                ) : isCurrent ? (
                  <Loader2 size={14} color="#06b6d4" className="spinner" style={{ animation: 'spin 1s linear infinite' }} />
                ) : (
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{s.num}</span>
                )}
                <span style={{
                  fontSize: '0.75rem',
                  fontWeight: isCurrent ? 700 : 500,
                  color: isCurrent ? '#fff' : isCompleted ? '#a7f3d0' : 'var(--text-secondary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                }}>
                  {s.title}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Terminal View */}
      <div className="glass-card" style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        padding: '1rem',
        background: '#070a10',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        minHeight: 0
      }}>
        {/* Terminal Header Toolbar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingBottom: '0.75rem',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          gap: '1rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Terminal size={18} color="#06b6d4" />
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e2e8f0', fontFamily: 'var(--font-mono)' }}>
              python-output:~$
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {/* Filter Search */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              background: 'rgba(255, 255, 255, 0.05)',
              padding: '0.25rem 0.6rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)'
            }}>
              <Search size={14} color="var(--text-muted)" />
              <input 
                type="text" 
                placeholder="Filter logs..." 
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#fff',
                  fontSize: '0.75rem',
                  width: '120px'
                }}
              />
            </div>

            {/* Auto-scroll toggle */}
            <button
              onClick={() => setAutoScroll(!autoScroll)}
              className="btn-secondary"
              style={{
                padding: '0.35rem 0.65rem',
                fontSize: '0.75rem',
                background: autoScroll ? 'rgba(6, 182, 212, 0.15)' : 'transparent',
                borderColor: autoScroll ? 'var(--accent-cyan)' : 'var(--border-subtle)',
                color: autoScroll ? 'var(--accent-cyan)' : 'var(--text-secondary)'
              }}
              title="Toggle autoscroll"
            >
              <ArrowDown size={14} /> Auto-Scroll
            </button>

            {/* Copy Button */}
            <button
              onClick={handleCopyLogs}
              className="btn-secondary"
              style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
              title="Copy all logs"
            >
              {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>

            {/* Stop process button if active */}
            {isRunning && (
              <button
                onClick={onStopJob}
                className="btn-danger"
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
              >
                <Square size={14} /> Stop
              </button>
            )}
          </div>
        </div>

        {/* Streaming Logs Body */}
        <div 
          ref={terminalEndRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '1rem 0.5rem',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.82rem',
            lineHeight: 1.6,
            color: '#cbd5e1',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all'
          }}
        >
          {filteredLogs.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '1rem' }}>
              {isRunning ? 'Pipeline initializing... waiting for standard output stream...' : 'No execution logs recorded yet. Launch a pipeline in the Studio tab to stream logs.'}
            </div>
          ) : (
            filteredLogs.map((log, idx) => {
              const isError = log.type === 'stderr' || log.type === 'error' || log.text.includes('Error') || log.text.includes('Traceback');
              const isStep = log.text.includes('STEP ') || log.text.includes('Step ');
              const isSuccess = log.text.includes('🎉') || log.text.includes('Successfully') || log.text.includes('COMPLETE');
              
              let textColor = '#e2e8f0';
              if (isError) textColor = '#f87171';
              else if (isStep) textColor = '#38bdf8';
              else if (isSuccess) textColor = '#4ade80';

              return (
                <span 
                  key={idx} 
                  style={{ 
                    color: textColor,
                    fontWeight: isStep || isSuccess ? 600 : 400 
                  }}
                >
                  {log.text}
                </span>
              );
            })
          )}
        </div>
      </div>

    </div>
  );
}
