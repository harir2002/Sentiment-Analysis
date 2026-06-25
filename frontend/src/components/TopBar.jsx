import { Badge, Button } from './ui';

function formatResolution(status) {
  if (!status) return '—';
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function TopBar({
  title,
  subtitle,
  status,
  statusLabel,
  theme,
  onToggleTheme,
  exportSlot,
}) {
  return (
    <header className="top-bar">
      <div className="top-bar-main">
        <div className="top-bar-titles">
          <h1 className="page-title">{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
        <div className="top-bar-actions">
          {statusLabel && (
            <Badge variant={status === 'failed' ? 'danger' : status === 'completed' ? 'success' : 'neutral'}>
              {statusLabel}
            </Badge>
          )}
          {exportSlot}
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleTheme}
            aria-label={theme === 'dark' ? 'Increase panel contrast' : 'Standard contrast'}
            title={theme === 'dark' ? 'Higher contrast' : 'Standard contrast'}
          >
            {theme === 'dark' ? '◐' : '●'}
          </Button>
        </div>
      </div>
    </header>
  );
}

export { formatResolution };
