import { useState } from 'react';
import { Button } from './ui';

export default function TranscriptPanel({
  transcript,
  title = 'Transcript',
  expanded = false,
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const text = (transcript || '').trim();

  return (
    <div className="transcript-panel">
      <div className="transcript-panel-header">
        <div>
          <h3 className="ui-card-title">{title}</h3>
          <p className="ui-card-subtitle">English translation of the call audio</p>
        </div>
        {text && (
          <Button variant="secondary" size="sm" onClick={() => setModalOpen(true)}>
            Expand
          </Button>
        )}
      </div>

      <div className={`transcript-panel-body ${expanded ? 'transcript-panel-expanded' : ''}`}>
        {text || <span className="results-muted">No transcript available.</span>}
      </div>

      {modalOpen && text && (
        <div
          className="transcript-modal-backdrop"
          role="presentation"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="transcript-modal"
            role="dialog"
            aria-labelledby="transcript-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="transcript-modal-header">
              <h4 id="transcript-modal-title">{title}</h4>
              <Button variant="ghost" size="sm" onClick={() => setModalOpen(false)}>
                Close
              </Button>
            </div>
            <div className="transcript-modal-body">{text}</div>
          </div>
        </div>
      )}
    </div>
  );
}
