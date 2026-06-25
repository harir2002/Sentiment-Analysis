import { useState } from 'react';
import { Card, CardHeader, ResultField, SentimentBadge } from './ui';
import { syncToOdooCRM } from '../services/api';

export default function SolutionComparison({ result, callReference, audioFilename, jobId }) {
  const [odooSyncing, setOdooSyncing] = useState(false);
  const [odooMessage, setOdooMessage] = useState(null);
  const [odooRecordId, setOdooRecordId] = useState(null);
  const completed = result?.status === 'completed' || result?.sentiment;
  const confidencePct = completed ? Math.round((result?.confidence || 0) * 100) : null;

  const handleSyncOdoo = async () => {
    if (!jobId) return;
    setOdooSyncing(true);
    setOdooMessage(null);
    try {
      const response = await syncToOdooCRM(jobId);
      if (response.crm_record_id) {
        setOdooRecordId(response.crm_record_id);
        setOdooMessage({
          type: 'success',
          text: `Synced to Odoo CRM (ID: ${response.crm_record_id})`
        });
      } else {
        setOdooMessage({
          type: 'error',
          text: 'Sync failed: No record ID returned'
        });
      }
    } catch (err) {
      setOdooMessage({
        type: 'error',
        text: `Sync failed: ${err.message}`
      });
    } finally {
      setOdooSyncing(false);
    }
  };

  const handleOpenOdoo = () => {
    if (!odooRecordId) return;
    // Extract Odoo server URL from environment or use default
    const odooUrl = import.meta.env.VITE_ODOO_URL || 'https://sba-info-solutions-pvt-ltd.odoo.com';
    const recordUrl = `${odooUrl}/web#id=${odooRecordId}&model=crm.lead&view_type=form`;
    window.open(recordUrl, '_blank');
  };

  if (!result) return null;

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

      {/* Core Metrics Section */}
      <Card className="analysis-result-card">
        <CardHeader
          title="Analysis Result"
          subtitle="Call sentiment, intent, and escalation assessment"
        />
        <div className="analysis-fields">
          <ResultField 
            label="Sentiment" 
            value={completed ? (<SentimentBadge sentiment={result?.sentiment} />) : ('—')} 
          />
          <ResultField 
            label="Confidence" 
            value={confidencePct != null ? `${confidencePct}%` : '—'} 
          />
          <ResultField 
            label="Intent" 
            value={result?.issue_type || 'General Inquiry'} 
          />
          <ResultField 
            label="Escalation Risk" 
            value={result?.escalation_risk || 'Low'} 
          />
        </div>
      </Card>

      {/* Summary Section */}
      {result?.summary && (
        <Card>
          <CardHeader title="Summary" subtitle="Call overview" />
          <div className="analysis-section">
            <p className="analysis-text">{result.summary}</p>
          </div>
        </Card>
      )}

      {/* Key Issues Section */}
      <Card>
        <CardHeader title="Key Issues" subtitle="Topics and concerns identified" />
        <div className="analysis-section">
          {result?.key_issues?.length > 0 ? (
            <ul className="analysis-list">
              {result.key_issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          ) : (
            <p className="analysis-muted">No significant issues identified.</p>
          )}
        </div>
      </Card>

      {/* Action Items Section */}
      <Card>
        <CardHeader title="Action Items" subtitle="Recommended follow-up actions" />
        <div className="analysis-section">
          {result?.action_items?.length > 0 ? (
            <ul className="analysis-list">
              {result.action_items.map((action, i) => (
                <li key={i}>{action}</li>
              ))}
            </ul>
          ) : (
            <p className="analysis-muted">No specific action items identified.</p>
          )}
        </div>
      </Card>

      {/* Recommended Action Section */}
      {result?.recommended_action && (
        <Card>
          <CardHeader title="Recommended Action" subtitle="Primary follow-up suggestion" />
          <div className="analysis-section">
            <p className="analysis-text highlight">{result.recommended_action}</p>
          </div>
        </Card>
      )}

      {/* Transcript Section */}
      {result?.transcript && (
        <Card>
          <CardHeader title="Transcript" subtitle="Full call recording transcript" />
          <div className="analysis-section">
            <p className="analysis-transcript">{result.transcript}</p>
          </div>
        </Card>
      )}

      {/* Odoo CRM Sync Message */}
      {odooMessage && (
        <div className={`odoo-message odoo-message-${odooMessage.type}`}>
          {odooMessage.text}
        </div>
      )}

      {/* Odoo CRM Sync & Open Buttons */}
      <div className="analysis-section-actions">
        <button
          onClick={handleSyncOdoo}
          disabled={odooSyncing}
          className="btn btn-odoo"
          title="Push analysis results to Odoo CRM"
        >
          {odooSyncing ? '⏳ Syncing to Odoo CRM...' : '🔗 Push to Odoo CRM'}
        </button>
        {odooRecordId && (
          <button
            onClick={handleOpenOdoo}
            className="btn btn-odoo-open"
            title="Open record in Odoo CRM"
          >
            📂 Open in Odoo
          </button>
        )}
      </div>
    </div>
  );
}
