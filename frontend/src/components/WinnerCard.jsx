export default function WinnerCard({ ranking }) {
  if (!ranking?.winner) return null;

  const { winner } = ranking;

  return (
    <div className="winner-card">
      <h3>Best-Performing Solution</h3>
      <div className="winner-name">{winner.label}</div>
      <div className="winner-score">
        Overall score: <strong>{winner.overall_score.toFixed(2)}</strong> / 1.00
      </div>
    </div>
  );
}
