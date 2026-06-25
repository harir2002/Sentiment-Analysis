import TranscriptPanel from './TranscriptPanel';
import { Card, CardHeader, Alert, Metric, SentimentBadge } from './ui';
import { formatResolution } from './TopBar';

export function pickClientResult(results, ranking) {
  if (!results?.length) return null;

  const winnerId = ranking?.winner?.solution_id;
  if (winnerId) {
    const winner = results.find((r) => r.solution_id === winnerId && r.status === 'completed');
    if (winner) return winner;
  }

  return results.find((r) => r.status === 'completed') || results[0];
}

export default function AnalysisResults({ result, callReference }) {
  if (!result) return null;

  const { analysis, status, error } = result;
  const pending = ['queued', 'running', 'timed_out'].includes(status);
  const failed = status === 'failed' || status === 'rate_limited';
  const completed = status === 'completed' && analysis;

  if (pending) {
    return (
      <Alert variant="info" title="Transcription in progress">
        Your call is being transcribed and analyzed. Results will appear here when ready.
      </Alert>
    );
  }

  if (failed) {
    return (
      <Alert variant="danger" title="Analysis could not be completed">
        {error || 'Please try uploading the file again or contact support if the issue persists.'}
      </Alert>
    );
  }

  if (!completed) return null;

  const confidencePct = Math.round((analysis.confidence || 0) * 100);

  return (
    <div className="results-layout">
      <div className="results-banner">
        <div className="results-banner-text">
          <strong>Analysis complete</strong>
          <span>Your call has been transcribed and reviewed.</span>
        </div>
        {callReference && (
          <span className="results-ref">Ref: {callReference}</span>
        )}
      </div>

      <div className="results-metrics">
        <Card className="metric-card">
          <Metric label="Sentiment" value={<SentimentBadge sentiment={analysis.sentiment} />} />
        </Card>
        <Card className="metric-card">
          <Metric
            label="Confidence"
            value={`${confidencePct}%`}
            hint={confidencePct >= 75 ? 'High reliability' : confidencePct >= 50 ? 'Moderate reliability' : 'Review recommended'}
          />
        </Card>
        <Card className="metric-card">
          <Metric
            label="Resolution"
            value={formatResolution(analysis.resolution_status)}
          />
        </Card>
      </div>

      <Card>
        <CardHeader title="Call Summary" subtitle="Overview of the conversation" />
        <p className="results-body-text">{analysis.summary || 'No summary available.'}</p>
      </Card>

      <div className="results-two-col">
        <Card>
          <CardHeader title="Key Issues" subtitle="Topics and concerns raised" />
          {(analysis.key_issues?.length ?? 0) > 0 ? (
            <ul className="results-list">
              {analysis.key_issues.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="results-muted">No significant issues identified.</p>
          )}
        </Card>

        <Card>
          <CardHeader title="Recommended Actions" subtitle="Follow-up items from the call" />
          {(analysis.action_items?.length ?? 0) > 0 ? (
            <ul className="results-list">
              {analysis.action_items.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="results-muted">No action items identified.</p>
          )}
        </Card>
      </div>

      {analysis.notes && (
        <Card>
          <CardHeader title="Analyst Notes" />
          <p className="results-body-text">{analysis.notes}</p>
        </Card>
      )}

      <Card>
        <TranscriptPanel transcript={result.transcript} title="Full Transcript" expanded />
      </Card>
    </div>
  );
}
