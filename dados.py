from datetime import datetime
from pathlib import Path
import time
import unicodedata

import pandas as pd
import streamlit as st

from alertas import notificar_admin, registrar_log
from caminhos import (
    SNAPSHOT_ESTADOS,
    SNAPSHOT_LANCAMENTOS,
    SNAPSHOT_METAS,
    garantir_pastas,
    localizar_planilha,
)

garantir_pastas()

# Contratos mínimos de colunas (Data Quality Gate)
SCHEMA_LANCAMENTOS = [
    "ID_Lancamento", "Data", "Mês_Num", "UF", "Estado",
    "Região", "Grupo_DRE", "Natureza", "Canal", "Descrição", "Valor",
]
SCHEMA_METAS = [
    "UF", "Região", "Mês", "Meta_Receita",
    "Teto_Custos_Despesas", "Meta_Margem_Pct",
]
SCHEMA_ESTADOS = [
    "UF", "Estado", "Região", "Lat", "Lon",
    "Gerente_Regional", "Modal_Principal",
]

STATUS_PIPELINE: dict = {
    "estado": "ok",
    "fonte": "Excel Oficial",
    "quando": None,
    "linhas_lancamentos": 0,
    "latencia_ms": 0.0,
}


def _chave_limpa(texto: str) -> str:
    """Remove acentos, espaços e caixa para comparar nomes de abas com tolerância."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    )
    return sem_acento.lower().replace(" ", "").replace("_", "").strip()


def _ler_aba_inteligente(
    caminho_excel: Path, aba_esperada: str, colunas_esperadas: list[str]
) -> pd.DataFrame:
    """
    1. Tenta ler a aba pelo nome exato ou equivalente sem acento/espaço.
    2. Se a aba tiver sido renomeada (ex.: 'Planilha1'), procura qual aba contém as colunas do contrato.
    3. Se não achar, informa claramente quais abas existem dentro do arquivo.
    """
    with pd.ExcelFile(caminho_excel, engine="openpyxl") as xls:
        abas_existentes = xls.sheet_names

        # 1. Busca por nome exato ou normalizado
        alvo = _chave_limpa(aba_esperada)
        for aba in abas_existentes:
            if aba == aba_esperada or _chave_limpa(aba) == alvo:
                return xls.parse(sheet_name=aba)

        # 2. Busca por assinatura de colunas em todas as abas do arquivo
        conjunto_esperado = {c.strip() for c in colunas_esperadas}
        for aba in abas_existentes:
            amostra = xls.parse(sheet_name=aba, nrows=2)
            cols_aba = {str(c).strip() for c in amostra.columns}
            if conjunto_esperado.issubset(cols_aba):
                registrar_log(
                    f"Aba '{aba_esperada}' não encontrada em '{caminho_excel.name}'; "
                    f"usando aba compatível '{aba}'.",
                    nivel="warning",
                    origem="ETL",
                )
                return xls.parse(sheet_name=aba)

    raise ValueError(
        f"A aba '{aba_esperada}' não existe em '{caminho_excel.name}'. "
        f"Abas encontradas neste arquivo: {abas_existentes}"
    )


def _ler_csv_seguro(caminho: Path) -> pd.DataFrame:
    """
    Lê snapshot CSV tolerando diferentes encodings do Windows (UTF-8, CP1252, Latin-1)
    e detectando arquivos .xlsx que foram apenas renomeados para .csv.
    """
    if not caminho.exists() or caminho.stat().st_size == 0:
        return pd.DataFrame()

    # Assinatura 'PK\x03\x04' indica arquivo Excel (.xlsx / ZIP) renomeado para .csv
    assinatura = caminho.read_bytes()[:4]
    if assinatura == b"PK\x03\x04":
        registrar_log(
            f"O arquivo '{caminho.name}' é um Excel binário renomeado para .csv; lendo via openpyxl.",
            nivel="warning",
            origem="ETL",
        )
        return pd.read_excel(caminho, engine="openpyxl")

    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(caminho, encoding=enc, sep=None, engine="python")
            if not df.empty:
                return df
        except UnicodeDecodeError:
            continue
        except Exception:
            break

    return pd.DataFrame()


def _validar_schema(df: pd.DataFrame, colunas_obrigatorias: list[str], nome_tabela: str) -> None:
    """Garante que todas as colunas críticas existam antes de transformar os dados."""
    faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"Quebra de contrato na base '{nome_tabela}'. Colunas ausentes: {faltantes} | "
            f"Colunas encontradas: {list(df.columns)}"
        )


def _converter_numero_br(serie: pd.Series) -> pd.Series:
    """Converte série numérica ou texto monetário ('R$ 1.234,50') para float seguro."""
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce").fillna(0.0)

    texto = serie.astype(str).str.replace("R$", "", regex=False).str.strip()
    tem_virgula = texto.str.contains(",", na=False)
    if tem_virgula.any():
        texto = texto.mask(
            tem_virgula,
            texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
        )
    return pd.to_numeric(texto, errors="coerce").fillna(0.0)


def _normalizar_lancamentos(df_bruto: pd.DataFrame) -> pd.DataFrame:
    df = df_bruto.copy()
    df.columns = df.columns.astype(str).str.strip()
    _validar_schema(df, SCHEMA_LANCAMENTOS, "Lancamentos")

    for col_txt in ("ID_Lancamento", "UF", "Estado", "Região", "Grupo_DRE", "Natureza", "Canal", "Descrição"):
        df[col_txt] = df[col_txt].astype(str).str.strip()
    df["UF"] = df["UF"].str.upper()

    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"]).copy()

    df["Mês_Num"] = pd.to_numeric(df["Mês_Num"], errors="coerce").fillna(df["Data"].dt.month).astype(int)
    df["Valor"] = _converter_numero_br(df["Valor"]).astype(float)

    tem_id = df["ID_Lancamento"].ne("") & df["ID_Lancamento"].ne("NAN")
    if tem_id.any():
        com_id = df[tem_id].drop_duplicates(subset=["ID_Lancamento"], keep="last")
        df = pd.concat([com_id, df[~tem_id]], ignore_index=True)

    return df.sort_values(["Data", "UF"]).reset_index(drop=True)


def _normalizar_metas(df_bruto: pd.DataFrame) -> pd.DataFrame:
    df = df_bruto.copy()
    df.columns = df.columns.astype(str).str.strip()
    _validar_schema(df, SCHEMA_METAS, "Metas_UF")

    df["UF"] = df["UF"].astype(str).str.strip().str.upper()
    df["Região"] = df["Região"].astype(str).str.strip()
    df["Mês"] = pd.to_numeric(df["Mês"], errors="coerce").fillna(0).astype(int)
    df["Meta_Receita"] = _converter_numero_br(df["Meta_Receita"]).astype(float)
    df["Teto_Custos_Despesas"] = _converter_numero_br(df["Teto_Custos_Despesas"]).astype(float)
    df["Meta_Margem_Pct"] = _converter_numero_br(df["Meta_Margem_Pct"]).astype(float)

    return df.drop_duplicates(subset=["UF", "Mês"], keep="last").reset_index(drop=True)


def _normalizar_estados(df_bruto: pd.DataFrame) -> pd.DataFrame:
    df = df_bruto.copy()
    df.columns = df.columns.astype(str).str.strip()
    _validar_schema(df, SCHEMA_ESTADOS, "Cadastro_Estados")

    for col_txt in ("UF", "Estado", "Região", "Gerente_Regional", "Modal_Principal"):
        df[col_txt] = df[col_txt].astype(str).str.strip()
    df["UF"] = df["UF"].str.upper()
    df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    df["Lon"] = pd.to_numeric(df["Lon"], errors="coerce")

    return df.dropna(subset=["Lat", "Lon"]).drop_duplicates(subset=["UF"], keep="last").reset_index(drop=True)


def salvar_snapshot_atomico(df: pd.DataFrame, destino: Path) -> None:
    """Grava arquivo temporário (.tmp) e substitui o CSV final de forma atômica."""
    if df.empty:
        return
    try:
        temporario = destino.with_suffix(".tmp")
        df.to_csv(temporario, index=False, encoding="utf-8-sig")
        temporario.replace(destino)
    except Exception as e:
        notificar_admin(f"Falha ao gravar snapshot {destino.name}", e, origem="ETL")


def ler_snapshots_locais() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, datetime | None]:
    """Lê os espelhos CSV de forma isolada; nunca lança exceção não tratada."""
    arquivos = (SNAPSHOT_LANCAMENTOS, SNAPSHOT_METAS, SNAPSHOT_ESTADOS)
    if not all(p.exists() for p in arquivos):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None

    try:
        df_lanc = _ler_csv_seguro(SNAPSHOT_LANCAMENTOS)
        df_metas = _ler_csv_seguro(SNAPSHOT_METAS)
        df_estados = _ler_csv_seguro(SNAPSHOT_ESTADOS)

        if df_lanc.empty or df_metas.empty or df_estados.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None

        df_lanc = _normalizar_lancamentos(df_lanc)
        df_metas = _normalizar_metas(df_metas)
        df_estados = _normalizar_estados(df_estados)

        idade = datetime.fromtimestamp(SNAPSHOT_LANCAMENTOS.stat().st_mtime)
        return df_lanc, df_metas, df_estados, idade
    except Exception as erro_snap:
        notificar_admin("Snapshots CSV locais inválidos ou corrompidos", erro_snap, origem="ETL")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None


@st.cache_data(ttl=600, max_entries=4, show_spinner="Executando pipeline de dados DRE...")
def carregar_bases_oficiais() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    inicio = time.perf_counter()
    arq_lanc = localizar_planilha("Base_Lancamentos_DRE.xlsx")
    arq_metas = localizar_planilha("Metas_e_Cadastro_UF.xlsx")

    try:
        if not arq_lanc.exists() or not arq_metas.exists():
            raise FileNotFoundError(
                f"Planilhas oficiais ausentes em '{arq_lanc.parent}': "
                f"{arq_lanc.name} / {arq_metas.name}."
            )

        bruto_lanc = _ler_aba_inteligente(arq_lanc, "Lancamentos", SCHEMA_LANCAMENTOS)
        bruto_metas = _ler_aba_inteligente(arq_metas, "Metas_UF", SCHEMA_METAS)
        bruto_estados = _ler_aba_inteligente(arq_metas, "Cadastro_Estados", SCHEMA_ESTADOS)

        if bruto_lanc.empty:
            raise RuntimeError("A aba 'Lancamentos' retornou zero registros.")

        df_lanc = _normalizar_lancamentos(bruto_lanc)
        df_metas = _normalizar_metas(bruto_metas)
        df_estados = _normalizar_estados(bruto_estados)

        salvar_snapshot_atomico(df_lanc, SNAPSHOT_LANCAMENTOS)
        salvar_snapshot_atomico(df_metas, SNAPSHOT_METAS)
        salvar_snapshot_atomico(df_estados, SNAPSHOT_ESTADOS)

        duracao_ms = (time.perf_counter() - inicio) * 1000.0
        STATUS_PIPELINE.update({
            "estado": "ok",
            "fonte": "Excel Oficial",
            "quando": datetime.now(),
            "linhas_lancamentos": len(df_lanc),
            "latencia_ms": round(duracao_ms, 1),
        })
        registrar_log(
            f"Carga Excel concluída com sucesso | {len(df_lanc)} lançamentos, "
            f"{len(df_estados)} UFs | {duracao_ms:.1f} ms",
            origem="ETL",
        )
        return df_lanc, df_metas, df_estados

    except Exception as erro_excel:
        notificar_admin(
            "Falha na leitura/validação do Excel oficial. Ativando fallback para snapshot CSV.",
            erro_excel,
            origem="ETL",
        )
        df_lanc, df_metas, df_estados, idade = ler_snapshots_locais()
        if not df_lanc.empty:
            duracao_ms = (time.perf_counter() - inicio) * 1000.0
            STATUS_PIPELINE.update({
                "estado": "backup",
                "fonte": "Snapshot CSV Local",
                "quando": idade,
                "linhas_lancamentos": len(df_lanc),
                "latencia_ms": round(duracao_ms, 1),
            })
            registrar_log(
                f"Operando em fallback com snapshot CSV de {idade} ({len(df_lanc)} linhas).",
                nivel="warning",
                origem="ETL",
            )
            return df_lanc, df_metas, df_estados

        st.error(
            f"❌ **Erro ao carregar as planilhas oficiais:** {erro_excel}\n\n"
            "Verifique se `Base_Lancamentos_DRE.xlsx` e `Metas_e_Cadastro_UF.xlsx` estão corretos "
            "na pasta `dados_locais/`."
        )
        st.stop()


# ==============================================================================
# TRANSFORMAÇÕES ANALÍTICAS E REGRAS DE NEGÓCIO (CAMADA GOLD)
# ==============================================================================
def aplicar_filtros_globais(
    df_lancamentos: pd.DataFrame,
    df_metas: pd.DataFrame,
    meses_sel: list[int],
    regiao_sel: str,
    uf_sel: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df_filtrado = df_lancamentos[df_lancamentos["Mês_Num"].isin(meses_sel)].copy()
    df_metas_filt = df_metas[df_metas["Mês"].isin(meses_sel)].copy()
    df_evolucao = df_lancamentos.copy()

    if regiao_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado["Região"] == regiao_sel]
        df_metas_filt = df_metas_filt[df_metas_filt["Região"] == regiao_sel]
        df_evolucao = df_evolucao[df_evolucao["Região"] == regiao_sel]

    if uf_sel != "Todos (Consolidado)":
        df_filtrado = df_filtrado[df_filtrado["UF"] == uf_sel]
        df_metas_filt = df_metas_filt[df_metas_filt["UF"] == uf_sel]
        df_evolucao = df_evolucao[df_evolucao["UF"] == uf_sel]

    return df_filtrado, df_metas_filt, df_evolucao


def calcular_kpis_dre(df_filtrado: pd.DataFrame, df_metas_filt: pd.DataFrame) -> dict[str, float]:
    resumo = df_filtrado.groupby("Grupo_DRE")["Valor"].sum() if not df_filtrado.empty else pd.Series(dtype=float)

    receita_bruta = float(resumo.get("Receita Bruta", 0.0))
    impostos = float(resumo.get("Impostos", 0.0))
    cmv = float(resumo.get("CMV", 0.0))
    frete = float(resumo.get("Frete & Logística", 0.0))
    desp_op = float(resumo.get("Desp. Operacionais", 0.0))

    custos_totais = impostos + cmv + frete + desp_op
    lucro_liquido = receita_bruta - custos_totais
    margem_liquida = (lucro_liquido / receita_bruta * 100.0) if receita_bruta > 0 else 0.0

    meta_receita = float(df_metas_filt["Meta_Receita"].sum()) if not df_metas_filt.empty else 0.0
    pct_meta_rec = (receita_bruta / meta_receita * 100.0) if meta_receita > 0 else 0.0
    meta_margem = float(df_metas_filt["Meta_Margem_Pct"].mean() * 100.0) if not df_metas_filt.empty else 0.0
    desvio_margem = margem_liquida - meta_margem

    teto_custos = float(df_metas_filt["Teto_Custos_Despesas"].sum()) if not df_metas_filt.empty else 0.0
    saldo_teto = teto_custos - custos_totais
    pct_teto = (custos_totais / teto_custos * 100.0) if teto_custos > 0 else 0.0
    peso_frete = (frete / receita_bruta * 100.0) if receita_bruta > 0 else 0.0

    return {
        "receita_bruta": receita_bruta,
        "impostos": impostos,
        "cmv": cmv,
        "frete": frete,
        "desp_op": desp_op,
        "custos_totais": custos_totais,
        "lucro_liquido": lucro_liquido,
        "margem_liquida": margem_liquida,
        "meta_receita": meta_receita,
        "pct_meta_rec": pct_meta_rec,
        "meta_margem": meta_margem,
        "desvio_margem": desvio_margem,
        "teto_custos": teto_custos,
        "saldo_teto": saldo_teto,
        "pct_teto": pct_teto,
        "peso_frete": peso_frete,
    }


def consolidar_dados_mapa(
    df_filtrado: pd.DataFrame,
    df_metas_filt: pd.DataFrame,
    df_estados: pd.DataFrame,
) -> pd.DataFrame:
    if df_filtrado.empty:
        return pd.DataFrame()

    piv_uf = df_filtrado.pivot_table(
        index="UF", columns="Grupo_DRE", values="Valor", aggfunc="sum", fill_value=0.0
    ).reset_index()

    for col_esperada in ("Receita Bruta", "Impostos", "CMV", "Frete & Logística", "Desp. Operacionais"):
        if col_esperada not in piv_uf.columns:
            piv_uf[col_esperada] = 0.0

    piv_uf["Custos Totais"] = (
        piv_uf["Impostos"] + piv_uf["CMV"] + piv_uf["Frete & Logística"] + piv_uf["Desp. Operacionais"]
    )
    piv_uf["Lucro Líquido"] = piv_uf["Receita Bruta"] - piv_uf["Custos Totais"]
    piv_uf["Margem %"] = (piv_uf["Lucro Líquido"] / piv_uf["Receita Bruta"] * 100.0).fillna(0.0)
    piv_uf["Peso Frete %"] = (piv_uf["Frete & Logística"] / piv_uf["Receita Bruta"] * 100.0).fillna(0.0)

    metas_uf_media = df_metas_filt.groupby("UF", as_index=False)["Meta_Margem_Pct"].mean()
    metas_uf_media["Meta Margem %"] = metas_uf_media["Meta_Margem_Pct"] * 100.0

    df_mapa = (
        piv_uf.merge(df_estados, on="UF", how="left")
        .merge(metas_uf_media[["UF", "Meta Margem %"]], on="UF", how="left")
    )

    def _classificar_faixa(margem: float) -> str:
        if margem < 0:
            return "Prejuízo (< 0%)"
        if margem < 15:
            return "Margem Apertada (0% a 15%)"
        return "Alta Margem (≥ 15%)"

    df_mapa["Status Margem"] = df_mapa["Margem %"].map(_classificar_faixa)
    return df_mapa