import { downloadExport } from '../services/api';
import { Card, CardHeader, Button } from './ui';

export default function ExportSection({ jobId, compact = false }) {
  if (!jobId) return null;

  if (compact) {
    return (
      <div className="export-buttons-compact">
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'docx')}>
          📄 Word
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'pdf')}>
          📕 PDF
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'xlsx')}>
          📊 Excel
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'csv')}>
          📋 CSV
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'json')}>
          {} JSON
        </Button>
      </div>
    );
  }

  return (
    <Card className="export-card">
      <CardHeader
        title="Export Analysis Report"
        subtitle="Download report in your preferred format"
      />
      <div className="export-actions">
        <Button variant="primary" size="sm" onClick={() => downloadExport(jobId, 'docx')}>
          Export Word
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'pdf')}>
          Export PDF
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'xlsx')}>
          Export Excel
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'csv')}>
          Export CSV
        </Button>
        <Button variant="secondary" size="sm" onClick={() => downloadExport(jobId, 'json')}>
          Export JSON
        </Button>
      </div>
    </Card>
  );
}
