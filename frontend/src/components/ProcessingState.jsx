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

export default function ProcessingState({
  uploadStatus,
  job,
  running,
  multiFile,
  completedBatchCount,
  batchTotal,
}) {
  const stepIndex = getProcessingStepIndex({ uploadStatus, job, running });

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
        {multiFile && (
          <p className="processing-hint">
            {completedBatchCount} of {batchTotal} analyses complete
          </p>
        )}
        {(job?.pending_providers ?? 0) > 0 && (
          <p className="processing-hint">
            Transcription in progress — this may take a few minutes for longer calls.
          </p>
        )}
        <SkeletonGroup />
      </div>
    </div>
  );
}
