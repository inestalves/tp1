from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
OUTPUT = ROOT / "output"

ENTRY_ZONES = ("Z_E1", "Z_E2")
EXIT_ZONES = ("Z_E1", "Z_E2", "Z_CK")


def run_cmd(cmd: list[str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def run_pipeline(events_path: Path, run_llm: bool) -> dict[str, Path]:
    OUTPUT.mkdir(exist_ok=True)
    paths = {
        "journeys": OUTPUT / "journeys.csv",
        "metrics": OUTPUT / "metrics.json",
        "insights": OUTPUT / "insights.json",
        "report": OUTPUT / "weekly_report.md",
    }

    py = sys.executable
    run_cmd([py, str(SRC / "stitcher.py"), "--input", str(events_path), "--output", str(paths["journeys"])])
    run_cmd([py, str(SRC / "analytics.py"), "--input", str(paths["journeys"]), "--output", str(paths["metrics"])])

    if run_llm:
        run_cmd([py, str(SRC / "insights.py"), "--input", str(paths["metrics"]), "--output", str(paths["insights"])])
        run_cmd([py, str(SRC / "report.py"), "--input", str(paths["insights"]), "--output", str(paths["report"])])

    return paths


def resolve_path(path: str | None, default: Path) -> Path:
    if not path:
        return default
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def output_paths(args) -> dict[str, Path]:
    return {
        "journeys": resolve_path(args.journeys, OUTPUT / "journeys.csv"),
        "metrics":  resolve_path(args.metrics,  OUTPUT / "metrics.json"),
        "insights": resolve_path(args.insights, OUTPUT / "insights.json"),
        "report":   resolve_path(args.report,   OUTPUT / "weekly_report.md"),
    }


def check_outputs(paths: dict[str, Path], need_events: bool) -> None:
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Ficheiros em falta para --evaluate-only: "
            + ", ".join(f"{k}={paths[k]}" for k in missing)
        )


def metric_consistency(journeys: pd.DataFrame) -> dict:
    df = journeys.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"]  = pd.to_datetime(df["exit_time"])

    total_persons = df["person_id"].nunique()
    violations = 0

    for pid, group in df.groupby("person_id"):
        g = group.sort_values("entry_time")
        prev_exit = None
        for _, row in g.iterrows():
            if prev_exit is not None and row["entry_time"] < prev_exit:
                violations += 1
                break
            prev_exit = row["exit_time"]

    consistent = total_persons - violations
    pct = (consistent / total_persons * 100) if total_persons else 0.0

    return {
        "value_percent": round(pct, 2),
        "total_persons": int(total_persons),
        "persons_with_overlap": int(violations),
        "target": "100%",
    }


def metric_coverage(events: pd.DataFrame, journeys: pd.DataFrame) -> dict:
    """
    Para cada evento, verifica se existe uma visita
    com a mesma zona+atributos cujo intervalo [entry_time, exit_time] contém
    o timestamp do evento.
    """
    ev = events[['timestamp', 'zone_id', 'gender', 'age_range']].copy()
    ev['timestamp'] = pd.to_datetime(ev['timestamp'])

    jn = journeys[['zone_id', 'gender', 'age_range', 'entry_time', 'exit_time']].copy()
    jn['entry_time'] = pd.to_datetime(jn['entry_time'])
    jn['exit_time']  = pd.to_datetime(jn['exit_time'])

    # Merge por zona + atributos — expande cada evento com todas as visitas
    # compatíveis em termos de zona/género/idade
    merged = ev.merge(jn, on=['zone_id', 'gender', 'age_range'], how='left')

    # Filtrar apenas os pares onde o timestamp cai dentro do intervalo da visita
    covered_mask = (merged['timestamp'] >= merged['entry_time']) & \
                   (merged['timestamp'] <= merged['exit_time'])

    # Um evento é coberto se tiver pelo menos um match
    covered_events = merged[covered_mask]['timestamp'].nunique()
    total = len(ev)
    pct = (covered_events / total * 100) if total else 0.0

    return {
        "value_percent": round(pct, 2),
        "events_total": int(total),
        "events_covered_heuristic": int(covered_events),
        "note": "Cobertura inferida por zona+tempo+atributos; ideal seria event_id no stitcher.",
    }


def metric_completeness(journeys: pd.DataFrame) -> dict:
    df = journeys.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"])

    complete = 0
    total = df["person_id"].nunique()

    for pid, group in df.groupby("person_id"):
        g = group.sort_values("entry_time")
        first_zone = g.iloc[0]["zone_id"]
        last_zone  = g.iloc[-1]["zone_id"]
        starts_ok = str(first_zone).startswith("Z_E")
        ends_ok   = last_zone in EXIT_ZONES or str(last_zone).startswith("Z_E")
        if starts_ok and ends_ok:
            complete += 1

    pct = (complete / total * 100) if total else 0.0
    return {
        "value_percent": round(pct, 2),
        "complete_trajectories": int(complete),
        "total_trajectories": int(total),
    }


def metric_transition_gaps(journeys: pd.DataFrame) -> dict:
    df = journeys.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"]  = pd.to_datetime(df["exit_time"])

    gaps = []
    for _, group in df.groupby("person_id"):
        g = group.sort_values("entry_time")
        for i in range(len(g) - 1):
            gap_s = (g.iloc[i + 1]["entry_time"] - g.iloc[i]["exit_time"]).total_seconds()
            if gap_s >= 0:
                gaps.append(gap_s)

    if not gaps:
        return {"count": 0, "median_s": 0, "p95_s": 0, "over_300s_percent": 0}

    s = pd.Series(gaps)
    return {
        "count": int(len(s)),
        "median_s": float(s.median()),
        "p95_s": float(s.quantile(0.95)),
        "over_300s_percent": round((s > 300).mean() * 100, 2),
    }


def _flatten_numbers(obj, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_numbers(v, out)


def _extract_numbers_from_text(text: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", text)]


def _number_in_metrics(value: float, metric_numbers: list[float], tol: float = 0.05) -> bool:
    for m in metric_numbers:
        if m == 0 and value == 0:
            return True
        if m != 0 and abs(value - m) / abs(m) <= tol:
            return True
        if m < 1 and value > 1 and abs(value / 100 - m) <= tol:
            return True
        if m > 1 and value < 1 and abs(m / 100 - value) <= tol:
            return True
    return False


def metric_numeric_precision(insights_path: Path, metrics_path: Path) -> dict:
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)
    with open(insights_path, encoding="utf-8") as f:
        insights_doc = json.load(f)

    metric_numbers: list[float] = []
    _flatten_numbers(metrics, metric_numbers)

    texts = []
    for key in ("zero_shot_results", "few_shot_results"):
        block = insights_doc.get(key, {})
        for ins in block.get("insights", []):
            for field in ("observacao", "implicacao", "recomendacao", "titulo"):
                texts.append(str(ins.get(field, "")))

    found = _extract_numbers_from_text(" ".join(texts))
    found = [n for n in found if n > 1 or n == 0]

    verified = sum(1 for n in found if _number_in_metrics(n, metric_numbers))
    total = len(found) or 1

    return {
        "value_percent": round(verified / total * 100, 2),
        "numbers_found": len(found),
        "numbers_verified": verified,
        "note": "Comparação aproximada.",
    }


def metric_report_hallucination(report_path: Path, metrics_path: Path) -> dict:
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)
    text = report_path.read_text(encoding="utf-8")

    metric_numbers: list[float] = []
    _flatten_numbers(metrics, metric_numbers)

    found = [n for n in _extract_numbers_from_text(text) if n > 1 or n == 0]
    verified = sum(1 for n in found if _number_in_metrics(n, metric_numbers))
    total = len(found) or 1

    return {
        "value_percent": round(verified / total * 100, 2),
        "numbers_found": len(found),
        "numbers_verified": verified,
    }


def _insights_text_blob(insights_doc: dict) -> str:
    parts: list[str] = []
    for key in ("zero_shot_results", "few_shot_results"):
        block = insights_doc.get(key, {})
        for ins in block.get("insights", []):
            parts.append(json.dumps(ins, ensure_ascii=False))
        for item in block.get("resumo_executivo", []):
            parts.append(str(item))
    return " ".join(parts).lower()


def _anomaly_mentioned(blob: str, zone: str, hour: int | None = None) -> bool:
    if zone.lower() not in blob:
        return False
    if hour is not None and str(hour) not in blob:
        return False
    return True


def _expected_anomalies(
    ground_truth_path: Path | None,
    metrics_path: Path | None,
) -> tuple[list[dict], str]:
    if ground_truth_path and ground_truth_path.exists():
        with open(ground_truth_path, encoding="utf-8") as f:
            return json.load(f), "ground_truth_file"

    if metrics_path and metrics_path.exists():
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)
        from_metrics = []
        for a in metrics.get("anomalies_day_7", []):
            zone = a.get("zone") or a.get("zone_id")
            if zone:
                from_metrics.append({"zone_id": zone, "hour_of_day": a.get("hour_of_day")})
        if from_metrics:
            return from_metrics, "metrics_anomalies_day_7"

    return [], "none"


def metric_anomaly_detection(
    insights_path: Path,
    ground_truth_path: Path | None,
    metrics_path: Path | None,
) -> dict:
    expected, source = _expected_anomalies(ground_truth_path, metrics_path)
    if not expected:
        return {
            "value_percent": None,
            "skipped": True,
            "reason": "Sem anomalias em metrics.json nem em validation_anomalies.json.",
        }

    with open(insights_path, encoding="utf-8") as f:
        insights_doc = json.load(f)
    blob = _insights_text_blob(insights_doc)

    hits = 0
    for anomaly in expected:
        zone = anomaly.get("zone_id") or anomaly.get("zone", "")
        hour = anomaly.get("hour_of_day")
        if _anomaly_mentioned(blob, zone, hour):
            hits += 1

    total = len(expected)
    return {
        "value_percent": round(hits / total * 100, 2),
        "expected": total,
        "detected_matches": hits,
        "source": source,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Harness de avaliação TP1")
    parser.add_argument("--data", default="data/events.csv", help="CSV de eventos")
    parser.add_argument("--output", required=True, help="JSON de relatório de avaliação")
    parser.add_argument("--evaluate-only", action="store_true",
                        help="Não corre pipeline; usa ficheiros em output/")
    parser.add_argument("--skip-coverage", action="store_true",
                        help="Ignora cobertura")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Pipeline sem Ollama")
    parser.add_argument("--journeys", help="Caminho para journeys.csv")
    parser.add_argument("--metrics",  help="Caminho para metrics.json")
    parser.add_argument("--insights", help="Caminho para insights.json")
    parser.add_argument("--report",   help="Caminho para weekly_report.md")
    parser.add_argument("--ground-truth",
                        default=str(ROOT / "data" / "validation_anomalies.json"),
                        help="Lista de anomalias injetadas")
    args = parser.parse_args()

    paths = output_paths(args)

    if args.evaluate_only:
        check_outputs(paths, need_events=not args.skip_coverage)
        print("Modo --evaluate-only: a usar outputs existentes.")
    else:
        events_path = resolve_path(args.data, ROOT / "data" / "events.csv")
        paths = run_pipeline(events_path, run_llm=not args.skip_llm)

    journeys = pd.read_csv(paths["journeys"])
    journeys["entry_time"] = pd.to_datetime(journeys["entry_time"])
    journeys["exit_time"]  = pd.to_datetime(journeys["exit_time"])

    events_path = resolve_path(args.data, ROOT / "data" / "events.csv")

    phase1 = {
        "consistency":       metric_consistency(journeys),
        "completeness":      metric_completeness(journeys),
        "transition_gaps":   metric_transition_gaps(journeys),
    }

    if args.skip_coverage:
        phase1["coverage"] = {"skipped": True, "reason": "Nâo disponíveç"}
    else:
        if not events_path.exists():
            raise FileNotFoundError(f"events.csv em falta para cobertura: {events_path}")
        print("A calcular cobertura...")
        events = pd.read_csv(events_path)
        events["timestamp"] = pd.to_datetime(events["timestamp"])
        phase1["coverage"] = metric_coverage(events, journeys)

    report = {
        "mode": "evaluate_only" if args.evaluate_only else "full_pipeline",
        "input_events": str(events_path) if not args.skip_coverage else None,
        "outputs": {k: str(v) for k, v in paths.items()},
        "phase1": phase1,
    }

    gt_path = Path(args.ground_truth)
    if not gt_path.is_absolute():
        gt_path = ROOT / gt_path

    if paths["metrics"].exists():
        report["phase2"] = {}
        if paths["insights"].exists():
            report["phase2"]["numeric_precision"] = metric_numeric_precision(
                paths["insights"], paths["metrics"])
            report["phase2"]["anomaly_detection"] = metric_anomaly_detection(
                paths["insights"],
                gt_path if gt_path.exists() else None,
                paths["metrics"])
        if paths["report"].exists():
            report["phase2"]["absence_of_hallucination"] = metric_report_hallucination(
                paths["report"], paths["metrics"])

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nRelatório guardado em: {out_path}")
    print(json.dumps(report["phase1"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()