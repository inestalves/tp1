import json
import re
import ollama
import argparse


def repair_json(raw, strategy):
    """Tenta reparar JSON malformado gerado pelo LLM."""
    # Tentativa 1: parse direto
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Tentativa 2: truncar no último ']}' que fecha o array de insights
    last_valid = raw.rfind(']}')
    if last_valid != -1:
        try:
            result = json.loads(raw[:last_valid + 2] + '}')
            print(f"  JSON reparado por truncagem em {strategy}")
            return result
        except json.JSONDecodeError:
            pass

    # Tentativa 3: extrair apenas o array de insights via regex
    match = re.search(r'"insights"\s*:\s*(\[.*)', raw, re.DOTALL)
    if match:
        insights_raw = match.group(1)
        # Fechar colchete se incompleto
        open_b  = insights_raw.count('[')
        close_b = insights_raw.count(']')
        if open_b > close_b:
            insights_raw += ']' * (open_b - close_b)
        # Remover vírgula pendente antes do ]
        insights_raw = re.sub(r',\s*\]', ']', insights_raw)
        try:
            insights_list = json.loads(insights_raw)
            print(f"  JSON recuperado via regex: {len(insights_list)} insights em {strategy}")
            return {'insights': insights_list, 'resumo_executivo': []}
        except json.JSONDecodeError:
            pass

    return None


def get_insights(strategy, metrics_json, prompt_template):
    prompt = f"{prompt_template}\n\nDADOS PARA ANÁLISE:\n{metrics_json}"
    print(f"A processar {strategy}...")

    try:
        response = ollama.generate(
            model='llama3.1:8b',
            prompt=prompt,
            format='json',
            options={'temperature': 0, 'num_ctx': 8192}
        )
        raw = response['response'].strip()
        result = repair_json(raw, strategy)

        if result is None:
            print(f"  Erro: JSON irrecuperável em {strategy}")
            return {'insights': [], 'resumo_executivo': [], 'error': 'JSON inválido', 'tipo': strategy}

        if 'insights' not in result:
            result = {'insights': [], 'resumo_executivo': [], 'raw': result}

        return result

    except Exception as e:
        print(f"  Erro em {strategy}: {e}")
        return {'insights': [], 'resumo_executivo': [], 'error': str(e), 'tipo': strategy}


def run_pipeline(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            metrics_str = f.read()
    except FileNotFoundError as e:
        print(f"Erro: {e}")
        return

    # Lê prompts separados — fallback para ficheiro único se não existirem
    for name, fname in [('zero_shot', 'prompts/zero_shot.txt'), ('few_shot', 'prompts/few_shot.txt')]:
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                globals()[f'{name}_prompt'] = f.read()
        except FileNotFoundError:
            print(f"Aviso: {fname} não encontrado, a usar prompts/prompts.txt")
            with open('prompts/prompts.txt', 'r', encoding='utf-8') as f:
                globals()[f'{name}_prompt'] = f.read()

    results = {
        'zero_shot_results': get_insights('zero-shot', metrics_str, zero_shot_prompt),
        'few_shot_results':  get_insights('few-shot',  metrics_str, few_shot_prompt)
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f"\nInsights guardados em '{output_file}'")
    zs = len(results['zero_shot_results'].get('insights', []))
    fs = len(results['few_shot_results'].get('insights', []))
    print(f"  zero-shot: {zs} insights | few-shot: {fs} insights")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gera insights via LLM.')
    parser.add_argument('--input',  type=str, required=True, help='Caminho para metrics.json')
    parser.add_argument('--output', type=str, required=True, help='Caminho para insights.json')
    args = parser.parse_args()
    run_pipeline(args.input, args.output)