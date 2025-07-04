import pandas as pd
import os
import logging
import argparse
from typing import List, Dict, Any, Optional
import warnings

# --- Importações dos Módulos Personalizados ---
from src.data_loader import load_crypto_data
from src.data_visualizer import plot_crypto_data
from src.data_analyzer import calculate_statistics, generate_analysis_plots, calculate_comparative_variability
from src.feature_engineering import create_moving_average_features, create_technical_features # Adicionado create_technical_features
from src.model_training import train_and_evaluate_model, compare_models # Novos módulos
from src.prediction_profit import simulate_investment_and_profit # Novo módulo
from src.statistical_tests import perform_hypothesis_test, perform_anova_analysis # Novo módulo

#Parametros vindos do config.py
from config import (
    CRIPTOS_PARA_BAIXAR as criptos_para_baixar,
    MOEDA_COTACAO as moeda_cotacao,
    TIMEFRAME as timeframe,
    OUTPUT_FOLDER as output_folder,
    PROCESSED_DATA_FOLDER as processed_data_folder,
    MODELS_FOLDER as models_folder,
    PLOTS_FOLDER as plots_folder,
    ANALYSIS_FOLDER as analysis_folder,
    PROFIT_PLOTS_FOLDER as profit_plots_folder,
    STATS_REPORTS_FOLDER as stats_reports_folder,
    DEFAULT_KFOLDS as default_kfolds,
    DEFAULT_TARGET_RETURN_PERCENT as default_target_return_percent,
    DEFAULT_POLY_DEGREE as default_poly_degree
)

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="X does not have valid feature names"
)


def setup_logging(level=logging.ERROR):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        force=True  # ← ESSENCIAL após rodar pytest
    )

def main():
    """
    Função principal que orquestra o download, a análise, a engenharia de features,
    o treinamento de modelos, a simulação de lucro e os testes estatísticos.
    """

    setup_logging()

    
    parser = argparse.ArgumentParser(description="Análise e Previsão de Preços de Criptomoedas.")
    parser.add_argument('--action', type=str, default='all',
                        choices=['all', 'download', 'analyze', 'features', 'train', 'profit', 'stats'],
                        help="Ação a ser executada: 'all', 'download', 'analyze', 'features', 'train', 'profit', 'stats'.")
    parser.add_argument('--crypto', type=str, default='all',
                        help="Símbolo da criptomoeda para processar (ex: BTC). Use 'all' para todas as configuradas.")
    parser.add_argument('--model', type=str, default='MLP',
                        choices=['MLP', 'Linear', 'Polynomial', 'RandomForest'],
                        help="Modelo a ser usado para treinamento (MLP, Linear, Polynomial, RandomForest).")
    parser.add_argument('--kfolds', type=int, default=default_kfolds,
                        help="Número de folds para K-fold cross-validation.")
    parser.add_argument('--target_return_percent', type=float, default=default_target_return_percent,
                        help="Retorno esperado médio (%) para o teste de hipótese (ex: 0.01 para 1%).")
    parser.add_argument('--poly_degree', type=int, default=default_poly_degree,
                        help="Grau máximo para a regressão polinomial (de 2 a 10).")
    parser.add_argument('--force_download', action='store_true',
                        help="Força o download dos dados mesmo que o arquivo já exista.")
    args = parser.parse_args()

    print(f">>> Executando ação: {args.action} para crypto: {args.crypto}")

   
    # Criação de pastas se não existirem
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(plots_folder, exist_ok=True)
    os.makedirs(analysis_folder, exist_ok=True)
    os.makedirs(processed_data_folder, exist_ok=True)
    os.makedirs(models_folder, exist_ok=True)
    os.makedirs(profit_plots_folder, exist_ok=True)
    os.makedirs(stats_reports_folder, exist_ok=True)

    summary_logs: List[Dict[str, Any]] = []
    all_stats: Dict[str, pd.Series] = {}
    all_dfs: Dict[str, pd.DataFrame] = {} # Armazena DataFrames brutos
    all_processed_dfs: Dict[str, pd.DataFrame] = {} # Armazena DataFrames com features

    # --- Ação: Download ---
    if args.action in ['all', 'download']:
        logging.info(f"Iniciando processo de download para {len(criptos_para_baixar)} criptomoedas.")
        print("-" * 70)

        for simbolo_base in criptos_para_baixar:
            if args.crypto != 'all' and simbolo_base != args.crypto:
                continue # Pula se uma criptomoeda específica foi solicitada e não é esta

            nome_arquivo = f"{simbolo_base.upper()}_{moeda_cotacao.upper()}_{timeframe}.csv"
            caminho_arquivo = os.path.join(output_folder, nome_arquivo)
            if not args.force_download and os.path.exists(caminho_arquivo):
                print(f"[INFO] Arquivo já existe e --force_download não foi especificado: {caminho_arquivo}")
                df = pd.read_csv(caminho_arquivo)
                all_dfs[f"{simbolo_base.upper()}_{moeda_cotacao.upper()}"] = df
                log_info = {
                    "Par de Moedas": f"{simbolo_base.upper()}/{moeda_cotacao.upper()}",
                    "Status": "Já Existente", "Total de Registros": len(df),
                    "Data de Início": df['date'].min() if 'date' in df.columns else 'N/A',
                    "Data de Fim": df['date'].max() if 'date' in df.columns else 'N/A',
                    "Preço Médio (Close)": round(df['close'].mean(), 4) if 'close' in df.columns else 0.0,
                    "Arquivo Salvo": nome_arquivo
                }
                summary_logs.append(log_info)
                continue

            df = load_crypto_data(base_symbol=simbolo_base, quote_symbol=moeda_cotacao, timeframe=timeframe)

            log_info = {
                "Par de Moedas": f"{simbolo_base.upper()}/{moeda_cotacao.upper()}",
                "Status": "Falha", "Total de Registros": 0, "Data de Início": "N/A",
                "Data de Fim": "N/A", "Preço Médio (Close)": 0.0, "Arquivo Salvo": "Nenhum"
            }

            if df is not None and not df.empty:
                nome_arquivo = f"{simbolo_base.upper()}_{moeda_cotacao.upper()}_{timeframe}.csv"
                caminho_arquivo = os.path.join(output_folder, nome_arquivo)
                df.to_csv(caminho_arquivo, index=False)

                log_info.update({
                    "Status": "Sucesso", "Total de Registros": len(df),
                    "Data de Início": df['date'].min().strftime('%Y-%m-%d'),
                    "Data de Fim": df['date'].max().strftime('%Y-%m-%d'),
                    "Preço Médio (Close)": round(df['close'].mean(), 4),
                    "Arquivo Salvo": nome_arquivo
                })
                logging.info(f"Sucesso ao processar e salvar {simbolo_base}.")
                all_dfs[f"{simbolo_base.upper()}_{moeda_cotacao.upper()}"] = df # Guarda o dataframe bruto

            summary_logs.append(log_info)

        # Relatório de Download
        print("-" * 70)
        logging.info("Gerando relatório de resumo do download...")
        df_summary = pd.DataFrame(summary_logs)
        # df_summary.to_csv(os.path.join(output_folder, "relatorio_download.csv"), index=False)
        print("\n*** Relatório Final do Download ***\n")
        print(df_summary.to_string())

    # --- Ação: Análise Estatística e Visualização ---
    if args.action in ['all', 'analyze']:
        print("-" * 70)
        logging.info("Iniciando análises estatísticas e geração de gráficos.")

        if args.action in ['all', 'analyze']:
            print("-" * 70)
            logging.info("Iniciando análises estatísticas e geração de gráficos.")

            for pair_key, df in all_dfs.items():
                # Análise Individual
                stats = calculate_statistics(df)
                all_stats[pair_key] = stats
                generate_analysis_plots(df, pair_name=pair_key, save_folder=analysis_folder)
                plot_crypto_data(df, pair_name=pair_key, save_folder=plots_folder)

            # Relatório de Análise Estatística
            print("-" * 70)
            logging.info("Gerando relatório de análise estatística descritiva...")
            df_stats = pd.DataFrame.from_dict(all_stats, orient='index')
            df_stats.to_csv(os.path.join(stats_reports_folder, "relatorio_estatistico_descritivo.csv"), index_label="Métrica")
            print("\n*** Relatório de Análise Estatística (Preço de Fechamento) ***\n")
            print(df_stats)
            print(f"\nGráficos de análise consolidados salvos na pasta: '{analysis_folder}'")

            # Relatório de Análise Comparativa
            print("-" * 70)
            logging.info("Gerando relatório de análise de variabilidade comparativa...")
            df_variability = calculate_comparative_variability(all_dfs)
            df_variability.to_csv(os.path.join(stats_reports_folder, "relatorio_comparativo_volatilidade.csv"), index=False)
            print("\n*** Análise Comparativa de Volatilidade (Ordenado pela Maior Relativa) ***\n")
            print(df_variability.to_string())
        
        # --- Ação: Engenharia de Features ---
        if args.action in ['all', 'features']:
            print("-" * 70)
            logging.info("Iniciando engenharia de features.")

            if not all_dfs and args.action not in ['download', 'analyze']: # Se não baixou/analisou agora, tenta carregar do disco
                logging.info("Carregando dados existentes para engenharia de features...")
                for simbolo_base in criptos_para_baixar:
                    if args.crypto != 'all' and simbolo_base != args.crypto:
                        continue
                    nome_arquivo = f"{simbolo_base.upper()}_{moeda_cotacao.upper()}_{timeframe}.csv"
                    caminho_arquivo = os.path.join(output_folder, nome_arquivo)
                    if os.path.exists(caminho_arquivo):
                        df = load_crypto_data(simbolo_base, moeda_cotacao, timeframe)
                        if df is not None:
                            all_dfs[f"{simbolo_base.upper()}_{moeda_cotacao.upper()}"] = df
                        else:
                            logging.warning(f"Falha ao carregar dados para análise: {simbolo_base}")
                    else:
                        logging.warning(f"Arquivo não encontrado para engenharia de features: {caminho_arquivo}")

            if all_dfs:
                for pair_key, df in all_dfs.items():
                    if args.crypto != 'all' and pair_key.split('_')[0] != args.crypto:
                        continue

                    logging.info(f"Criando features para {pair_key}...")
                    # Exemplo de janelas para médias móveis e desvio padrão
                    windows = [7, 14, 30]
                    df_featured = create_moving_average_features(df.copy(), windows) # Passa uma cópia para não modificar o original

                    # Adicionar features técnicas (se implementadas)
                    df_featured = create_technical_features(df_featured.copy())

                    # Salva o DataFrame com features
                    processed_filename = f"featured_{pair_key}.csv"
                    processed_filepath = os.path.join(processed_data_folder, processed_filename)
                    df_featured.to_csv(processed_filepath, index=False)
                    all_processed_dfs[pair_key] = df_featured
                    logging.info(f"Features para {pair_key} salvas em: {processed_filepath}")
            else:
                logging.warning("Nenhum dado disponível para engenharia de features.")

        # --- Ação: Treinamento de Modelos ---
        if args.action in ['all', 'train']:
            print("-" * 70)
            logging.info("Iniciando treinamento e avaliação de modelos.")

            if not all_processed_dfs and args.action not in ['download', 'analyze', 'features']: # Tenta carregar dados processados
                logging.info("Carregando dados processados para treinamento de modelos...")
                for simbolo_base in criptos_para_baixar:
                    if args.crypto != 'all' and simbolo_base != args.crypto:
                        continue
                    pair_key = f"{simbolo_base.upper()}_{moeda_cotacao.upper()}"
                    processed_filename = f"featured_{pair_key}.csv"
                    processed_filepath = os.path.join(processed_data_folder, processed_filename)
                    if os.path.exists(processed_filepath):
                        df_featured = pd.read_csv(processed_filepath)
                        df_featured['date'] = pd.to_datetime(df_featured['date'])
                        all_processed_dfs[pair_key] = df_featured
                    else:
                        logging.warning(f"Arquivo de features não encontrado para treinamento: {processed_filepath}")

            if all_processed_dfs:
                for pair_key, df_featured in all_processed_dfs.items():
                    if args.crypto != 'all' and pair_key.split('_')[0] != args.crypto:
                        continue

                    logging.info(f"Treinando e avaliando modelos para {pair_key}...")
                    # Define as features (X) e o target (y) com variáveis selecionadas
                    selected_features = [
                        'high', 'low', 'sma_7', 'sma_14', 'sma_30',
                        'close_lag5', 'macd', 'macd_signal', 'macd_diff',
                        'bb_upper', 'bb_lower', 'bb_mavg', 'daily_return'
                    ]
                    # Filtra apenas as colunas presentes no DataFrame (evita erro caso alguma esteja ausente)
                    features = [col for col in selected_features if col in df_featured.columns]
                    X = df_featured[features]
                    y = df_featured['close']

                    # Treina e avalia o modelo especificado
                    train_and_evaluate_model(
                        X, y,
                        model_type=args.model,
                        kfolds=args.kfolds,
                        pair_name=pair_key,
                        models_folder=models_folder,
                        poly_degree=args.poly_degree
                    )

                    # Comparar MLP com outros regressores (se for a ação 'all' ou 'train')
                    if args.action in ['all', 'train']:
                        logging.info(f"Comparando modelos para {pair_key}...")
                        compare_models(
                            X, y,
                            kfolds=args.kfolds,
                            pair_name=pair_key,
                            plots_folder=analysis_folder, # Salva gráficos de comparação aqui
                            poly_degree=args.poly_degree
                        )
            else:
                logging.warning("Nenhum dado processado disponível para treinamento de modelos.")

        # --- Ação: Simulação de Lucro ---
        if args.action in ['all', 'profit']:
            print("-" * 70)
            logging.info("Iniciando simulação de lucro.")

            if not all_processed_dfs and args.action not in ['download', 'analyze', 'features', 'train']:
                logging.info("Carregando dados processados para simulação de lucro...")
                for simbolo_base in criptos_para_baixar:
                    if args.crypto != 'all' and simbolo_base != args.crypto:
                        continue
                    pair_key = f"{simbolo_base.upper()}_{moeda_cotacao.upper()}"
                    processed_filename = f"featured_{pair_key}.csv"
                    processed_filepath = os.path.join(processed_data_folder, processed_filename)
                    if os.path.exists(processed_filepath):
                        df_featured = pd.read_csv(processed_filepath)
                        df_featured['date'] = pd.to_datetime(df_featured['date'])
                        all_processed_dfs[pair_key] = df_featured
                    else:
                        logging.warning(f"Arquivo de features não encontrado para simulação de lucro: {processed_filepath}")

            if all_processed_dfs:
                for pair_key, df_featured in all_processed_dfs.items():
                    if args.crypto != 'all' and pair_key.split('_')[0] != args.crypto:
                        continue

                    logging.info(f"Simulando lucro para {pair_key}...")
                    # Define as features (X) e o target (y)
                    # Define as features (X) e o target (y) com variáveis selecionadas
                    selected_features = [
                        'high', 'low', 'sma_7', 'sma_14', 'sma_30',
                        'close_lag5', 'macd', 'macd_signal', 'macd_diff',
                        'bb_upper', 'bb_lower', 'bb_mavg', 'daily_return'
                    ]
                    # Filtra apenas as colunas presentes no DataFrame (evita erro caso alguma esteja ausente)
                    features = [col for col in selected_features if col in df_featured.columns]
                    X = df_featured[features]
                    y = df_featured['close']
                    dates = df_featured['date']

                    # Simula o investimento e plota o lucro
                    simulate_investment_and_profit(
                        X, y, dates,
                        pair_name=pair_key,
                        models_folder=models_folder,
                        profit_plots_folder=profit_plots_folder,
                        initial_investment=1000.0
                    )
            else:
                logging.warning("Nenhum dado processado disponível para simulação de lucro.")

        # --- Ação: Testes Estatísticos Avançados (Hipótese e ANOVA) ---
        if args.action in ['all', 'stats']:
            print("-" * 70)
            logging.info("Iniciando testes estatísticos avançados.")

            if not all_dfs and args.action not in ['download', 'analyze', 'features', 'train', 'profit']:
                logging.info("Carregando dados existentes para testes estatísticos...")
                for simbolo_base in criptos_para_baixar:
                    if args.crypto != 'all' and simbolo_base != args.crypto:
                        continue
                    nome_arquivo = f"{simbolo_base.upper()}_{moeda_cotacao.upper()}_{timeframe}.csv"
                    caminho_arquivo = os.path.join(output_folder, nome_arquivo)
                    if os.path.exists(caminho_arquivo):
                        df = load_crypto_data(simbolo_base, moeda_cotacao, timeframe)
                        if df is not None:
                            all_dfs[f"{simbolo_base.upper()}_{moeda_cotacao.upper()}"] = df
                        else:
                            logging.warning(f"Falha ao carregar dados para análise: {simbolo_base}")
                    else:
                        logging.warning(f"Arquivo não encontrado para testes estatísticos: {caminho_arquivo}")

            if all_dfs:
                # Teste de Hipótese para cada criptomoeda
                print("-" * 70)
                logging.info("Realizando teste de hipótese para retorno esperado médio...")
                for pair_key, df in all_dfs.items():
                    if args.crypto != 'all' and pair_key.split('_')[0] != args.crypto:
                        continue
                    logging.info(f"Teste de hipótese para {pair_key} com retorno alvo de {args.target_return_percent*100:.2f}%")
                    perform_hypothesis_test(df, pair_key, args.target_return_percent, stats_reports_folder)

                # Análise ANOVA para comparar retornos médios diários
                print("-" * 70)
                logging.info("Realizando análise ANOVA para retornos médios diários...")
                
                if not all_processed_dfs:
                    logging.info("Carregando dados processados para testes estatísticos (ANOVA)...")
                    for simbolo_base in criptos_para_baixar:
                        if args.crypto != 'all' and simbolo_base != args.crypto:
                            continue
                        pair_key = f"{simbolo_base.upper()}_{moeda_cotacao.upper()}"
                        processed_filename = f"featured_{pair_key}.csv"
                        processed_filepath = os.path.join(processed_data_folder, processed_filename)
                        if os.path.exists(processed_filepath):
                            df_featured = pd.read_csv(processed_filepath)
                            df_featured['date'] = pd.to_datetime(df_featured['date'])
                            all_processed_dfs[pair_key] = df_featured
                        else:
                            logging.warning(f"Arquivo de features não encontrado para ANOVA: {processed_filepath}")
                
                perform_anova_analysis(all_processed_dfs, stats_reports_folder)
            else:
                logging.warning("Nenhum dado disponível para testes estatísticos avançados.")

        print("\nFLUXO DE TRABALHO CONCLUÍDO!")

if __name__ == '__main__':
    main()
