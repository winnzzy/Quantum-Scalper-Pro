"""Durable qualification evidence tied to an exact historical dataset."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.markets import normalize_symbol


def _stem(symbol: str, timeframe: str) -> str:
    return f"{normalize_symbol(symbol).replace('/', '_')}_{timeframe}"


def evidence_paths(symbol: str, timeframe: str) -> tuple[Path, Path, Path]:
    root = Path(settings.BACKTEST_DATA_PATH)
    stem = _stem(symbol, timeframe)
    return (
        root / f"{stem}.csv",
        root / f"{stem}.manifest.json",
        root / f"{stem}.qualification.json",
    )


def dataset_fingerprint(symbol: str, timeframe: str) -> str | None:
    data_path, _, _ = evidence_paths(symbol, timeframe)
    if not data_path.exists():
        return None
    return hashlib.sha256(data_path.read_bytes()).hexdigest()


def save_qualification(symbol: str, timeframe: str, result: dict[str, Any]) -> Path:
    """Save only gate evidence; never treat a raw backtest as live approval."""
    data_path, manifest_path, qualification_path = evidence_paths(symbol, timeframe)
    fingerprint = dataset_fingerprint(symbol, timeframe)
    payload = {
        "schema_version": 1,
        "symbol": normalize_symbol(symbol),
        "timeframe": timeframe,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": fingerprint,
        "dataset_path": data_path.name,
        "manifest_path": manifest_path.name,
        "strategy": result.get("strategy"),
        "final_parameters": result.get("final_parameters", {}),
        "out_of_sample_summary": result.get("out_of_sample_summary", {}),
        "untouched_holdout": result.get("untouched_holdout", {}),
        "adverse_cost_holdout": result.get("adverse_cost_holdout", {}),
        "promotion_gate": result.get("promotion_gate", {"approved": False}),
    }
    qualification_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = qualification_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(qualification_path)
    return qualification_path


def qualification_readiness(symbol: str, timeframe: str) -> dict[str, Any]:
    data_path, manifest_path, qualification_path = evidence_paths(symbol, timeframe)
    blockers: list[str] = []
    fingerprint = dataset_fingerprint(symbol, timeframe)
    if fingerprint is None:
        blockers.append("Historical dataset is missing")

    manifest: dict[str, Any] = {}
    if not manifest_path.exists():
        blockers.append("Provenance manifest is missing")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if fingerprint and manifest.get("sha256") != fingerprint:
                blockers.append("Dataset fingerprint does not match its provenance manifest")
        except (json.JSONDecodeError, OSError):
            blockers.append("Provenance manifest is unreadable")

    qualification: dict[str, Any] = {}
    if not qualification_path.exists():
        blockers.append("Qualification report is missing")
    else:
        try:
            qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
            if qualification.get("dataset_sha256") != fingerprint:
                blockers.append("Qualification report belongs to a different dataset")
            if not qualification.get("promotion_gate", {}).get("approved", False):
                blockers.append("Strategy has not passed every promotion check")
        except (json.JSONDecodeError, OSError):
            blockers.append("Qualification report is unreadable")

    return {
        "symbol": normalize_symbol(symbol),
        "timeframe": timeframe,
        "ready_for_live": not blockers,
        "blockers": blockers,
        "dataset_sha256": fingerprint,
        "source": manifest.get("source"),
        "qualified_at": qualification.get("created_at"),
        "strategy": qualification.get("strategy"),
    }
