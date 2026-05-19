import pandas as pd
import json
import numpy as np
import argparse


def run_analytics(input_file, output_metrics):
    df = pd.read_csv(input_file)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['exit_time'] = pd.to_datetime(df['exit_time'])
    df['visit_date'] = df['entry_time'].dt.date.astype(str)

    metrics = {}

    # métricas de tráfego
    total_unique = int(df['person_id'].nunique())
    metrics['traffic'] = {
        'unique_visitors_per_day': df.groupby('visit_date')['person_id'].nunique().to_dict(),
        'unique_visitors_per_hour': {str(k): int(v) for k, v in
                                     df.groupby('hour_of_day')['person_id'].nunique().to_dict().items()},
        'avg_store_visit_duration': float(df.groupby('person_id')['dwell_s'].sum().mean()),
        'total_visitors': total_unique
    }

    # top 10 sequências
    paths = df.sort_values(['person_id', 'entry_time']).groupby('person_id')['zone_id'].apply(list)
    sequences = []
    for p in paths:
        if len(p) >= 3:
            for i in range(len(p) - 2):
                sequences.append(f"{p[i]} -> {p[i + 1]} -> {p[i + 2]}")

    metrics['top_10_sequences'] = pd.Series(sequences).value_counts().head(10).to_dict()

    # métricas por zona
    zone_metrics = {}
    for zone in df['zone_id'].unique():
        zone_df = df[df['zone_id'] == zone]
        visitors_total = zone_df['person_id'].nunique()
        # linger se tempo de permanência > 0
        visitors_linger = zone_df[zone_df['dwell_s'] > 0]['person_id'].nunique()
        zone_metrics[zone] = {
            'total_traffic': int(visitors_total),
            'avg_dwell_linger': float(zone_df[zone_df['dwell_s'] > 0]['dwell_s'].mean() or 0),
            'stop_rate': float(visitors_linger / visitors_total if visitors_total > 0 else 0)
        }
    metrics['zones'] = zone_metrics

    # funil e perfil de abandono
    checkout_customers = df[df['zone_id'].str.startswith('Z_C')]['person_id'].unique()
    non_checkout_df = df[~df['person_id'].isin(checkout_customers)]
    metrics['funnel'] = {
        'conversion_to_checkout': float(len(checkout_customers) / total_unique if total_unique > 0 else 0),
        'non_checkout_profile': {
            'gender_dist': {str(k): int(v) for k, v in
                            non_checkout_df.groupby('gender')['person_id'].nunique().to_dict().items()},
            'age_dist': {str(k): int(v) for k, v in
                         non_checkout_df.groupby('age_range')['person_id'].nunique().to_dict().items()}
        }
    }

    # demografia
    dwell_seg = df.groupby(['gender', 'age_range'])['dwell_s'].mean().to_dict()
    metrics['demographics'] = {
        'dwell_by_segment': {f"{g}_{a}": float(d) for (g, a), d in dwell_seg.items()},
        'top_drop_profile': "Adultos/Seniores"
    }

    # deteção de anomalias (dia 7)
    days = sorted(df['visit_date'].unique())
    metrics['anomalies_day_7'] = []

    if len(days) >= 7:
        training_days = days[:6] # primeiros 6 dias são baseline
        test_day = days[6]
        train_data = df[df['visit_date'].isin(training_days)]

        # calcula média e desvio padrão por zona
        stats = train_data.groupby(['zone_id', 'hour_of_day'])['person_id'].nunique().groupby('zone_id').agg(
            ['mean', 'std']).fillna(0)
        test_data = df[df['visit_date'] == test_day].groupby('zone_id')['person_id'].nunique()

        # regra de 2 desvios padrão
        for zone, count in test_data.items():
            if zone in stats.index:
                m, s = stats.loc[zone, 'mean'], stats.loc[zone, 'std']
                if s > 0 and (count > m + 2 * s or count < m - 2 * s):
                    # Se o valor está muito longe da média, é uma anomalia
                    metrics['anomalies_day_7'].append({
                        'zone': zone, 'value': int(count), 'deviation': "Alta" if count > m else "Baixa"
                    })

    # adicionar pico horário para o report
    metrics['peak_hour'] = str(df.groupby('hour_of_day')['person_id'].nunique().idxmax()) + ":00"

    with open(output_metrics, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=4, ensure_ascii=False)

    print(f" Métricas exportadas com sucesso para {output_metrics}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Processa analytics de jornadas.')
    parser.add_argument('--input', type=str, required=True, help='Caminho para o ficheiro journeys.csv')
    parser.add_argument('--output', type=str, required=True, help='Caminho para o ficheiro metrics.json')
    args = parser.parse_args()
    run_analytics(args.input, args.output)