import { useState, useRef } from 'react';
import { fileEntryKey } from '../constants/sttLanguages';
import { Button, Alert } from './ui';

const AUDIO_ACCEPT =
  'audio/*,audio/wav,audio/mpeg,audio/mp4,audio/x-m4a,audio/ogg,audio/webm,audio/flac,.wav,.mp3,.mpeg,.m4a,.ogg,.webm,.flac';

const ACCEPTED_LABEL = 'MP3, M4A, WAV, MPEG, FLAC, OGG, WebM';

export default function Sidebar({
  files,
  onFilesChange,
  callReference,
  onCallReferenceChange,
  onRun,
  running,
  health,
  uploadStatus,
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);
  const providersReady =
    health?.providers?.sarvam &&
    health?.providers?.groq &&
    health?.providers?.openrouter;

  const fileCount = files?.length || 0;

  const handleFiles = (incoming) => {
    const list = Array.from(incoming || []);
    if (list.length) onFilesChange(list);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true" />
        <div>
          <h1 className="brand-title">Call Analytics</h1>
          <p className="brand-subtitle">K Fin Tech</p>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        <span className="sidebar-nav-item active">Call Analysis</span>
      </nav>

      <div className="sidebar-section">
        <h2 className="sidebar-label">Upload recording</h2>
        <div
          className={`file-drop ${dragOver ? 'file-drop-active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={AUDIO_ACCEPT}
            onChange={(e) => handleFiles(e.target.files)}
          />
          <p className="file-drop-title">
            {fileCount > 0 ? `${fileCount} file${fileCount !== 1 ? 's' : ''} selected` : 'Drop audio or browse'}
          </p>
          <p className="file-drop-hint">{ACCEPTED_LABEL} · max 25 MB</p>
        </div>

        {fileCount > 0 && (
          <ul className="file-list">
            {files.map((file) => (
              <li key={fileEntryKey(file)}>
                <span className="file-list-name" title={file.name}>{file.name}</span>
                <span className="file-list-size">{(file.size / 1024).toFixed(0)} KB</span>
              </li>
            ))}
          </ul>
        )}

        {uploadStatus && (
          <p className="upload-status" role="status">{uploadStatus}</p>
        )}
      </div>

      <div className="sidebar-section">
        <h2 className="sidebar-label">Call reference</h2>
        <div className="field">
          <input
            type="text"
            placeholder="e.g. CALL-2024-001"
            value={callReference}
            onChange={(e) => onCallReferenceChange(e.target.value)}
            aria-label="Call reference ID"
          />
        </div>
      </div>

      <div className="sidebar-footer">
        <Button
          variant="primary"
          className="sidebar-run-btn"
          onClick={onRun}
          disabled={running || fileCount === 0 || !providersReady}
        >
          {running ? 'Processing…' : fileCount > 1 ? `Analyze ${fileCount} calls` : 'Analyze call'}
        </Button>

        {!providersReady && health && (
          <Alert variant="warning">
            Analysis service is temporarily unavailable. Please try again shortly.
          </Alert>
        )}
      </div>
    </aside>
  );
}
