import { Card, CardHeader, ResultField, SentimentBadge } from './ui';
import { StatusBadge } from './SolutionTab';

export default function SolutionComparison({ result, callReference, audioFilename }) {
  const completed = result?.status === 'completed' || result?.sentiment;
  const confidencePct = completed ? Math.round((result?.confidence || 0) * 100) : null;

  return (
    <div className="analysis-layout">
      <div className="results-banner">
        <div className="results-banner-text">
          <strong>Analysis complete</strong>
          <span>Sarvam STT + Sarvam LLM analysis results.</span>
        </div>
        <div className="results-banner-meta">
          {audioFilename && <span className="results-ref">Audio: {audioFilename}</span>}
          {callReference && <span className="results-ref">Ref: {callReference}</span>}
        </div>
      </div>

      <Card className="analysis-result-card">
        <CardHeader
          title="Analysis Result"
          subtitle="Sentiment, transcript, and recommended actions"
        />
        <div className="analysis-fields">
          <ResultField label="Sentiment" value={completed ? (<SentimentBadge sentiment={result?.sentiment} />) : ('—')} />
          <ResultField label="Confidence" value={confidencePct != null ? `${confidencePct}%` : '—'} />
          <ResultField label="Issue Type" value={result?.issue_type || '—'} />
          <ResultField label="Escalation Risk" value={result?.escalation_risk || '—'} />
        </div>

        {result?.summary && (
          <div className="analysis-section">
            <h4 className="analysis-label">Summary</h4>
            <p className="analysis-text">{result.summary}</p>
          </div>
        )}

        {result?.key_issues?.length > 0 && (
          <div className="analysis-section">
            <h4 className="analysis-label">Key Issues</h4>
            <ul className="analysis-list">
              {result.key_issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          </div>
        )}

        {result?.action_items?.length > 0 && (
          <div className="analysis-section">
            <h4 className="analysis-label">Action Items</h4>
            <ul className="analysis-list">
              {result.action_items.map((action, i) => (
                <li key={i}>{action}</li>
              ))}
            </ul>
          </div>
        )}

        {result?.recommended_action && (
          <div className="analysis-section">
            <h4 className="analysis-label">Recommended Action</h4>
            <p className="analysis-text highlight">{result.recommended_action}</p>
          </div>
        )}

        {result?.transcript && (
          <div className="analysis-section">
            <h4 className="analysis-label">Transcript</h4>
            <p className="analysis-transcript">{result.transcript}</p>
          </div>
        )}
      </Card>
    </div>
  );
}
