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

function extractProgressFromJob(job) {
  // Extract progress % from job if available
  // For now, return a dynamic estimate based on job status
  if (!job) return 10;
  if (job.status === 'pending') return 20;
  if (job.status === 'running') return 60;
  if (job.results_ready) return 100;
  return 50;
}

function renderProgressBar(percentage) {
  const filled = Math.floor(percentage / 5); // 20 segments
  const empty = 20 - filled;
  return `[${'█'.repeat(filled)}${'░'.repeat(empty)}] ${percentage}%`;
}

export default function ProcessingState({
  uploadStatus,
  job,
  running,
  multiFile,
  completedBatchCount,
  batchTotal,
}) {
  const [progress, setProgress] = useState(10);

  useEffect(() => {
    if (!running && !job) return;

    const timer = setInterval(() => {
      setProgress((prev) => {
        const jobProgress = extractProgressFromJob(job);
        // Smoothly increment towards job progress but don't exceed it
        if (prev < jobProgress) {
          return Math.min(prev + 5, jobProgress);
        }
        return prev;
      });
    }, 1500); // Update every 1.5 seconds

    return () => clearInterval(timer);
  }, [running, job]);

  const stepIndex = getProcessingStepIndex({ uploadStatus, job, running });
  const progressBar = renderProgressBar(progress);
  const progressMessage = uploadStatus ||
    (multiFile
      ? `Processing ${batchTotal} call recordings…`
      : 'Processing your call recording…');

  return (
    <div className="processing-state">
      <ProgressSteps steps={STEPS} currentIndex={stepIndex} />
      <div className="processing-body">
        <p className="processing-message">{progressMessage}</p>
        <p className="processing-progress">{progressBar}</p>
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
