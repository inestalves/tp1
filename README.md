# TP1 — From Raw Detections to Real Intelligence

Pipeline de reconstrução de trajetórias e inteligência de retalho (LIACD).

## Estrutura

```
tp1/
├── README.md
├── requirements.txt
├── evaluate.py
├── data/events.csv
├── src/stitcher.py | analytics.py | insights.py | report.py
├── prompts/*.txt
└── output/journeys.csv | metrics.json | insights.json | weekly_report.md
```

## Instalação

```bash
pip install -r requirements.txt
ollama pull phi3:mini
```

## Pipeline (enunciado)

Executar a partir da raiz `tp1/`:

```bash
python src/stitcher.py --input data/events.csv --output output/journeys.csv
python src/analytics.py --input output/journeys.csv --output output/metrics.json
python src/insights.py --input output/metrics.json --output output/insights.json
python src/report.py --input output/insights.json --output output/weekly_report.md
```

## Avaliação (professor)

```bash
python evaluate.py --data events_validation.csv --output evaluation_report.json
```

## Modelo LLM

- **Ollama:** `phi3:mini`
- **Parâmetros:** `temperature=0` (em `src/insights.py`)
