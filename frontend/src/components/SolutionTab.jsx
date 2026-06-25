import TranscriptPanel from './TranscriptPanel';
import { ResultField, SentimentBadge, RecommendedActionPanel } from './ui';
import { formatResolution } from './TopBar';

function StatusBadge({ status }) {
  const normalized = (status || 'pending').toLowerCase();
  const labels = {
    completed: 'Completed',
    failed: 'Failed',
    running: 'Running',
    pending: 'Pending',
    queued: 'Queued',
    retrying: 'Retrying',
    rate_limited: 'Rate Limited',
    timed_out: 'Timed Out (background)',
  };
  return (
    <span className={`status-pill status-${normalized}`}>
      {labels[normalized] || status}
    </span>
  );
}

export default function SolutionTab({ result }) {
  if (!result) return null;

  const { analysis, status, error, parsing_error, status_message, sarvam_batch_job_id } = result;
  const pending = ['queued', 'running', 'timed_out'].includes(status);
  const failed = status === 'failed' || status === 'rate_limited';
  const confidencePct = Math.round((analysis?.confidence || 0) * 100);

  return (
    <div className="result-card">
      <div className="result-meta">
        <div className="meta-item"><span>Status</span><StatusBadge status={status} /></div>
        <div className="meta-item"><span>STT Model</span><strong>{result.stt_model}</strong></div>
        <div className="meta-item"><span>LLM Model</span><strong>{result.llm_model}</strong></div>
        <div className="meta-item"><span>STT Time</span><strong>{result.stt_runtime_seconds?.toFixed(2)}s</strong></div>
        <div className="meta-item"><span>LLM Time</span><strong>{result.llm_runtime_seconds?.toFixed(2)}s</strong></div>
        <div className="meta-item"><span>Total</span><strong>{result.total_runtime_seconds?.toFixed(2)}s</strong></div>
        <div className="meta-item"><span>Score</span><strong>{result.overall_score?.toFixed(2)}</strong></div>
        {result.retry_count > 0 && (
          <div className="meta-item"><span>Retries</span><strong>{result.retry_count}</strong></div>
        )}
      </div>

      {pending && (
        <div className="info-banner inner-banner">
          <p><strong>{status_message || 'Sarvam STT is still processing this audio.'}</strong></p>
          {sarvam_batch_job_id && (
            <p className="loading-hint">Batch job ID: {sarvam_batch_job_id}</p>
          )}
        </div>
      )}

      {failed && (
        <div className="error-panel">
          <h4>Provider Error</h4>
          <p className="error-text">{error || 'Pipeline failed'}</p>
          {parsing_error && (
            <p className="error-detail"><strong>JSON parse:</strong> {parsing_error}</p>
          )}
        </div>
      )}

      <TranscriptPanel transcript={result.transcript} />

      {!failed && !pending && (
        <>
          <section className="result-analysis-card" aria-label="Analysis results">
            <div className="result-fields-grid">
              <ResultField
                label="Sentiment"
                value={<SentimentBadge sentiment={analysis?.sentiment} />}
              />
              <ResultField
                label="Confidence"
                value={`${confidencePct}%`}
                hint={
                  confidencePct >= 75
                    ? 'High reliability'
                    : confidencePct >= 50
                      ? 'Moderate reliability'
                      : 'Review recommended'
                }
              />
              <ResultField
                label="Resolution"
                value={formatResolution(analysis?.resolution_status)}
              />
            </div>
          </section>

          <div className="result-section">
            <h4 className="result-section-label">Summary</h4>
            <p className="result-section-value">{analysis?.summary || '—'}</p>
          </div>

          <div className="result-section">
            <h4 className="result-section-label">Key Issues</h4>
            <ul className="list-items">
              {(analysis?.key_issues || []).map((item, i) => <li key={i}>{item}</li>)}
              {!analysis?.key_issues?.length && <li>—</li>}
            </ul>
          </div>

          <RecommendedActionPanel analysis={analysis} />

          {analysis?.notes && (
            <div className="result-section">
              <h4 className="result-section-label">Notes</h4>
              <p className="result-section-value">{analysis.notes}</p>
            </div>
          )}

          {(analysis?.action_items?.length ?? 0) > 0 && (
            <div className="result-section">
              <h4 className="result-section-label">Action Items</h4>
              <ul className="list-items">
                {analysis.action_items.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export { StatusBadge };
