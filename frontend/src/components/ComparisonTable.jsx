import { StatusBadge } from './SolutionTab';

function truncate(text, max = 120) {
  if (!text) return '—';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

function TranscriptCell({ transcript }) {
  return <span>{truncate(transcript, 120)}</span>;
}

export default function ComparisonTable({ results, winnerId }) {
  if (!results?.length) return null;

  return (
    <div className="comparison-table-wrap">
      <h3>Side-by-Side Comparison</h3>
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Solution</th>
            <th>Models</th>
            <th>Transcript</th>
            <th>Sentiment</th>
            <th>Summary</th>
            <th>Key Issues</th>
            <th>Recommended Action</th>
            <th>Confidence</th>
            <th>STT / LLM / Total</th>
            <th>Score</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.solution_id} className={r.solution_id === winnerId ? 'row-winner' : ''}>
              <td><StatusBadge status={r.status} /></td>
              <td>
                <strong>{r.label}</strong>
                {r.solution_id === winnerId && <span className="winner-star"> ★</span>}
              </td>
              <td className="model-cell">
                <div>{r.stt_model}</div>
                <div>{r.llm_model}</div>
              </td>
              <td className="transcript-table-cell">
                <TranscriptCell transcript={r.transcript} />
              </td>
              <td>{r.analysis?.sentiment || '—'}</td>
              <td>{truncate(r.analysis?.summary, 80)}</td>
              <td>{truncate((r.analysis?.key_issues || []).join('; '), 60)}</td>
              <td>{truncate(r.analysis?.recommended_action, 70)}</td>
              <td>{((r.analysis?.confidence || 0) * 100).toFixed(0)}%</td>
              <td>
                {r.stt_runtime_seconds?.toFixed(1)}s / {r.llm_runtime_seconds?.toFixed(1)}s / {r.total_runtime_seconds?.toFixed(1)}s
              </td>
              <td>
                <div className="score-bar">
                  <div className="score-bar-track">
                    <div className="score-bar-fill" style={{ width: `${(r.overall_score || 0) * 100}%` }} />
                  </div>
                  <span>{r.overall_score?.toFixed(2)}</span>
                </div>
              </td>
              <td className="error-text">{r.error || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
