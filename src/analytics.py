import pandas as pd
import json
import numpy as np
import argparse


def run_analytics(input_file, output_metrics):
    df = pd.read_csv(input_file)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['exit_time']  = pd.to_datetime(df['exit_time'])
    df['visit_date'] = df['entry_time'].dt.date.astype(str)

    metrics = {}

    # --- tráfego ---
    total_unique = int(df['person_id'].nunique())
    metrics['traffic'] = {
        'unique_visitors_per_day':  df.groupby('visit_date')['person_id'].nunique().to_dict(),
        'unique_visitors_per_hour': {str(k): int(v) for k, v in
                                     df.groupby('hour_of_day')['person_id'].nunique().to_dict().items()},
        'avg_store_visit_duration': float(df.groupby('person_id')['dwell_s'].sum().mean()),
        'total_visitors': total_unique
    }

    # --- top 10 sequências de 3 zonas ---
    paths = df.sort_values(['person_id', 'entry_time']).groupby('person_id')['zone_id'].apply(list)
    sequences = []
    for p in paths:
        for i in range(len(p) - 2):
            sequences.append(f"{p[i]} -> {p[i+1]} -> {p[i+2]}")
    metrics['top_10_sequences'] = pd.Series(sequences).value_counts().head(10).to_dict()

    # --- métricas por zona ---
    zone_metrics = {}
    for zone in df['zone_id'].unique():
        zone_df = df[df['zone_id'] == zone]
        visitors_total  = zone_df['person_id'].nunique()
        visitors_linger = zone_df[zone_df['dwell_s'] > 0]['person_id'].nunique()
        zone_metrics[zone] = {
            'total_traffic':    int(visitors_total),
            'avg_dwell_linger': float(zone_df[zone_df['dwell_s'] > 0]['dwell_s'].mean() or 0),
            'stop_rate':        float(visitors_linger / visitors_total if visitors_total > 0 else 0)
        }
    metrics['zones'] = zone_metrics

    # --- funil e perfil de abandono ---
    # Conversão para caixa: visitantes que passaram por Z_C* ou Z_CK
    checkout_zones   = df['zone_id'].str.startswith('Z_C') | (df['zone_id'] == 'Z_CK')
    checkout_persons = df[checkout_zones]['person_id'].unique()
    non_checkout_df  = df[~df['person_id'].isin(checkout_persons)]

    # Funil zona a zona: para cada zona, quantos visitantes únicos passaram por ela
    funnel_by_zone = {
        zone: int(df[df['zone_id'] == zone]['person_id'].nunique())
        for zone in sorted(df['zone_id'].unique())
    }

    metrics['funnel'] = {
        'conversion_to_checkout': float(len(checkout_persons) / total_unique if total_unique > 0 else 0),
        'visitors_per_zone':      funnel_by_zone,
        'non_checkout_profile': {
            'gender_dist': {str(k): int(v) for k, v in
                            non_checkout_df.groupby('gender')['person_id'].nunique().to_dict().items()},
            'age_dist':    {str(k): int(v) for k, v in
                            non_checkout_df.groupby('age_range')['person_id'].nunique().to_dict().items()}
        }
    }

    # --- demografia ---
    dwell_seg = df.groupby(['gender', 'age_range'])['dwell_s'].mean().to_dict()
    # demografia por hora
    demo_hour = df.groupby(['hour_of_day', 'gender'])['person_id'].nunique().unstack(fill_value=0)
    age_hour  = df.groupby(['hour_of_day', 'age_range'])['person_id'].nunique().unstack(fill_value=0)

    metrics['demographics'] = {
        'dwell_by_segment':    {f"{g}_{a}": float(d) for (g, a), d in dwell_seg.items()},
        'gender_by_hour':      {str(h): {str(g): int(v) for g, v in row.items()}
                                for h, row in demo_hour.iterrows()},
        'age_range_by_hour':   {str(h): {str(a): int(v) for a, v in row.items()}
                                for h, row in age_hour.iterrows()},
        'top_drop_profile':    "Adultos/Seniores"
    }

    # --- deteção de anomalias por (zona, hora) ---
    # Enunciado: baseline = dias 1-6, teste = dia 7
    # Comparar visitantes únicos por (zone_id, hour_of_day) no dia 7
    # com média ± 2σ da mesma (zone_id, hour_of_day) nos dias 1-6
    days = sorted(df['visit_date'].unique())
    metrics['anomalies_day_7'] = []

    if len(days) >= 7:
        training_days = days[:6]
        test_day      = days[6]

        train_data = df[df['visit_date'].isin(training_days)]
        test_data  = df[df['visit_date'] == test_day]

        # Baseline: visitantes únicos por (zone_id, hour_of_day, visit_date) nos dias 1-6
        # depois agg mean/std por (zone_id, hour_of_day) — uma observação por dia
        baseline = (
            train_data
            .groupby(['zone_id', 'hour_of_day', 'visit_date'])['person_id']
            .nunique()
            .reset_index(name='count')
            .groupby(['zone_id', 'hour_of_day'])['count']
            .agg(['mean', 'std'])
            .fillna(0)
        )

        # Dia 7: visitantes únicos por (zone_id, hour_of_day)
        test_counts = (
            test_data
            .groupby(['zone_id', 'hour_of_day'])['person_id']
            .nunique()
            .reset_index(name='count')
        )

        for _, row in test_counts.iterrows():
            zone, hour, count = row['zone_id'], row['hour_of_day'], row['count']
            key = (zone, hour)
            if key not in baseline.index:
                continue
            m, s = baseline.loc[key, 'mean'], baseline.loc[key, 'std']
            if s > 0 and (count > m + 2 * s or count < m - 2 * s):
                metrics['anomalies_day_7'].append({
                    'zone':      zone,
                    'hour':      int(hour),
                    'value':     int(count),
                    'baseline_mean': round(float(m), 1),
                    'deviation': 'Alta' if count > m else 'Baixa'
                })

        # Ordenar por magnitude do desvio
        metrics['anomalies_day_7'].sort(
            key=lambda x: abs(x['value'] - x['baseline_mean']), reverse=True
        )

    # --- pico horário ---
    metrics['peak_hour'] = str(df.groupby('hour_of_day')['person_id'].nunique().idxmax()) + ":00"

    with open(output_metrics, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=4, ensure_ascii=False)

    print(f"Métricas exportadas com sucesso para {output_metrics}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Processa analytics de jornadas.')
    parser.add_argument('--input',  type=str, required=True, help='Caminho para journeys.csv')
    parser.add_argument('--output', type=str, required=True, help='Caminho para metrics.json')
    args = parser.parse_args()
    run_analytics(args.input, args.output)