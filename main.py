import pandas as pd
import streamlit as st

from alertas import configurar_logs
from caminhos import garantir_pastas
from dados import (
    STATUS_PIPELINE,
    aplicar_filtros_globais,
    calcular_kpis_dre,
    carregar_bases_oficiais,
    consolidar_dados_mapa,
)
from estilo import MAPA_MESES, aplicar_estilo, formatar_moeda, secao
from graficos import (
    grafico_evolucao_mensal,
    grafico_peso_frete_uf,
    grafico_frete_por_canal,
    grafico_ranking_uf,
    grafico_receita_canal,
    grafico_waterfall_dre,
    renderizar_mapa_geoespacial,
)
from interface import renderizar_filtros_mapa, renderizar_sidebar


def renderizar_pagina_principal(
    df_filtrado: pd.DataFrame,
    df_metas_filt: pd.DataFrame,
    df_evolucao: pd.DataFrame,
    escopo_titulo: str,
    periodo_txt: str,
    modo_clone: bool = False,
) -> None:
    """Renderiza a tela executiva com KPIs da DRE, 4 gráficos ApexCharts e tabela analítica."""
    sufixo = "_clone" if modo_clone else ""
    kpis = calcular_kpis_dre(df_filtrado, df_metas_filt)

    st.title("📊 DRE Regional — Painel Principal")
    st.subheader("Resumo de Receita, Custos, Lucro e Margem Líquida")
    st.caption(f"Escopo ativo: *{escopo_titulo}* · Período: *{periodo_txt}*")

    st.markdown("---")
    secao("Resumo Executivo", f"Meta de Receita no período: {formatar_moeda(kpis['meta_receita'])}")

    c1, c2, c3 = st.columns(3)
    c1.metric(
        ":material/payments: Receita Bruta",
        formatar_moeda(kpis["receita_bruta"]),
        f"{kpis['pct_meta_rec']:.1f}% da meta".replace(".", ","),
        delta_color="off",
    )
    c2.metric(
        ":material/savings: Lucro Líquido",
        formatar_moeda(kpis["lucro_liquido"]),
        "Positivo" if kpis["lucro_liquido"] >= 0 else "Prejuízo na operação",
        delta_color="normal" if kpis["lucro_liquido"] >= 0 else "inverse",
    )
    c3.metric(
        ":material/percent: Margem Líquida",
        f"{kpis['margem_liquida']:.1f}%".replace(".", ","),
        f"{kpis['desvio_margem']:+.1f} p.p. vs meta ({kpis['meta_margem']:.1f}%)".replace(".", ","),
    )

    c4, c5, c6 = st.columns(3)
    c4.metric(
        ":material/account_balance_wallet: Custos & Despesas",
        formatar_moeda(kpis["custos_totais"]),
        f"{kpis['pct_teto']:.1f}% do teto orçado".replace(".", ","),
        delta_color="off",
    )
    c5.metric(
        ":material/rule: Saldo do Teto de Gastos",
        formatar_moeda(abs(kpis["saldo_teto"])),
        "Dentro do teto (Economia)" if kpis["saldo_teto"] >= 0 else "Acima do teto orçado",
        delta_color="normal" if kpis["saldo_teto"] >= 0 else "inverse",
    )
    c6.metric(
        ":material/local_shipping: Peso do Frete s/ Receita",
        f"{kpis['peso_frete']:.1f}%".replace(".", ","),
        f"Gasto logístico: {formatar_moeda(kpis['frete'])}",
        delta_color="off",
    )

    st.markdown("---")
    secao("Estrutura de Resultado & Evolução Mensal")

    g1, g2 = st.columns(2)
    with g1:
        with st.container(height=430, border=True):
            st.markdown("*:material/account_tree: CASCATA DA DRE (WATERFALL)*")
            grafico_waterfall_dre(
                kpis["receita_bruta"],
                kpis["impostos"],
                kpis["cmv"],
                kpis["frete"],
                kpis["desp_op"],
                kpis["lucro_liquido"],
            )

    with g2:
        with st.container(height=430, border=True):
            st.markdown("*:material/ssid_chart: EVOLUÇÃO MENSAL (2026)*")
            grafico_evolucao_mensal(df_evolucao)

    g3, g4 = st.columns(2)
    with g3:
        with st.container(height=430, border=True):
            st.markdown("*:material/leaderboard: RANKING DE MARGEM LÍQUIDA POR ESTADO*")
            grafico_ranking_uf(df_filtrado)

    with g4:
        with st.container(height=430, border=True):
            st.markdown("*:material/pie_chart: RECEITA BRUTA POR CANAL*")
            grafico_receita_canal(df_filtrado)

    st.markdown("---")
    secao("Lançamentos Detalhados", f"{len(df_filtrado):,} registros no filtro".replace(",", "."))

    f1, f2 = st.columns(2)
    grupos_opcoes = sorted(df_filtrado["Grupo_DRE"].unique()) if not df_filtrado.empty else []
    canais_opcoes = sorted(df_filtrado["Canal"].unique()) if not df_filtrado.empty else []

    filtro_grupo = f1.multiselect(
        "Filtrar Rubrica DRE:",
        options=grupos_opcoes,
        placeholder="Todas as rubricas...",
        key=f"tab_grupo{sufixo}",
    )
    filtro_canal = f2.multiselect(
        "Filtrar Canal:",
        options=canais_opcoes,
        placeholder="Todos os canais...",
        key=f"tab_canal{sufixo}",
    )

    df_tab = df_filtrado.copy()
    if filtro_grupo:
        df_tab = df_tab[df_tab["Grupo_DRE"].isin(filtro_grupo)]
    if filtro_canal:
        df_tab = df_tab[df_tab["Canal"].isin(filtro_canal)]

    if df_tab.empty:
        st.info("Nenhum lançamento encontrado para os filtros selecionados.")
        return

    df_tab["Data_Formatada"] = df_tab["Data"].dt.strftime("%d/%m/%Y")
    colunas_exibir = [
        "ID_Lancamento", "Data_Formatada", "UF", "Região",
        "Grupo_DRE", "Natureza", "Canal", "Descrição", "Valor",
    ]
    df_saida = df_tab[colunas_exibir].rename(columns={"Data_Formatada": "Data"})

    st.dataframe(
        df_saida,
        use_container_width=True,
        hide_index=True,
        height=380,
        column_config={
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
        },
    )

    col_info, col_dl = st.columns([3, 1])
    col_info.caption(f"{len(df_saida):,} registros exibidos na tabela.".replace(",", "."))
    col_dl.download_button(
        ":material/file_download: Baixar CSV",
        data=df_saida.to_csv(index=False).encode("utf-8-sig"),
        file_name="lancamentos_dre_regional.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"btn_csv{sufixo}",
    )


def renderizar_pagina_mapa(
    df_filtrado: pd.DataFrame,
    df_metas_filt: pd.DataFrame,
    df_estados: pd.DataFrame,
    escopo_titulo: str,
    periodo_txt: str,
    modo_clone: bool = False,
) -> None:
    """Renderiza a tela exclusiva de análise geoespacial e logística."""
    st.title("🗺️ Mapa Geográfico de Rentabilidade & Logística")
    st.caption(f"Escopo ativo: *{escopo_titulo}* · Período: *{periodo_txt}*")
    st.markdown("---")

    df_mapa_base = consolidar_dados_mapa(df_filtrado, df_metas_filt, df_estados)
    df_mapa, metrica_tamanho, estilo_vis = renderizar_filtros_mapa(df_mapa_base, modo_clone=modo_clone)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(":material/location_on: Estados no Mapa", f"{len(df_mapa)} UFs")
    if not df_mapa.empty:
        melhor_uf = df_mapa.sort_values("Margem %", ascending=False).iloc[0]
        maior_frete_uf = df_mapa.sort_values("Peso Frete %", ascending=False).iloc[0]
        qtd_abaixo = int((df_mapa["Margem %"] < df_mapa["Meta Margem %"]).sum())

        k2.metric(
            ":material/workspace_premium: Maior Margem",
            f"{melhor_uf['UF']} ({melhor_uf['Margem %']:.1f}%)".replace(".", ","),
        )
        k3.metric(
            ":material/local_shipping: Maior Peso de Frete",
            f"{maior_frete_uf['UF']} ({maior_frete_uf['Peso Frete %']:.1f}%)".replace(".", ","),
        )
        k4.metric(":material/warning: Abaixo da Meta", f"{qtd_abaixo} estado(s)")
    else:
        k2.metric(":material/workspace_premium: Maior Margem", "—")
        k3.metric(":material/local_shipping: Maior Peso de Frete", "—")
        k4.metric(":material/warning: Abaixo da Meta", "0")

    st.markdown("---")
    secao("Visualização Geoespacial", f"Dimensionado por: {metrica_tamanho}")
    renderizar_mapa_geoespacial(df_mapa, metrica_tamanho, estilo_vis)

    if not df_mapa.empty:
        st.markdown("---")
        secao("Resumo Regional das UFs Exibidas")
        cols_resumo = [
            "UF", "Estado", "Região", "Gerente_Regional", "Modal_Principal",
            "Receita Bruta", "Frete & Logística", "Lucro Líquido", "Margem %", "Meta Margem %",
        ]
        st.dataframe(
            df_mapa[cols_resumo].sort_values("Margem %", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Gerente_Regional": "Gerente Regional",
                "Modal_Principal": "Modal Principal",
                "Receita Bruta": st.column_config.NumberColumn(format="R$ %.2f"),
                "Frete & Logística": st.column_config.NumberColumn(format="R$ %.2f"),
                "Lucro Líquido": st.column_config.NumberColumn(format="R$ %.2f"),
                "Margem %": st.column_config.NumberColumn(format="%.1f%%"),
                "Meta Margem %": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )


def renderizar_pagina_logistica(
    df_filtrado: pd.DataFrame,
    df_metas_filt: pd.DataFrame,
    df_estados: pd.DataFrame,
    escopo_titulo: str,
    periodo_txt: str,
    modo_clone: bool = False,
) -> None:
    """Renderiza a tela dedicada a custos de frete, modais e eficiência logística por UF."""
    sufixo = "_clone" if modo_clone else ""
    st.title("🚚 Logística, Fretes & Modais por UF")
    st.caption(f"Escopo ativo: *{escopo_titulo}* · Período: *{periodo_txt}*")
    st.markdown("---")

    df_mapa_base = consolidar_dados_mapa(df_filtrado, df_metas_filt, df_estados)
    if df_mapa_base.empty:
        st.info("Sem dados logísticos para o recorte atual.")
        return

    with st.container(border=True):
        f1, f2 = st.columns([1.5, 1])
        modais_opcoes = sorted(df_mapa_base["Modal_Principal"].dropna().unique())
        modais_sel = f1.multiselect(
            "Filtrar Modal Logístico:",
            options=modais_opcoes,
            placeholder="Todos os modais...",
            key=f"log_modal{sufixo}",
        )
        peso_min = f2.slider(
            "Peso mínimo do frete s/ receita (%):",
            min_value=0.0,
            max_value=30.0,
            value=0.0,
            step=1.0,
            key=f"log_peso_min{sufixo}",
        )

    df_log_uf = df_mapa_base.copy()
    if modais_sel:
        df_log_uf = df_log_uf[df_log_uf["Modal_Principal"].isin(modais_sel)]
    if peso_min > 0:
        df_log_uf = df_log_uf[df_log_uf["Peso Frete %"] >= peso_min]

    ufs_validas = df_log_uf["UF"].unique().tolist()
    df_frete_lanc = df_filtrado[
        (df_filtrado["Grupo_DRE"] == "Frete & Logística") & (df_filtrado["UF"].isin(ufs_validas))
    ].copy()

    frete_total = float(df_frete_lanc["Valor"].sum())
    receita_escopo = float(df_log_uf["Receita Bruta"].sum())
    peso_medio = (frete_total / receita_escopo * 100.0) if receita_escopo > 0 else 0.0

    secao("Indicadores de Frete e Distribuição")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(":material/local_shipping: Frete Total", formatar_moeda(frete_total))
    k2.metric(":material/percent: Peso Médio do Frete", f"{peso_medio:.1f}%".replace(".", ","))

    if not df_log_uf.empty:
        pior_log = df_log_uf.sort_values("Peso Frete %", ascending=False).iloc[0]
        melhor_log = df_log_uf.sort_values("Peso Frete %", ascending=True).iloc[0]
        k3.metric(
            ":material/trending_up: Maior Peso de Frete",
            f"{pior_log['UF']} ({pior_log['Peso Frete %']:.1f}%)".replace(".", ","),
        )
        k4.metric(
            ":material/verified: Menor Peso de Frete",
            f"{melhor_log['UF']} ({melhor_log['Peso Frete %']:.1f}%)".replace(".", ","),
        )
    else:
        k3.metric(":material/trending_up: Maior Peso de Frete", "—")
        k4.metric(":material/verified: Menor Peso de Frete", "—")

    st.markdown("---")
    secao("Análise Comparativa por UF e Canal")
    g1, g2 = st.columns(2)
    with g1:
        with st.container(height=430, border=True):
            st.markdown("*:material/bar_chart: PESO DO FRETE S/ RECEITA POR UF (%)*")
            grafico_peso_frete_uf(df_filtrado[df_filtrado["UF"].isin(ufs_validas)])
    with g2:
        with st.container(height=430, border=True):
            st.markdown("*:material/donut_large: FRETE & LOGÍSTICA POR CANAL*")
            grafico_frete_por_canal(df_frete_lanc)

    st.markdown("---")
    secao("Lançamentos de Frete & Logística")
    if df_frete_lanc.empty:
        st.info("Nenhum lançamento de frete encontrado para os filtros atuais.")
    else:
        df_frete_lanc["Data"] = df_frete_lanc["Data"].dt.strftime("%d/%m/%Y")
        cols = ["ID_Lancamento", "Data", "UF", "Região", "Canal", "Descrição", "Valor"]
        df_saida_log = df_frete_lanc[cols]
        st.dataframe(
            df_saida_log,
            use_container_width=True,
            hide_index=True,
            height=360,
            column_config={"Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")},
        )

        col_info, col_dl = st.columns([3, 1])
        col_info.caption(f"{len(df_saida_log):,} lançamentos de frete exibidos.".replace(",", "."))
        col_dl.download_button(
            ":material/file_download: Baixar CSV de Frete",
            data=df_saida_log.to_csv(index=False).encode("utf-8-sig"),
            file_name="fretes_logistica_dre.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"btn_csv_log{sufixo}",
        )


def executar_app() -> None:
    garantir_pastas()
    st.set_page_config(
        page_title="Balanço Regional — DRE por UF",
        page_icon="📊",
        layout="wide",
    )
    configurar_logs()
    aplicar_estilo()

    df_lancamentos, df_metas, df_estados = carregar_bases_oficiais()

    pagina, regiao_sel, uf_sel, meses_sel, mes_escolhido = renderizar_sidebar(
        df_lancamentos, df_estados, STATUS_PIPELINE, modo_clone=False
    )

    df_filtrado, df_metas_filt, df_evolucao = aplicar_filtros_globais(
        df_lancamentos, df_metas, meses_sel, regiao_sel, uf_sel
    )

    escopo_titulo = uf_sel if uf_sel != "Todos (Consolidado)" else f"Região: {regiao_sel}"
    periodo_txt = "Todos os meses" if mes_escolhido == 0 else MAPA_MESES.get(mes_escolhido, "")

    if pagina == "Painel Principal":
        renderizar_pagina_principal(
            df_filtrado, df_metas_filt, df_evolucao, escopo_titulo, periodo_txt
        )
    elif pagina == "Logística":
        renderizar_pagina_logistica(
            df_filtrado, df_metas_filt, df_estados, escopo_titulo, periodo_txt
        )
    else:
        renderizar_pagina_mapa(
            df_filtrado, df_metas_filt, df_estados, escopo_titulo, periodo_txt
        )


if __name__ == "__main__":
    executar_app()