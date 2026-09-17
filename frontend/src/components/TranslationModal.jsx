import React, { useState, useEffect } from 'react';
import { 
  X, 
  Languages, 
  Save, 
  Play, 
  CheckCircle2, 
  FolderOpen, 
  AlertTriangle, 
  FileText,
  Copy
} from 'lucide-react';
import { api } from '../services/api';

export default function TranslationModal({ projectName, onClose, onContinuePipeline }) {
  const [loading, setLoading] = useState(true);
  const [subData, setSubData] = useState(null);
  const [activeFile, setActiveFile] = useState('audio.vtt');
  const [content, setContent] = useState('');
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!projectName) return;
    setLoading(true);
    api.getSubtitles(projectName).then(res => {
      setSubData(res);
      if (res.chunkFiles && res.chunkFiles.length > 0) {
        setActiveFile(res.chunkFiles[0].filename);
        setContent(res.chunkFiles[0].content);
      } else if (res.originalVtt) {
        setActiveFile('audio.vtt');
        setContent(res.originalVtt);
      }
      setLoading(false);
    });
  }, [projectName]);

  const handleSelectFile = (file) => {
    setActiveFile(file.filename);
    setContent(file.content);
  };

  const handleSave = async () => {
    setSaving(true);
    const res = await api.saveSubtitles(projectName, activeFile, content);
    setSaving(false);
    if (res.success) {
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 2500);
    } else {
      alert('Failed to save subtitles: ' + (res.error || 'Unknown error'));
    }
  };

  const handleOpenFolder = () => {
    if (subData?.translatedDir) {
      api.openPath(subData.translatedDir);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(5, 8, 15, 0.85)',
      backdropFilter: 'blur(10px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '2rem'
    }}>
      <div className="glass-card" style={{
        width: '950px',
        maxWidth: '95vw',
        height: '85vh',
        display: 'flex',
        flexDirection: 'column',
        padding: '1.75rem',
        background: '#0c101c',
        border: '1px solid rgba(6, 182, 212, 0.3)',
        boxShadow: '0 25px 60px rgba(0, 0, 0, 0.8)'
      }}>
        
        {/* Modal Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: 'var(--radius-md)',
              background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-purple))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff'
            }}>
              <Languages size={20} />
            </div>
            <div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>
                Translate Subtitles to English
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Project: <code style={{ color: 'var(--accent-cyan)' }}>{projectName}</code> (Paused after transcription)
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button 
              className="btn-secondary" 
              onClick={handleOpenFolder}
              style={{ fontSize: '0.8rem', padding: '0.45rem 0.85rem' }}
              title="Open Translated folder in Windows Explorer"
            >
              <FolderOpen size={15} /> Open Translated/ Folder
            </button>
            <button 
              onClick={onClose}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                padding: '0.4rem',
                borderRadius: 'var(--radius-sm)'
              }}
            >
              <X size={22} />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '260px 1fr', gap: '1.25rem', padding: '1.25rem 0', minHeight: 0 }}>
          
          {/* File selector & original preview */}
          <div style={{
            background: 'rgba(255, 255, 255, 0.02)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
            padding: '1rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem'
          }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Subtitle Files
            </div>

            {loading ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading subtitles...</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {subData?.chunkFiles && subData.chunkFiles.length > 0 ? (
                  subData.chunkFiles.map(f => (
                    <button
                      key={f.filename}
                      onClick={() => handleSelectFile(f)}
                      style={{
                        padding: '0.6rem 0.8rem',
                        borderRadius: 'var(--radius-sm)',
                        background: activeFile === f.filename ? 'rgba(6, 182, 212, 0.2)' : 'transparent',
                        border: `1px solid ${activeFile === f.filename ? 'var(--accent-cyan)' : 'transparent'}`,
                        color: activeFile === f.filename ? '#fff' : 'var(--text-secondary)',
                        textAlign: 'left',
                        fontSize: '0.8rem',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem'
                      }}
                    >
                      <FileText size={14} color="#06b6d4" />
                      {f.filename}
                    </button>
                  ))
                ) : (
                  <button
                    onClick={() => {
                      setActiveFile('audio.vtt');
                      setContent(subData?.originalVtt || '');
                    }}
                    style={{
                      padding: '0.6rem 0.8rem',
                      borderRadius: 'var(--radius-sm)',
                      background: 'rgba(6, 182, 212, 0.2)',
                      border: '1px solid var(--accent-cyan)',
                      color: '#fff',
                      textAlign: 'left',
                      fontSize: '0.8rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem'
                    }}
                  >
                    <FileText size={14} color="#06b6d4" />
                    audio.vtt (Full)
                  </button>
                )}
              </div>
            )}

            <div style={{ marginTop: 'auto', padding: '0.75rem', background: 'rgba(6, 182, 212, 0.08)', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              💡 <strong>Tip:</strong> Keep the timestamp format <code style={{ color: 'var(--accent-cyan)' }}>00:00.000 --&gt; 00:05.000</code> and replace the non-English dialogue lines with your English translation.
            </div>
          </div>

          {/* Subtitle Editor Textarea */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e2e8f0' }}>
                Editing: <code style={{ color: 'var(--accent-cyan)' }}>Translated/{activeFile}</code>
              </span>
              {savedSuccess && (
                <span style={{ color: 'var(--accent-emerald)', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <CheckCircle2 size={14} /> Saved successfully!
                </span>
              )}
            </div>

            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              style={{
                flex: 1,
                background: '#07090e',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '1rem',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.85rem',
                lineHeight: 1.6,
                color: '#e2e8f0',
                outline: 'none',
                resize: 'none',
              }}
              placeholder="Paste or edit your translated subtitles here..."
            />
          </div>

        </div>

        {/* Modal Footer Controls */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            After translating, save your file and click "Continue Pipeline" to generate speech and render the final recap video.
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={handleSave}
              disabled={saving}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <Save size={16} />
              {saving ? 'Saving...' : 'Save Subtitle Translation'}
            </button>

            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                handleSave().then(() => {
                  if (onContinuePipeline) onContinuePipeline();
                });
              }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.7rem 1.6rem' }}
            >
              <Play size={16} />
              Continue Pipeline (Render Video)
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
