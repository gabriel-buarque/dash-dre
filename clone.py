import runpy
import time
import streamlit as st

from alertas import configurar_logs, notificar_admin, registrar_log
from caminhos import ARQUIVO_LOG_ERROS, RAIZ, garantir_pastas
from dados import (
    aplicar_filtros_globais,
    calcular_kpis_dre,
    consolidar_dados_mapa,
    ler_snapshots_locais,
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

garantir_pastas()
configurar_logs()

# Janela em que a sessão permanece no clone antes de tentar o main.py novamente.
# Clicar em "Atualizar dados" na barra lateral força o retorno imediato ao main.py.
TEMPO_CONTINGENCIA = 10 * 60  # 10 minutos


def _e_controle_do_streamlit(erro: BaseException) -> bool:
    """
    Ignora sinais internos levantados por st.rerun() e st.stop(),
    evitando que interações normais de interface acionem contingência falsa.
    """
    nomes_controle = {"RerunException", "StopException", "RerunData", "NoSessionContext"}
    return any(classe.__name__ in nomes_controle for classe in type(erro).__mro__)


def _em_contingencia() -> bool:
    desde = st.session_state.get("_contingencia_desde")
    return desde is not None and (time.time() - desde) < TEMPO_CONTINGENCIA


def _renderizar_painel_contingencia() -> None:
    """
    Espelho operacional completo que NÃO depende do main.py nem das planilhas Excel:
    opera diretamente sobre os snapshots CSV validados em dados_locais/.
    """
    try:
        st.set_page_config(
            page_title="Balanço Regional — DRE por UF",
            page_icon="📊",
            layout="wide",
        )
    except Exception:
        pass

    aplicar_estilo()

    df_lancamentos, df_metas, df_estados, idade_snapshot = ler_snapshots_locais()
    if df_lancamentos.empty or df_estados.empty:
        st.error(
            "🚨 O painel principal encontrou uma falha e os snapshots CSV locais ainda não "
            f"foram gerados em 'dados_locais/'. Consulte '{ARQUIVO_LOG_ERROS.name}'."
        )
        return

    status_clone = {
        "estado": "backup",
        "fonte": "Snapshot CSV (Clone)",
        "quando": idade_snapshot,
        "linhas_lancamentos": len(df_lancamentos),
        "latencia_ms": 0.0,
    }

    pagina, regiao_sel, uf_sel, meses_sel, mes_escolhido = renderizar_sidebar(
        df_lancamentos, df_estados, status_clone, modo_clone=True
    )

    df_filtrado, df_metas_filt, df_evolucao = aplicar_filtros_globais(
        df_lancamentos, df_metas, meses_sel, regiao_sel, uf_sel
    )

    escopo_titulo = uf_sel if uf_sel != "Todos (Consolidado)" else f"Região: {regiao_sel}"
    periodo_txt = "Todos os meses" if mes_escolhido == 0 else MAPA_MESES.get(mes_escolhido, "")

    if pagina == "Painel Principal":
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
                    kpis["receita_bruta"], kpis["impostos"], kpis["cmv"],
                    kpis["frete"], kpis["desp_op"], kpis["lucro_liquido"],
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
        if not df_filtrado.empty:
            df_tab = df_filtrado.copy()
            df_tab["Data"] = df_tab["Data"].dt.strftime("%d/%m/%Y")
            cols = ["ID_Lancamento", "Data", "UF", "Região", "Grupo_DRE", "Natureza", "Canal", "Descrição", "Valor"]
            st.dataframe(
                df_tab[cols],
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config={"Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")},
            )
    elif pagina == "Logística":
        st.title("🚚 Logística, Fretes & Modais por UF")
        st.caption(f"Escopo ativo: *{escopo_titulo}* · Período: *{periodo_txt}*")
        st.markdown("---")

        df_mapa_base = consolidar_dados_mapa(df_filtrado, df_metas_filt, df_estados)
        if df_mapa_base.empty:
            st.info("Sem dados logísticos para o recorte atual.")
        else:
            with st.container(border=True):
                f1, f2 = st.columns([1.5, 1])
                modais_opcoes = sorted(df_mapa_base["Modal_Principal"].dropna().unique())
                modais_sel = f1.multiselect(
                    "Filtrar Modal Logístico:",
                    options=modais_opcoes,
                    placeholder="Todos os modais...",
                    key="log_modal_clone",
                )
                peso_min = f2.slider(
                    "Peso mínimo do frete s/ receita (%):",
                    min_value=0.0,
                    max_value=30.0,
                    value=0.0,
                    step=1.0,
                    key="log_peso_min_clone",
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
            if not df_frete_lanc.empty:
                df_frete_lanc["Data"] = df_frete_lanc["Data"].dt.strftime("%d/%m/%Y")
                cols = ["ID_Lancamento", "Data", "UF", "Região", "Canal", "Descrição", "Valor"]
                st.dataframe(
                    df_frete_lanc[cols],
                    use_container_width=True,
                    hide_index=True,
                    height=360,
                    column_config={"Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")},
                )
    else:
        st.title("🗺️ Mapa Geográfico de Rentabilidade & Logística")
        st.caption(f"Escopo ativo: *{escopo_titulo}* · Período: *{periodo_txt}*")
        st.markdown("---")

        df_mapa_base = consolidar_dados_mapa(df_filtrado, df_metas_filt, df_estados)
        df_mapa, metrica_tamanho, estilo_vis = renderizar_filtros_mapa(df_mapa_base, modo_clone=True)
        secao("Visualização Geoespacial", f"Dimensionado por: {metrica_tamanho}")
        renderizar_mapa_geoespacial(df_mapa, metrica_tamanho, estilo_vis)


# ==============================================================================
# ESCUDO DE EXECUÇÃO PRINCIPAL
# ==============================================================================
if _em_contingencia():
    _renderizar_painel_contingencia()
else:
    try:
        runpy.run_path(str(RAIZ / "main.py"), run_name="__main__")
    except Exception as erro_critico:
        if _e_controle_do_streamlit(erro_critico):
            raise

        notificar_admin(
            "main.py falhou — Clone de Contingência assumiu o controle visual",
            erro_critico,
            origem="CLONE",
        )
        registrar_log(
            "Sessão redirecionada para modo contingência (clone.py).",
            nivel="warning",
            origem="CLONE",
        )
        st.session_state["_contingencia_desde"] = time.time()
        st.rerun()