import json
import ollama
import sys
import argparse

def get_insights_by_strategy(strategy, metrics_json, base_prompt):
    prompt = f"{base_prompt}\n\nDados completos: \n{metrics_json}\n\n"
    prompt += "Tarefa: Executa Estratégia A (zero-shot)." if strategy == "zero-shot" else "Tarefa: Executa Estratégia B (few-shot)."

    print(f" Processando {strategy} ... ")

    try:
        response = ollama.generate(
            model='phi3:mini',
            prompt=prompt,
            format='json',
            options={
                'temperature': 0,
            }
        )
        return json.loads(response['response'])
    except Exception as e:
        print(f"Erro em {strategy}: {e}")
        return {"error": "Falha na geração", "tipo": strategy}

def run_pipeline(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            metrics_str = f.read()
        with open('prompts/prompts.txt', 'r', encoding='utf-8') as f:
            template = f.read()
    except FileNotFoundError as e:
        print(f"Erro: Ficheiro não encontrado. {e}")
        return

    results = {
        "zero_shot_results": get_insights_by_strategy("zero-shot", metrics_str, template),
        "few_shot_results": get_insights_by_strategy("few-shot", metrics_str, template)
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f"\n Sucesso! Insights guardados em '{output_file}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gera insights via LLM.')
    parser.add_argument('--input', type=str, required=True, help='Caminho para o ficheiro metrics.json')
    parser.add_argument('--output', type=str, required=True, help='Caminho para o ficheiro insights.json')
    args = parser.parse_args()
    run_pipeline(args.input, args.output)