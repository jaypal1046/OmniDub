import React, { useState, useEffect } from 'react';
import { 
  Folder, 
  Film, 
  Music, 
  FileText, 
  ExternalLink, 
  RefreshCw, 
  Play, 
  Image, 
  Calendar,
  Layers,
  ChevronRight,
  Sparkles
} from 'lucide-react';
import { api } from '../services/api';

export default function ProjectGallery() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedProject, setSelectedProject] = useState(null);
  const [projectDetails, setProjectDetails] = useState(null);
  const [activeTab, setActiveTab] = useState('video'); // 'video' | 'script' | 'slices'

  const loadProjects = async () => {
    setLoading(true);
    try {
      const list = await api.listProjects();
      setProjects(list);
      if (list.length > 0 && !selectedProject) {
        setSelectedProject(list[0]);
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    if (selectedProject) {
      api.getProjectDetails(selectedProject.name).then(details => {
        setProjectDetails(details);
      });
    }
  }, [selectedProject]);

  const handleOpenFolder = (path) => {
    api.openPath(path);
  };

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff' }}>
            Generated Media & Project Gallery
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
            Review, preview, and play generated YouTube recap videos, narration audio tracks, and scripts.
          </p>
        </div>

        <button 
          className="btn-secondary"
          onClick={loadProjects}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <RefreshCw size={16} className={loading ? 'spinner' : ''} />
          Refresh Projects
        </button>
      </div>

      {projects.length === 0 && !loading ? (
        <div className="glass-card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
          <Folder size={48} color="var(--text-muted)" style={{ margin: '0 auto 1rem auto' }} />
          <h3 style={{ fontSize: '1.25rem', color: '#fff', marginBottom: '0.5rem' }}>No projects generated yet</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', maxWidth: '400px', margin: '0 auto' }}>
            Head over to the Studio tab and launch your first Manhwa or Video Recap generation pipeline.
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '1.5rem', minHeight: '600px' }}>
          
          {/* Projects Sidebar List */}
          <div className="glass-card" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', padding: '0.5rem', letterSpacing: '0.05em' }}>
              Completed Projects ({projects.length})
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto', maxHeight: '650px' }}>
              {projects.map((proj) => {
                const isSelected = selectedProject?.name === proj.name;
                const formattedDate = new Date(proj.updatedAt).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                });

                return (
                  <div
                    key={proj.name}
                    onClick={() => setSelectedProject(proj)}
                    style={{
                      padding: '0.85rem 1rem',
                      borderRadius: 'var(--radius-md)',
                      background: isSelected ? 'linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(139, 92, 246, 0.2))' : 'rgba(255, 255, 255, 0.02)',
                      border: `1px solid ${isSelected ? 'var(--accent-cyan)' : 'var(--border-subtle)'}`,
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.9rem', color: isSelected ? '#fff' : '#e2e8f0', wordBreak: 'break-all' }}>
                        {proj.name}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <Calendar size={12} /> {formattedDate}
                      </span>
                      {proj.hasVideo && (
                        <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>MP4 Video</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Project Details / Media Viewer */}
          {selectedProject && (
            <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              
              {/* Top Details Bar */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '1rem' }}>
                <div>
                  <h3 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
                    {selectedProject.name}
                  </h3>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                    Path: <code style={{ color: 'var(--accent-cyan)' }}>{selectedProject.path}</code>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button 
                    className="btn-secondary"
                    onClick={() => handleOpenFolder(selectedProject.path)}
                    style={{ fontSize: '0.8rem', padding: '0.5rem 0.9rem' }}
                  >
                    <ExternalLink size={14} />
                    Open Folder in Explorer
                  </button>
                </div>
              </div>

              {/* Viewer Tabs */}
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  className={`nav-tab-btn ${activeTab === 'video' ? 'active' : ''}`}
                  onClick={() => setActiveTab('video')}
                >
                  <Film size={15} /> Video & Audio Player
                </button>
                <button
                  className={`nav-tab-btn ${activeTab === 'script' ? 'active' : ''}`}
                  onClick={() => setActiveTab('script')}
                >
                  <FileText size={15} /> Story Script
                </button>
                <button
                  className={`nav-tab-btn ${activeTab === 'slices' ? 'active' : ''}`}
                  onClick={() => setActiveTab('slices')}
                >
                  <Image size={15} /> Slices & Artwork
                </button>
              </div>

              {/* Content Panel */}
              <div style={{ flex: 1, minHeight: '400px' }}>
                
                {/* Tab: Video & Audio */}
                {activeTab === 'video' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    {selectedProject.hasVideo ? (
                      <div style={{ borderRadius: 'var(--radius-md)', overflow: 'hidden', background: '#000', border: '1px solid var(--border-subtle)' }}>
                        <video
                          controls
                          src={api.formatMediaUrl(selectedProject.videoPath)}
                          style={{ width: '100%', maxHeight: '480px', display: 'block' }}
                        />
                      </div>
                    ) : (
                      <div style={{
                        padding: '3rem',
                        textAlign: 'center',
                        background: 'rgba(255, 255, 255, 0.02)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px dashed var(--border-subtle)',
                        color: 'var(--text-muted)'
                      }}>
                        <Film size={36} style={{ margin: '0 auto 0.5rem auto' }} />
                        No final video rendered yet for this project.
                      </div>
                    )}

                    {/* Audio track preview */}
                    {selectedProject.hasAudio && (
                      <div style={{
                        padding: '1rem',
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-subtle)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.5rem'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fff', fontSize: '0.85rem', fontWeight: 600 }}>
                          <Music size={16} color="var(--accent-purple)" />
                          Master Narration Audio Track
                        </div>
                        <audio 
                          controls 
                          src={api.formatMediaUrl(selectedProject.audioPath)} 
                          style={{ width: '100%' }}
                        />
                      </div>
                    )}
                  </div>
                )}

                {/* Tab: Story Script */}
                {activeTab === 'script' && (
                  <div style={{
                    background: '#070a10',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '1.25rem',
                    maxHeight: '480px',
                    overflowY: 'auto',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.85rem',
                    lineHeight: 1.7,
                    color: '#e2e8f0',
                    whiteSpace: 'pre-wrap'
                  }}>
                    {projectDetails?.scriptText || 'No master script text found in this project folder.'}
                  </div>
                )}

                {/* Tab: Comic Slices */}
                {activeTab === 'slices' && (
                  <div>
                    {projectDetails?.sampleImages && projectDetails.sampleImages.length > 0 ? (
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
                        gap: '0.75rem',
                        maxHeight: '480px',
                        overflowY: 'auto',
                        padding: '0.5rem'
                      }}>
                        {projectDetails.sampleImages.map((imgUrl, i) => (
                          <div 
                            key={i}
                            style={{
                              borderRadius: 'var(--radius-sm)',
                              overflow: 'hidden',
                              background: '#000',
                              border: '1px solid var(--border-subtle)',
                              aspectRatio: '1',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center'
                            }}
                          >
                            <img 
                              src={api.formatMediaUrl(imgUrl)} 
                              alt={`Slice ${i}`}
                              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                            />
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No cropped comic panel slices detected for this project.
                      </div>
                    )}
                  </div>
                )}

              </div>
            </div>
          )}

        </div>
      )}

    </div>
  );
}
