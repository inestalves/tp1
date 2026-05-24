# TP1 — From Raw Detections to Real Intelligence

Pipeline de reconstrução de trajetórias e inteligência de retalho (LIACD).

## Estrutura

```
tp1/
├── README.md
├── requirements.txt
├── evaluate.py
├── data/
│   ├── events.csv
│   └── validation_anomalies.json
├── src/
│   ├── stitcher.py
│   ├── analytics.py
│   ├── insights.py
│   └── report.py
├── prompts/
│   ├── zero_shot.txt
│   └── few_shot.txt
└── output/
    ├── journeys.csv
    ├── metrics.json
    ├── insights.json
    └── weekly_report.md
```

## Instalação

```bash
pip install -r requirements.txt
ollama pull llama3.1:8b
```

## Pipeline (enunciado)

Executar a partir da raiz `tp1/`:

```bash
python src/stitcher.py --input data/events.csv --output output/journeys.csv
python src/analytics.py --input output/journeys.csv --output output/metrics.json
python src/insights.py --input output/metrics.json --output output/insights.json
python src/report.py --input output/insights.json --output output/weekly_report.md --metrics output/metrics.json
```

## Avaliação (professor)

```bash
python evaluate.py --data events_validation.csv --output evaluation_report.json
```

Para avaliação sem correr o pipeline LLM (mais rápido):

```bash
python evaluate.py --data events_validation.csv --output evaluation_report.json --skip-llm
```

Para usar outputs já existentes sem correr nada:

```bash
python evaluate.py --data events_validation.csv --output evaluation_report.json --evaluate-only
```

## Modelo LLM

- **Ollama:** `llama3.1:8b`
- **Parâmetros:** `temperature=0`, `num_ctx=8192` (em `src/insights.py`)
- **Prompts:** `prompts/zero_shot.txt` (Estratégia A) e `prompts/few_shot.txt` (Estratégia B)

## Resultados (dataset de treino)

| Métrica | Valor |
|---|---|
| Consistência | 100% |
| Completude | 5,44% (ver nota abaixo) |
| Cobertura | 64,59% |
| Gaps medianos entre zonas | 18s (p95: 58s) |
| Ausência de alucinação (report) | 100% |
| Precisão numérica (insights) | 100% |
| Deteção de anomalias injetadas | 50% (Z_N4 ✓, Z_C2 fora do âmbito) |

> **Nota sobre completude:** A completude baixa (5,44%) não é uma falha do algoritmo.
> O dataset tem 14.866 trajetórias reconstruídas mas apenas 10.712 entries em Z_E,
> porque muitos clientes fazem múltiplas passagens pelo checkout na mesma visita
> (visitas circulares). A consistência temporal é 100% — nenhuma sobreposição.
> Ver secção 2.4 do relatório técnico para análise detalhada.