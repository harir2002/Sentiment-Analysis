export function Card({ children, className = '', padding = true }) {
  return (
    <section className={`ui-card ${padding ? 'ui-card-padded' : ''} ${className}`.trim()}>
      {children}
    </section>
  );
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div className="ui-card-header">
      <div>
        {title && <h3 className="ui-card-title">{title}</h3>}
        {subtitle && <p className="ui-card-subtitle">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Badge({ children, variant = 'neutral', className = '' }) {
  return (
    <span className={`ui-badge ui-badge-${variant} ${className}`.trim()}>
      {children}
    </span>
  );
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled,
  className = '',
  ...props
}) {
  return (
    <button
      type="button"
      className={`ui-btn ui-btn-${variant} ui-btn-${size} ${className}`.trim()}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}

export function Alert({ children, variant = 'info', title }) {
  return (
    <div className={`ui-alert ui-alert-${variant}`} role="alert">
      {title && <strong className="ui-alert-title">{title}</strong>}
      <div className="ui-alert-body">{children}</div>
    </div>
  );
}

export function Skeleton({ className = '', style }) {
  return <div className={`ui-skeleton ${className}`.trim()} style={style} aria-hidden="true" />;
}

export function SkeletonGroup() {
  return (
    <div className="ui-skeleton-group" aria-busy="true" aria-label="Loading analysis">
      <Skeleton className="ui-skeleton-line ui-skeleton-line-lg" />
      <Skeleton className="ui-skeleton-line" />
      <Skeleton className="ui-skeleton-line" />
      <div className="ui-skeleton-grid">
        <Skeleton className="ui-skeleton-block" />
        <Skeleton className="ui-skeleton-block" />
        <Skeleton className="ui-skeleton-block" />
      </div>
      <Skeleton className="ui-skeleton-block ui-skeleton-block-tall" />
    </div>
  );
}

export function EmptyState({ icon, title, description, action }) {
  return (
    <div className="ui-empty">
      {icon && <div className="ui-empty-icon" aria-hidden="true">{icon}</div>}
      <h3 className="ui-empty-title">{title}</h3>
      {description && <p className="ui-empty-desc">{description}</p>}
      {action}
    </div>
  );
}

export function ProgressSteps({ steps, currentIndex }) {
  return (
    <ol className="ui-steps">
      {steps.map((step, i) => {
        const state = i < currentIndex ? 'done' : i === currentIndex ? 'active' : 'pending';
        return (
          <li key={step.id} className={`ui-step ui-step-${state}`}>
            <span className="ui-step-marker">{i < currentIndex ? '✓' : i + 1}</span>
            <span className="ui-step-label">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function Metric({ label, value, hint }) {
  return (
    <div className="ui-metric">
      <span className="ui-metric-label">{label}</span>
      <div className="ui-metric-value">{value}</div>
      {hint && <span className="ui-metric-hint">{hint}</span>}
    </div>
  );
}

export function ResultField({ label, value, hint }) {
  return (
    <div className="ui-result-field">
      <span className="ui-result-field-label">{label}</span>
      <div className="ui-result-field-value">{value}</div>
      {hint && <span className="ui-result-field-hint">{hint}</span>}
    </div>
  );
}

export function SentimentBadge({ sentiment }) {
  const key = (sentiment || 'neutral').toLowerCase();
  const labels = {
    positive: 'Positive',
    negative: 'Negative',
    neutral: 'Neutral',
    mixed: 'Mixed',
  };
  return (
    <Badge variant={`sentiment-${key}`} className="ui-sentiment-badge">
      {labels[key] || sentiment || '—'}
    </Badge>
  );
}

export function PriorityBadge({ priority }) {
  const key = (priority || 'medium').toLowerCase();
  const variants = {
    critical: 'danger',
    high: 'danger',
    medium: 'warning',
    low: 'neutral',
  };
  return (
    <Badge variant={variants[key] || 'neutral'} className="ui-priority-badge">
      {priority || '—'}
    </Badge>
  );
}

export function RecommendedActionPanel({ analysis }) {
  if (!analysis?.recommended_action) return null;

  return (
    <section className="recommended-action-card" aria-label="Recommended next step">
      <div className="recommended-action-header">
        <h4 className="recommended-action-title">Recommended Action</h4>
        {analysis.action_priority && (
          <PriorityBadge priority={analysis.action_priority} />
        )}
      </div>
      <p className="recommended-action-text">{analysis.recommended_action}</p>
      <div className="recommended-action-meta">
        <ResultField label="Assigned Team" value={analysis.assigned_team || '—'} />
        <ResultField label="Escalation Status" value={analysis.escalation_status || '—'} />
      </div>
    </section>
  );
}
