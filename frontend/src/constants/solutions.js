/** Canonical order for all four STT + LLM pipelines. */
export const SOLUTION_ORDER = [
  {
    id: 'sarvam_stt_sarvam_llm',
    label: 'Sarvam STT + Sarvam LLM',
  },
  {
    id: 'sarvam_stt_groq_gemma',
    label: 'Sarvam STT + Groq Gemma 4 26B A4B',
  },
  {
    id: 'groq_whisper_sarvam_llm',
    label: 'Groq Whisper + Sarvam LLM',
  },
  {
    id: 'groq_whisper_groq_gemma',
    label: 'Groq Whisper + Groq Gemma 4 26B A4B',
  },
];

export function orderSolutionResults(results = []) {
  const byId = Object.fromEntries((results || []).map((r) => [r.solution_id, r]));
  return SOLUTION_ORDER.map(({ id, label }) => (
    byId[id] || {
      solution_id: id,
      label,
      status: 'pending',
      transcript: '',
      error: 'No result available for this pipeline',
      analysis: null,
      overall_score: 0,
      stt_model: '—',
      llm_model: '—',
    }
  ));
}
