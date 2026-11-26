from pathlib import Path

# Diretório raiz do projeto resolvido dinamicamente
RAIZ = Path(__file__).resolve().parent

# Estrutura de pastas locais de dados e observabilidade
PASTA_DADOS_LOCAIS = RAIZ / "dados_locais"
PASTA_LOGS = RAIZ / "logs"

# Artefatos de Log
ARQUIVO_LOG_PIPELINE = PASTA_LOGS / "pipeline_dre.log"
ARQUIVO_LOG_ERROS = PASTA_LOGS / "app_errors.log"

# Snapshots locais (espelhos CSV atômicos usados pelo fallback e pelo clone.py)
SNAPSHOT_LANCAMENTOS = PASTA_DADOS_LOCAIS / "snapshot_lancamentos.csv"
SNAPSHOT_METAS = PASTA_DADOS_LOCAIS / "snapshot_metas.csv"
SNAPSHOT_ESTADOS = PASTA_DADOS_LOCAIS / "snapshot_estados.csv"


def garantir_pastas() -> None:
    """Garante que os diretórios de dados locais e logs existam."""
    PASTA_DADOS_LOCAIS.mkdir(parents=True, exist_ok=True)
    PASTA_LOGS.mkdir(parents=True, exist_ok=True)


def localizar_planilha(nome_arquivo: str) -> Path:
    """
    Procura a planilha oficial primeiro em dados_locais/ e depois na raiz.
    Retorna o caminho esperado em dados_locais/ caso ainda não exista.
    """
    caminho_dados = PASTA_DADOS_LOCAIS / nome_arquivo
    if caminho_dados.exists():
        return caminho_dados

    caminho_raiz = RAIZ / nome_arquivo
    if caminho_raiz.exists():
        return caminho_raiz

    return caminho_dados


ARQUIVO_LANCAMENTOS = localizar_planilha("Base_Lancamentos_DRE.xlsx")
ARQUIVO_METAS = localizar_planilha("Metas_e_Cadastro_UF.xlsx")
