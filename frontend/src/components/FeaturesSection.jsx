import React, { useState } from 'react';
import { 
  Sparkles, 
  Film, 
  BookOpen, 
  Layers, 
  Cpu, 
  Zap, 
  Volume2, 
  CheckCircle2, 
  Sliders, 
  Maximize2, 
  ShieldCheck, 
  Clock, 
  Play, 
  Pause,
  ArrowRight,
  Tv,
  Smartphone
} from 'lucide-react';

export default function FeaturesSection({ onLaunchStudio }) {
  const [activeEngine, setActiveEngine] = useState('manhwa');
  const [playingVoice, setPlayingVoice] = useState(null);

  const voices = [
    { id: 'en-US-ChristopherNeural', name: 'Christopher (Male)', style: 'Deep, Cinematic & Dramatic Storyteller' },
    { id: 'en-US-AriaNeural', name: 'Aria (Female)', style: 'Expressive, Crisp & Engaging Narration' },
    { id: 'en-US-GuyNeural', name: 'Guy (Male)', style: 'Natural, Casual & Conversational' },
    { id: 'en-US-JennyNeural', name: 'Jenny (Female)', style: 'Clear, Warm & Friendly Voice' },
    { id: 'en-US-EricNeural', name: 'Eric (Male)', style: 'Authoritative, Resonant Action Tone' },
    { id: 'en-US-MichelleNeural', name: 'Michelle (Female)', style: 'Polished, Commercial Grade' },
  ];

  const handleTestVoice = (voiceId) => {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      if (playingVoice === voiceId) {
        setPlayingVoice(null);
        return;
      }
      setPlayingVoice(voiceId);
      const text = `Greetings! I am ${voiceId.split('-')[2].replace('Neural', '')}. I will narrate your comic and anime recap videos with high emotional delivery and precise timing.`;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.onend = () => setPlayingVoice(null);
      utterance.onerror = () => setPlayingVoice(null);
      window.speechSynthesis.speak(utterance);
    }
  };

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
      
      {/* Hero Banner */}
      <div style={{
        position: 'relative',
        borderRadius: 'var(--radius-xl)',
        padding: '3.5rem 3rem',
        background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.12) 0%, rgba(139, 92, 246, 0.15) 50%, rgba(10, 13, 20, 0.9) 100%)',
        border: '1px solid rgba(6, 182, 212, 0.25)',
        overflow: 'hidden',
        boxShadow: '0 20px 50px rgba(0, 0, 0, 0.5)'
      }}>
        <div style={{
          position: 'absolute',
          top: '-20%',
          right: '-5%',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(139, 92, 246, 0.2) 0%, transparent 70%)',
          filter: 'blur(40px)',
          pointerEvents: 'none'
        }} />

        <div style={{ maxWidth: '850px', position: 'relative', zIndex: 2 }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.35rem 0.85rem',
            borderRadius: 'var(--radius-pill)',
            background: 'rgba(6, 182, 212, 0.15)',
            border: '1px solid rgba(6, 182, 212, 0.3)',
            color: 'var(--accent-cyan)',
            fontSize: '0.8rem',
            fontWeight: 700,
            marginBottom: '1.25rem',
            textTransform: 'uppercase',
            letterSpacing: '0.05em'
          }}>
            <Sparkles size={14} />
            Next-Gen AI Video Production Engine
          </div>

          <h1 style={{
            fontSize: '2.8rem',
            fontWeight: 800,
            lineHeight: 1.15,
            marginBottom: '1rem',
            letterSpacing: '-0.02em',
            background: 'linear-gradient(135deg, #ffffff 30%, #a5f3fc 70%, #c4b5fd 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>
            Automated Comic & Video Recaps Built for YouTube Creators
          </h1>

          <p style={{
            fontSize: '1.1rem',
            color: 'var(--text-secondary)',
            lineHeight: 1.6,
            marginBottom: '2rem'
          }}>
            Turn vertical webtoons, manga PDFs, and foreign videos into cinematic 16:9 YouTube Recaps with OpenCV panel isolation, page-level Gemini Vision storytelling, and dynamic Ken Burns animations.
          </p>

          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <button 
              className="btn-primary" 
              onClick={() => onLaunchStudio && onLaunchStudio('manhwa')}
              style={{ padding: '0.85rem 1.8rem', fontSize: '1rem' }}
            >
              <Zap size={18} />
              Launch Manhwa Studio
            </button>
            <button 
              className="btn-secondary"
              onClick={() => onLaunchStudio && onLaunchStudio('retimed')}
              style={{ padding: '0.85rem 1.6rem', fontSize: '1rem' }}
            >
              <Film size={18} />
              Open Video Redubber
            </button>
          </div>
        </div>
      </div>

      {/* Engine Selection Showcase */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fff' }}>Core Production Engines</h2>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
              Choose an engine architecture to explore features, mechanics, and technical advantages.
            </p>
          </div>

          {/* Engine Tabs */}
          <div className="nav-tabs">
            <button 
              className={`nav-tab-btn ${activeEngine === 'manhwa' ? 'active' : ''}`}
              onClick={() => setActiveEngine('manhwa')}
            >
              <BookOpen size={16} />
              Manhwa 16:9 Recap
            </button>
            <button 
              className={`nav-tab-btn ${activeEngine === 'retimed' ? 'active' : ''}`}
              onClick={() => setActiveEngine('retimed')}
            >
              <Film size={16} />
              Retimed Natural Speech
            </button>
            <button 
              className={`nav-tab-btn ${activeEngine === 'standard' ? 'active' : ''}`}
              onClick={() => setActiveEngine('standard')}
            >
              <Clock size={16} />
              Fast Fixed Duration
            </button>
          </div>
        </div>

        {/* Engine 1: Manhwa Recap Engine */}
        {activeEngine === 'manhwa' && (
          <div className="fade-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem' }}>
            
            <div className="glass-card" style={{ position: 'relative', overflow: 'hidden' }}>
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(6, 182, 212, 0.15)',
                color: 'var(--accent-cyan)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                OPENCV VISION PIPELINE
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                Smart Comic Panel Isolation
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                Uses <code style={{ color: 'var(--accent-cyan)', background: 'rgba(0,0,0,0.3)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>cv2.findContours</code> to detect natural drawn panel boxes instead of blind fixed height cuts. Automatically crops out pure white (<code style={{ color: 'var(--accent-cyan)' }}>RGB &gt; 240</code>) and dark margins.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#06b6d4" /> Natural panel edge preservation
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#06b6d4" /> Automatic margin & border cleaning
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#06b6d4" /> Multi-panel chapter support
                </div>
              </div>
            </div>

            <div className="glass-card">
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(139, 92, 246, 0.15)',
                color: 'var(--accent-purple)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                20X FASTER AI SCRIPTING
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                Page-Level Gemini Vision AI
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                Eliminates API rate-limit bottlenecks by grouping sliced panels into parent chapter pages. Sends only <strong>38 main page images</strong> to Gemini Vision AI instead of 800+ fragmented slices!
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#8b5cf6" /> 0% rate limit stall guarantee
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#8b5cf6" /> Context-rich whole page narrative flow
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#8b5cf6" /> OCR speech bubble correlation
                </div>
              </div>
            </div>

            <div className="glass-card">
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(16, 185, 129, 0.15)',
                color: 'var(--accent-emerald)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                CINEMATIC CANVAS & RENDERING
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                16:9 YouTube & 9:16 Shorts
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                Renders high-definition <code style={{ color: 'var(--accent-emerald)' }}>1920x1080</code> YouTube landscape canvas with smooth Gaussian blurred background filling, or switch to <code style={{ color: 'var(--accent-emerald)' }}>1080x1920</code> for TikTok/Shorts.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#10b981" /> Blurred canvas background fill
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#10b981" /> Dynamic Ken Burns pan & zoom motions
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#10b981" /> 8-Worker parallel rendering
                </div>
              </div>
            </div>

          </div>
        )}

        {/* Engine 2: Retimed Natural Speech */}
        {activeEngine === 'retimed' && (
          <div className="fade-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem' }}>
            <div className="glass-card">
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(245, 158, 11, 0.15)',
                color: 'var(--accent-amber)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                NATURAL SPEECH CADENCE
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                Dynamic Audio Retiming
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                No more rushed, robotically accelerated voices. Retimes video footage dynamically to allow English narrators to speak comfortably at 100% natural conversational tempo.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#f59e0b" /> Smooth frame pauses during speech
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#f59e0b" /> Relaxed, engaging voiceover speed
                </div>
              </div>
            </div>

            <div className="glass-card">
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(6, 182, 212, 0.15)',
                color: 'var(--accent-cyan)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                AUDIO SEPARATION & BGM
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                Demucs AI Music Isolation
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                Uses Deep Neural Demucs to separate background music and sound effects from dialogue. Re-mixes ambient BGM cleanly under your new English narration.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#06b6d4" /> Clean vocal removal
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#06b6d4" /> Configurable BGM ducking volume
                </div>
              </div>
            </div>

            <div className="glass-card">
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(139, 92, 246, 0.15)',
                color: 'var(--accent-purple)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                MULTI-MODE MERGING
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                4 Flexible Output Modes
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                Generate final recap video matching your workflow: Mode 1 (Voiceover only), Mode 2 (Original + Voiceover), Mode 3 (Burned Subtitles), Mode 4 (Voice + BGM + Subtitles).
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#8b5cf6" /> Crisp burned-in stylized subtitles
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} color="#8b5cf6" /> Chunked subtitle translation support
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Engine 3: Standard Fixed Duration */}
        {activeEngine === 'standard' && (
          <div className="fade-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem' }}>
            <div className="glass-card">
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(16, 185, 129, 0.15)',
                color: 'var(--accent-emerald)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                FRAME PRESERVATION
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                Exact Original Duration
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                Perfect for quick dubs where the video runtime must remain exactly identical to the original file.
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                <CheckCircle2 size={16} color="#10b981" /> Zero frame stretching or retiming
              </div>
            </div>

            <div className="glass-card">
              <div style={{
                display: 'inline-flex',
                padding: '0.4rem 0.8rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(6, 182, 212, 0.15)',
                color: 'var(--accent-cyan)',
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: '1rem'
              }}>
                ULTRA FAST
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', color: '#fff' }}>
                Stream-Copy Video Muxing
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
                Directly copies the video stream without slow re-encoding when subtitles are not burned, completing video creation in seconds.
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#e2e8f0', fontSize: '0.85rem' }}>
                <CheckCircle2 size={16} color="#06b6d4" /> Blazing fast rendering speeds
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Interactive 6-Step Pipeline Visualizer */}
      <div className="glass-card">
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem', color: '#fff' }}>
          Autonomous 6-Step Manhwa Pipeline Flow
        </h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
          How OmniDub transforms webtoons into YouTube ready recaps automatically:
        </p>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: '1rem',
          position: 'relative'
        }}>
          {[
            { step: '01', title: 'Download & Trim', desc: 'AsuraScans or PDF extraction & blank margin removal' },
            { step: '02', title: 'Parallel OCR', desc: 'Contour panel slicing & speech bubble text detection' },
            { step: '03', title: 'Gemini Vision', desc: '38 page-level AI requests for rich story scripting' },
            { step: '04', title: 'Master Script', desc: 'JSON & TXT script compilation with panel sync' },
            { step: '05', title: 'Ken Burns & TTS', desc: '8-worker Edge-TTS audio & pan/zoom video clips' },
            { step: '06', title: 'Final 16:9 Render', desc: 'Lossless FFmpeg stitch into FINAL_MANHWA_RECAP.mp4' },
          ].map((item, idx) => (
            <div key={idx} style={{
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '1.25rem 1rem',
              position: 'relative'
            }}>
              <div style={{
                fontSize: '0.75rem',
                fontWeight: 800,
                color: 'var(--accent-cyan)',
                marginBottom: '0.5rem'
              }}>
                STEP {item.step}
              </div>
              <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff', marginBottom: '0.35rem' }}>
                {item.title}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                {item.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Voice Narrator Soundboard Preview */}
      <div className="glass-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff' }}>
              🎙️ AI Voice Narrators
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Listen to sample narrator voices available in Edge-TTS for recap narration.
            </p>
          </div>
          <div style={{
            fontSize: '0.75rem',
            padding: '0.35rem 0.75rem',
            borderRadius: 'var(--radius-pill)',
            background: 'rgba(139, 92, 246, 0.15)',
            color: 'var(--accent-purple)',
            border: '1px solid rgba(139, 92, 246, 0.3)'
          }}>
            Zero Cloud Fees (Edge-TTS)
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
          {voices.map((v) => (
            <div key={v.id} style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '1rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '0.75rem'
            }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#fff' }}>{v.name}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>{v.style}</div>
              </div>

              <button
                className="btn-secondary"
                onClick={() => handleTestVoice(v.id)}
                style={{
                  padding: '0.4rem 0.8rem',
                  fontSize: '0.8rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  alignSelf: 'flex-start'
                }}
              >
                {playingVoice === v.id ? <Pause size={14} color="#f43f5e" /> : <Play size={14} color="#06b6d4" />}
                {playingVoice === v.id ? 'Stop Sample' : 'Preview Voice'}
              </button>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
