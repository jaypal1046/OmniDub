import React, { useState, useEffect } from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  Key, 
  Save, 
  Terminal, 
  Film, 
  Sparkles, 
  RefreshCw,
  ShieldCheck,
  AlertCircle
} from 'lucide-react';
import { api } from '../services/api';

export default function SystemStatus() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [geminiKey, setGeminiKey] = useState('');
  const [aimlKey, setAimlKey] = useState('');
  const [savedSuccess, setSavedSuccess] = useState(false);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const data = await api.getSystemStatus();
      setStatus(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleSaveKeys = async (e) => {
    e.preventDefault();
    const toSave = {};
    if (geminiKey.trim()) toSave.GEMINI_API_KEY = geminiKey.trim();
    if (aimlKey.trim()) toSave.AIMLAPI = aimlKey.trim();

    if (Object.keys(toSave).length > 0) {
      await api.saveEnv(toSave);
      setSavedSuccess(true);
      fetchStatus();
      setTimeout(() => setSavedSuccess(false), 2500);
    }
  };

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '850px' }}>
      
      <div>
        <h2 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff' }}>
          System Health & Environment Diagnostics
        </h2>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
          Verify runtime toolchains (Python, FFmpeg) and configure AI Vision API keys.
        </p>
      </div>

      {/* Dependency Status Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
        
        {/* Python */}
        <div className="glass-card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Terminal size={18} color="var(--accent-cyan)" />
              <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>Python Runtime</span>
            </div>
            {status?.python?.ok ? (
              <CheckCircle2 size={18} color="#10b981" />
            ) : (
              <XCircle size={18} color="#f43f5e" />
            )}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            {status?.python?.ok ? status.python.version : 'Python not found in system PATH'}
          </div>
        </div>

        {/* FFmpeg */}
        <div className="glass-card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Film size={18} color="var(--accent-purple)" />
              <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>FFmpeg Video Engine</span>
            </div>
            {status?.ffmpeg?.ok ? (
              <CheckCircle2 size={18} color="#10b981" />
            ) : (
              <XCircle size={18} color="#f43f5e" />
            )}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {status?.ffmpeg?.ok ? status.ffmpeg.version : 'FFmpeg not detected. Required for video stitching.'}
          </div>
        </div>

        {/* Gemini Vision API Key */}
        <div className="glass-card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Sparkles size={18} color="var(--accent-amber)" />
              <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>Gemini Vision AI</span>
            </div>
            {status?.env?.hasGeminiKey ? (
              <CheckCircle2 size={18} color="#10b981" />
            ) : (
              <AlertCircle size={18} color="#f59e0b" />
            )}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            {status?.env?.hasGeminiKey ? 'API Key Active in .env' : 'No Gemini key detected'}
          </div>
        </div>

      </div>

      {/* API Key Management */}
      <div className="glass-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1.25rem' }}>
          <Key size={20} color="var(--accent-cyan)" />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fff' }}>
            Configure Vision & Transcription Keys (.env)
          </h3>
        </div>

        <form onSubmit={handleSaveKeys} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">
              <span>GEMINI_API_KEY</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Required for Manhwa comic page visual scripting</span>
            </label>
            <input 
              type="password" 
              className="input-text"
              placeholder="Paste updated GEMINI_API_KEY..."
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
            />
          </div>

          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">
              <span>AIMLAPI (Optional Whisper/LLM Key)</span>
            </label>
            <input 
              type="password" 
              className="input-text"
              placeholder="Paste updated AIMLAPI key..."
              value={aimlKey}
              onChange={(e) => setAimlKey(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '0.5rem' }}>
            {savedSuccess ? (
              <span style={{ color: 'var(--accent-emerald)', fontSize: '0.85rem', fontWeight: 600 }}>
                ✓ Keys updated and saved to .env successfully!
              </span>
            ) : <span />}

            <button type="submit" className="btn-primary" style={{ padding: '0.6rem 1.4rem' }}>
              <Save size={16} /> Save Changes
            </button>
          </div>
        </form>
      </div>

    </div>
  );
}
