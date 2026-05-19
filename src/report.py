import json
from datetime import datetime
import re
import argparse


def generate_markdown(input_file, output_file, metrics_file='output/metrics.json'):
    try:
        with open(metrics_file, 'r', encoding='utf-8') as f:
            metrics = json.load(f)

        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            last_brace = content.rfind('}')
            if last_brace != -1:
                content = content[:last_brace + 1]
            all_insights = json.loads(content)

        data = all_insights.get("few_shot_results", {})
        traffic = metrics.get('traffic', {})
        zones = metrics.get('zones', {})
        real_peak_hour = metrics.get('peak_hour', '17:00')

        # Identificar a zona com maior tráfego real via código
        top_zone_id = max(zones, key=lambda x: zones[x].get('total_traffic', 0)) if zones else "Z_C2"

        # --- 1. RESUMO EXECUTIVO (Limpeza de redundâncias) ---
        resumo_raw = data.get('resumo_executivo', [])
        resumo_limpo = []
        for item in resumo_raw:
            txt = str(item).strip("- ")
            # Substitui "frescos" mas evita criar "Zona de zona"
            txt = txt.replace("Zona de frescos", f"A zona {top_zone_id}")
            txt = txt.replace("zona de frescos", f"zona {top_zone_id}")
            txt = txt.replace("frescos", f"zona {top_zone_id}")
            # Garante a hora correta
            txt = re.sub(r'\d{1,2}h', real_peak_hour, txt)
            resumo_limpo.append(txt)

        md = f"# 🏪 Relatório Semanal de Performance de Loja\n"
        md += f"*Gerado em: {datetime.now().strftime('%d/%m/%Y')}*\n\n"

        md += "## 1. Resumo Executivo\n"
        for item in resumo_limpo[:3]:
            md += f"* {item}\n"
        md += "\n---\n"

        # --- 2. PERFORMANCE DE TRÁFEGO ---
        daily_data = traffic.get('unique_visitors_per_day', {})
        dia_mais = max(daily_data, key=daily_data.get) if daily_data else "N/A"
        md += "## 2. Performance de Tráfego\n"
        md += f"Afluência total: **{traffic.get('total_visitors', 'N/A')} visitantes**.\n"
        md += f"* **Hora de Pico:** {real_peak_hour}.\n"
        md += f"* **Dia mais movimentado:** {dia_mais}.\n\n"

        # --- 3. ANÁLISE DE ZONAS (Correção de IDs técnicos) ---
        md += "## 3. Análise de Zonas\n"
        md += "### Top 3 Zonas (Desempenho)\n"
        for code, info in sorted(zones.items(), key=lambda x: x[1].get('total_traffic', 0), reverse=True)[:3]:
            md += f"* **{code}:** {info.get('total_traffic')} visitantes.\n"

        md += "\n### Zonas Problemáticas (Ação Imediata)\n"
        for ins in [i for i in data.get('insights', []) if 'imediata' in (i.get('urgencia') or '').lower()][:2]:
            rec = str(ins.get('recomendacao') or ins.get('recommendacao') or '')
            z_id = ins.get('id', '')

            # Se o ID for técnico (INS_...), tentamos extrair a zona mencionada no texto
            if "INS_" in z_id:
                if "tráfego" in ins.get('titulo', '').lower() or "tráfego" in rec.lower():
                    z_id = top_zone_id
                    rec = rec.replace("Z_S3", top_zone_id).replace("10h", real_peak_hour)
                elif "Z_N4" in rec or "anomalia" in rec.lower():
                    z_id = "Z_N4"

            md += f"**Zona: {z_id}**\n"
            md += f"* **Hipótese:** {ins.get('implicacao')}\n"
            md += f"* **Ação:** {rec}\n\n"

        # --- 4. FUNIL DE CLIENTES ---
        md += "## 4. Funil de Clientes\n"
        conv = metrics.get('funnel', {}).get('conversion_to_checkout', 0)
        md += f"Taxa de Conversão: **{conv * 100:.1f}%**.\n"
        md += f"* **Ponto de Perda:** Identificou-se que **{(1 - conv) * 100:.1f}%** dos visitantes abandonam a jornada.\n"
        md += f"* **Perfil:** {metrics.get('demographics', {}).get('top_drop_profile', 'Adultos/Seniores')}.\n\n"

        # --- 5. ANOMALIAS ---
        md += "## 5. Anomalias da Semana\n"
        for a in metrics.get('anomalies_day_7', [])[:3]:
            md += f"### Evento em {a.get('zone')}\n"
            md += f"* **Magnitude:** Desvio {a.get('deviation')}.\n"
            md += f"* **Ação:** Inspeção técnica e verificação de hardware.\n\n"

        # --- 6. RECOMENDAÇÕES (Sincronizadas) ---
        md += "\n## 6. Recomendações (Prioridade)\n"
        final_recs = []
        for ins in sorted(data.get('insights', []),
                          key=lambda x: 0 if 'imediata' in (x.get('urgencia') or '').lower() else 1):
            r = ins.get('recomendacao') or ins.get('recommendacao') or 'N/A'
            r = str(r).replace("Z_S3", top_zone_id).replace("10h", real_peak_hour).replace("10:00", real_peak_hour)
            urgencia = (ins.get('urgencia') or 'esta_semana').upper()
            line = f"**[{urgencia}]** {r}"
            if line not in final_recs:
                final_recs.append(line)

        for i, r in enumerate(final_recs[:3]):
            md += f"{i + 1}. {r}\n"

        # Escrita no ficheiro definido pelo argumento --output
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"Relatório '{output_file}' gerado")

    except Exception as e:
        print(f"Erro: {e}")


if __name__ == "__main__":
    # Configuração dos argumentos do terminal
    parser = argparse.ArgumentParser(description='Gera o relatório Markdown final.')
    parser.add_argument('--input', type=str, required=True, help='Caminho para o ficheiro insights.json')
    parser.add_argument('--output', type=str, required=True, help='Caminho para o ficheiro semanal .md')
    parser.add_argument('--metrics', type=str, default='output/metrics.json',
                        help='Caminho para metrics.json (default: output/metrics.json)')

    args = parser.parse_args()

    generate_markdown(args.input, args.output, args.metrics)