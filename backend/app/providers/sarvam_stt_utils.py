import json
from pathlib import Path


def extract_transcript_from_json(data: dict) -> str:
    if not isinstance(data, dict):
        return ""

    transcript = data.get("transcript") or data.get("text") or ""
    if transcript:
        return str(transcript).strip()

    diarized = data.get("diarized_transcript") or {}
    entries = diarized.get("entries") if isinstance(diarized, dict) else None
    if entries:
        parts = [str(e.get("transcript", "")).strip() for e in entries if e.get("transcript")]
        return "\n".join(parts).strip()

    if isinstance(data.get("results"), list) and data["results"]:
        return str(data["results"][0].get("transcript", "")).strip()

    return ""


def parse_batch_output_dir(output_dir: str) -> str:
    texts: list[str] = []
    for json_path in sorted(Path(output_dir).glob("*.json")):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            text = extract_transcript_from_json(data)
            if text:
                texts.append(text)
        except (json.JSONDecodeError, OSError):
            continue
    return "\n\n".join(texts).strip()
