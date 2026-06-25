import { useState, useEffect } from 'react';
import { ProgressSteps, SkeletonGroup } from './ui';

const STEPS = [
  { id: 'upload', label: 'Upload' },
  { id: 'transcribe', label: 'Transcription' },
  { id: 'analyze', label: 'Analysis' },
  { id: 'complete', label: 'Complete' },
];

export function getProcessingStepIndex({ uploadStatus, job, running }) {
  if (!running && !job) return 0;
  if (uploadStatus?.toLowerCase().includes('upload')) return 0;
  if (job && !job.results_ready) {
    if ((job.pending_providers ?? 0) > 0) return 1;
    return 2;
  }
  if (job?.results_ready) return 3;
  return running ? 1 : 0;
}

function formatElapsedTime(seconds) {
  if (!seconds) return '';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

export default function ProcessingState({
  uploadStatus,
  job,
  running,
  multiFile,
  completedBatchCount,
  batchTotal,
}) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!running && !job) return;

    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [running, job]);

  const stepIndex = getProcessingStepIndex({ uploadStatus, job, running });
  const elapsedDisplay = formatElapsedTime(elapsedSeconds);

  return (
    <div className="processing-state">
      <ProgressSteps steps={STEPS} currentIndex={stepIndex} />
      <div className="processing-body">
        <p className="processing-message">
          {uploadStatus ||
            (multiFile
              ? `Processing ${batchTotal} call recordings…`
              : 'Processing your call recording…')}
        </p>
        <p className="processing-elapsed">
          {elapsedDisplay && `Elapsed time: ${elapsedDisplay}`}
        </p>
        {multiFile && (
          <p className="processing-hint">
            {completedBatchCount} of {batchTotal} analyses complete
          </p>
        )}
        {(job?.pending_providers ?? 0) > 0 && (
          <p className="processing-hint">
            Transcription in progress — this may take several minutes for longer calls.
          </p>
        )}
        {running && !job && (
          <p className="processing-hint">
            Starting analysis — connecting to AI services…
          </p>
        )}
        <SkeletonGroup />
      </div>
    </div>
  );
}
