import pandas as pd
import streamlit as st

from alertas import ler_ultimas_linhas_log, registrar_log
from caminhos import ARQUIVO_LOG_PIPELINE
from estilo import MAPA_MESES, secao


def renderizar_sidebar(
    df_lancamentos: pd.DataFrame,
    df_estados: pd.DataFrame,
    status_pipeline: dict,
    modo_clone: bool = False,
) -> tuple[str, str, str, list[int], int]:
    """
    Constrói a barra lateral de navegação, sincronização, filtros globais e logs.
    Usa sufixo próprio quando executado via clone.py para evitar colisão de keys.
    """
    sufixo = "_clone" if modo_clone else ""

    if "pagina_atual" not in st.session_state:
        st.session_state.pagina_atual = "Painel Principal"

    with st.sidebar:
        st.markdown("## :material/account_balance: Balanço Regional")
        st.caption("DRE & Rentabilidade por UF")
        st.markdown("---")

        st.markdown("*:material/menu: Navegação*")
        if st.button(
            ":material/space_dashboard: Painel Principal",
            key=f"nav_principal{sufixo}",
            use_container_width=True,
        ):
            st.session_state.pagina_atual = "Painel Principal"
        if st.button(
            ":material/local_shipping: Logística & Fretes",
            key=f"nav_logistica{sufixo}",
            use_container_width=True,
        ):
            st.session_state.pagina_atual = "Logística"
        if st.button(
            ":material/map: Mapa Geográfico",
            key=f"nav_mapa{sufixo}",
            use_container_width=True,
        ):
            st.session_state.pagina_atual = "Mapa Geográfico"

        st.markdown("---")
        if st.button(
            ":material/sync: Atualizar dados",
            key=f"btn_sync{sufixo}",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.session_state.pop("_contingencia_desde", None)
            registrar_log(
                "Sincronização manual solicitada pelo usuário (cache limpo).",
                origem="UI_CLONE" if modo_clone else "UI",
            )
            st.toast("Bases recarregadas!", icon=":material/check_circle:")
            st.rerun()

        st.markdown("---")
        st.markdown("*:material/filter_alt: Filtros Globais*")

        regioes_opcoes = ["Todas"] + sorted(df_estados["Região"].dropna().unique().tolist())
        regiao_sel = st.selectbox("Região:", regioes_opcoes, key=f"f_regiao{sufixo}")

        if regiao_sel != "Todas":
            ufs_disponiveis = sorted(
                df_estados.loc[df_estados["Região"] == regiao_sel, "UF"].unique()
            )
        else:
            ufs_disponiveis = sorted(df_estados["UF"].unique())

        uf_sel = st.selectbox(
            "Estado (UF):",
            ["Todos (Consolidado)"] + ufs_disponiveis,
            key=f"f_uf{sufixo}",
        )

        meses_com_dados = sorted(
            df_lancamentos["Mês_Num"].dropna().astype(int).unique().tolist()
        )
        mes_escolhido = st.selectbox(
            "Período (2026):",
            options=[0] + meses_com_dados,
            index=0,
            format_func=lambda m: "Todos os meses" if m == 0 else MAPA_MESES.get(m, str(m)),
            key=f"f_periodo{sufixo}",
        )
        meses_sel = meses_com_dados if mes_escolhido == 0 else [mes_escolhido]

        st.markdown("---")

    return st.session_state.pagina_atual, regiao_sel, uf_sel, meses_sel, mes_escolhido


def renderizar_filtros_mapa(
    df_mapa: pd.DataFrame, modo_clone: bool = False
) -> tuple[pd.DataFrame, str, str]:
    """Renderiza os controles exclusivos da página de Mapa Geográfico e filtra as UFs."""
    sufixo = "_clone" if modo_clone else ""
    secao("Filtros do Mapa")

    with st.container(border=True):
        m1, m2, m3, m4 = st.columns([1.2, 1.2, 1.2, 1])

        metrica_tamanho = m1.selectbox(
            "Tamanho / Altura representa:",
            ["Receita Bruta", "Lucro Líquido", "Frete & Logística", "Custos Totais"],
            key=f"mp_metrica{sufixo}",
        )
        filtro_status_mapa = m2.multiselect(
            "Faixa de Rentabilidade:",
            options=["Alta Margem (≥ 15%)", "Margem Apertada (0% a 15%)", "Prejuízo (< 0%)"],
            placeholder="Todas as faixas...",
            key=f"mp_status{sufixo}",
        )
        modais_disp = sorted(df_mapa["Modal_Principal"].dropna().unique()) if not df_mapa.empty else []
        filtro_modal = m3.multiselect(
            "Modal Logístico:",
            options=modais_disp,
            placeholder="Todos os modais...",
            key=f"mp_modal{sufixo}",
        )
        estilo_vis = m4.radio(
            "Modo do Mapa:",
            ["Colunas 3D", "Bolhas 2D"],
            horizontal=True,
            key=f"mp_estilo{sufixo}",
        )

        f_gerente, f_meta = st.columns([2, 1])
        gerentes_disp = sorted(df_mapa["Gerente_Regional"].dropna().unique()) if not df_mapa.empty else []
        filtro_gerente = f_gerente.multiselect(
            "Gerente Regional:",
            options=gerentes_disp,
            placeholder="Todos os gerentes...",
            key=f"mp_gerente{sufixo}",
        )
        apenas_abaixo_meta = f_meta.checkbox(
            "Mostrar apenas UFs abaixo da meta de margem",
            key=f"mp_abaixo_meta{sufixo}",
        )

    d = df_mapa.copy()
    if not d.empty:
        if filtro_status_mapa:
            d = d[d["Status Margem"].isin(filtro_status_mapa)]
        if filtro_modal:
            d = d[d["Modal_Principal"].isin(filtro_modal)]
        if filtro_gerente:
            d = d[d["Gerente_Regional"].isin(filtro_gerente)]
        if apenas_abaixo_meta:
            d = d[d["Margem %"] < d["Meta Margem %"]]

    return d, metrica_tamanho, estilo_vis
