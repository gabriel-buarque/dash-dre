import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from alertas import notificar_admin
from estilo import MESES_CURTO, formatar_moeda

try:
    import pydeck as pdk
    TEM_PYDECK = True
except ImportError:
    TEM_PYDECK = False

CSS_NUMEROS_GRAFICO = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700;800&display=swap" rel="stylesheet">
<style>
  html, body { margin: 0; padding: 0; overflow: hidden; background: transparent; }
  .apexcharts-text, .apexcharts-datalabel, .apexcharts-yaxis-label,
  .apexcharts-xaxis-label, .apexcharts-donut-label, .apexcharts-legend-text {
    font-family: 'Inter', sans-serif !important;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.015em;
  }
</style>
"""


def _falhar_grafico_seguro(titulo: str, erro: Exception) -> None:
    notificar_admin(titulo, erro, origem="GRAFICOS")
    st.info("Visualização temporariamente indisponível para o recorte atual.")


def grafico_waterfall_dre(
    rec: float, imp: float, cmv: float, frete: float, desp_op: float, lucro: float
) -> None:
    """Cascata da DRE com pílulas translúcidas e formatação financeira compacta."""
    if rec <= 0:
        st.info("Sem dados para montar a cascata da DRE.")
        return

    try:
        apos_imp = rec - imp
        apos_cmv = apos_imp - cmv
        apos_frete = apos_cmv - frete
        cor_lucro = "#059669" if lucro >= 0 else "#DC2626"
        faixa_lucro = [0, round(lucro, 2)] if lucro >= 0 else [round(lucro, 2), 0]

        barras = [
            {"x": "Receita Bruta", "y": [0, round(rec, 2)], "fillColor": "#2563EB", "delta": round(rec, 2)},
            {"x": "(-) Impostos", "y": [round(apos_imp, 2), round(rec, 2)], "fillColor": "#DC2626", "delta": -round(imp, 2)},
            {"x": "(-) CMV", "y": [round(apos_cmv, 2), round(apos_imp, 2)], "fillColor": "#DC2626", "delta": -round(cmv, 2)},
            {"x": "(-) Frete", "y": [round(apos_frete, 2), round(apos_cmv, 2)], "fillColor": "#D97706", "delta": -round(frete, 2)},
            {"x": "(-) Operacional", "y": [round(lucro, 2), round(apos_frete, 2)], "fillColor": "#DC2626", "delta": -round(desp_op, 2)},
            {"x": "(=) Lucro Líq.", "y": faixa_lucro, "fillColor": cor_lucro, "delta": round(lucro, 2)},
        ]

        html = f"""
        {CSS_NUMEROS_GRAFICO}
        <div id="chart_waterfall"></div>
        <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
        <script>
          const dados = {json.dumps(barras)};
          const fmtCurto = (v) => {{
            const s = v < 0 ? "-" : "+";
            const a = Math.abs(v);
            if (a >= 1e6) return s + (a / 1e6).toFixed(1).replace(".", ",") + " mi";
            if (a >= 1e3) return s + (a / 1e3).toFixed(0) + " mil";
            return s + a.toFixed(0);
          }};
          const fmtCompleto = (v) => {{
            const s = v < 0 ? "-R$ " : "R$ ";
            const a = Math.abs(v);
            if (a >= 1e6) return s + (a / 1e6).toFixed(2).replace(".", ",") + " mi";
            if (a >= 1e3) return s + (a / 1e3).toFixed(1).replace(".", ",") + " mil";
            return s + a.toFixed(2).replace(".", ",");
          }};

          new ApexCharts(document.querySelector("#chart_waterfall"), {{
            series: [{{ data: dados }}],
            chart: {{
              type: "rangeBar",
              height: 350,
              foreColor: "#E2E8F0",
              toolbar: {{ show: false }},
              background: "transparent"
            }},
            plotOptions: {{ bar: {{ columnWidth: "60%", borderRadius: 6 }} }},
            dataLabels: {{
              enabled: true,
              formatter: (_, opts) => {{
                const idx = opts.dataPointIndex;
                const d = opts.w.config.series[0].data[idx].delta;
                if (idx === 0 || idx === 5) return fmtCompleto(d).replace("R$ ", "");
                return fmtCurto(d);
              }},
              style: {{ fontSize: "11px", fontWeight: 700, colors: ["#141414"] }},
              background: {{
                enabled: true,
                foreColor: "#FFFFFF",
                padding: 5,
                borderRadius: 5,
                borderWidth: 1,
                borderColor: "rgba(255,255,255,0.18)",
                opacity: 0.88,
                dropShadow: {{ enabled: false }}
              }}
            }},
            xaxis: {{
              labels: {{ style: {{ colors: "#E2E8F0", fontWeight: 600, fontSize: "11px" }} }},
              axisBorder: {{ color: "#2e2e2e" }},
              axisTicks: {{ show: false }}
            }},
            yaxis: {{
              labels: {{
                formatter: (v) => "R$ " + (v / 1e6).toFixed(0) + " mi",
                style: {{ colors: "#94A3B8", fontWeight: 600, fontSize: "11px" }}
              }}
            }},
            grid: {{ borderColor: "#262626", strokeDashArray: 4 }},
            tooltip: {{
              theme: "dark",
              custom: ({{ dataPointIndex, w }}) => {{
                const d = w.config.series[0].data[dataPointIndex];
                return '<div style="padding:8px 12px;font-size:12px;background:#141414;color:#FFF;border:1px solid #334155;border-radius:6px;">' +
                       '<span style="color:#94A3B8;font-size:11px;">' + d.x + '</span><br/>' +
                       '<b style="font-size:13px;">' + fmtCompleto(d.delta) + '</b></div>';
              }}
            }}
          }}).render();
        </script>
        """
        components.html(html, height=360, scrolling=False)
    except Exception as e:
        _falhar_grafico_seguro("Erro ao renderizar Waterfall DRE", e)


def grafico_evolucao_mensal(df_base_evolucao: pd.DataFrame) -> None:
    """Colunas de Receita x Custos + Linha de Margem (%) com badges ciano."""
    if df_base_evolucao.empty:
        st.info("Sem dados para evolução mensal.")
        return

    try:
        piv = df_base_evolucao.pivot_table(
            index="Mês_Num", columns="Grupo_DRE", values="Valor", aggfunc="sum", fill_value=0.0
        ).sort_index()

        categorias = [MESES_CURTO.get(int(m), str(m)) for m in piv.index]
        receitas = [round(float(v), 2) for v in piv.get("Receita Bruta", pd.Series(0.0, index=piv.index))]

        colunas_custo = [c for c in ("Impostos", "CMV", "Frete & Logística", "Desp. Operacionais") if c in piv.columns]
        custos = [round(float(v), 2) for v in piv[colunas_custo].sum(axis=1)] if colunas_custo else [0.0] * len(receitas)
        margens = [round(((r - c) / r) * 100.0, 1) if r > 0 else 0.0 for r, c in zip(receitas, custos)]

        html = f"""
        {CSS_NUMEROS_GRAFICO}
        <div id="chart_evolucao"></div>
        <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
        <script>
          const fmtMoeda = (v) => "R$ " + (v / 1e6).toFixed(2).replace(".", ",") + " mi";

          new ApexCharts(document.querySelector("#chart_evolucao"), {{
            series: [
              {{ name: "Receita Bruta", type: "column", data: {json.dumps(receitas)} }},
              {{ name: "Custos & Despesas", type: "column", data: {json.dumps(custos)} }},
              {{ name: "Margem Líquida (%)", type: "line", data: {json.dumps(margens)} }}
            ],
            chart: {{
              height: 350,
              type: "line",
              foreColor: "#E2E8F0",
              toolbar: {{ show: false }},
              background: "transparent"
            }},
            colors: ["#2563EB", "#475569", "#02d6d6"],
            stroke: {{ width: [0, 0, 3], curve: "smooth" }},
            plotOptions: {{ bar: {{ columnWidth: "56%", borderRadius: 4 }} }},
            dataLabels: {{
              enabled: true,
              enabledOnSeries: [2],
              formatter: (v) => v.toFixed(1).replace(".", ",") + "%",
              offsetY: -7,
              style: {{ fontSize: "10px", fontWeight: 700, colors: ["#0F172A"] }},
              background: {{
                enabled: true,
                foreColor: "#02d6d6",
                padding: 3,
                borderRadius: 4,
                borderWidth: 1,
                borderColor: "rgba(2, 214, 214, 0.45)",
                opacity: 0.92
              }}
            }},
            markers: {{ size: [0, 0, 4], strokeColors: "#141414", strokeWidth: 2 }},
            xaxis: {{
              categories: {json.dumps(categorias)},
              labels: {{ style: {{ colors: "#E2E8F0", fontWeight: 600 }} }},
              axisBorder: {{ color: "#2e2e2e" }},
              axisTicks: {{ show: false }}
            }},
            yaxis: [
              {{
                labels: {{
                  formatter: (v) => "R$ " + (v / 1e6).toFixed(0) + " mi",
                  style: {{ colors: "#94A3B8", fontWeight: 600 }}
                }}
              }},
              {{ show: false }},
              {{
                opposite: true,
                labels: {{
                  formatter: (v) => v.toFixed(0) + "%",
                  style: {{ colors: "#02d6d6", fontWeight: 700 }}
                }}
              }}
            ],
            grid: {{ borderColor: "#262626", strokeDashArray: 4 }},
            tooltip: {{
              theme: "dark",
              shared: true,
              intersect: false,
              y: [
                {{ formatter: fmtMoeda }},
                {{ formatter: fmtMoeda }},
                {{ formatter: (v) => v.toFixed(1).replace(".", ",") + "%" }}
              ]
            }},
            legend: {{ position: "bottom", labels: {{ colors: "#E2E8F0" }} }}
          }}).render();
        </script>
        """
        components.html(html, height=360, scrolling=False)
    except Exception as e:
        _falhar_grafico_seguro("Erro ao renderizar Evolução Mensal", e)


def grafico_ranking_uf(df_filtrado: pd.DataFrame) -> None:
    """Ranking horizontal de Margem Líquida (%) por UF."""
    piv = df_filtrado.pivot_table(
        index="UF", columns="Grupo_DRE", values="Valor", aggfunc="sum", fill_value=0.0
    ).reset_index()

    if piv.empty or "Receita Bruta" not in piv.columns:
        st.info("Sem dados por UF para o ranking.")
        return

    try:
        saidas = [c for c in ("Impostos", "CMV", "Frete & Logística", "Desp. Operacionais") if c in piv.columns]
        piv["Lucro"] = piv["Receita Bruta"] - piv[saidas].sum(axis=1)
        piv["Margem"] = (piv["Lucro"] / piv["Receita Bruta"]) * 100.0
        piv = piv.sort_values("Margem", ascending=False)

        ufs = piv["UF"].tolist()
        margens = [round(float(m), 1) for m in piv["Margem"]]
        cores = ["#059669" if m >= 15 else ("#D97706" if m >= 0 else "#DC2626") for m in margens]

        html = f"""
        {CSS_NUMEROS_GRAFICO}
        <div id="chart_rank"></div>
        <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
        <script>
          new ApexCharts(document.querySelector("#chart_rank"), {{
            series: [{{ name: "Margem Líquida", data: {json.dumps(margens)} }}],
            chart: {{
              type: "bar",
              height: 350,
              foreColor: "#E2E8F0",
              toolbar: {{ show: false }},
              background: "transparent"
            }},
            colors: {json.dumps(cores)},
            plotOptions: {{ bar: {{ horizontal: true, distributed: true, barHeight: "68%", borderRadius: 4 }} }},
            dataLabels: {{
              enabled: true,
              formatter: (v) => (v > 0 ? "+" : "") + v.toFixed(1).replace(".", ",") + "%",
              style: {{ fontSize: "10.5px", fontWeight: 700, colors: ["#141414"] }},
              background: {{
                enabled: true,
                foreColor: "#FFFFFF",
                padding: 3,
                borderRadius: 4,
                borderWidth: 0,
                opacity: 0.72,
                dropShadow: {{ enabled: false }}
              }}
            }},
            annotations: {{
              xaxis: [{{ x: 0, borderColor: "#64748B", strokeDashArray: 0 }}]
            }},
            xaxis: {{
              categories: {json.dumps(ufs)},
              labels: {{
                formatter: (v) => v + "%",
                style: {{ colors: "#94A3B8", fontWeight: 600 }}
              }},
              axisBorder: {{ color: "#2e2e2e" }}
            }},
            yaxis: {{
              labels: {{ style: {{ colors: "#FFFFFF", fontWeight: 700, fontSize: "11.5px" }} }}
            }},
            grid: {{
              borderColor: "#262626",
              strokeDashArray: 4,
              xaxis: {{ lines: {{ show: true }} }},
              yaxis: {{ lines: {{ show: false }} }}
            }},
            tooltip: {{
              theme: "dark",
              y: {{ formatter: (v) => v.toFixed(1).replace(".", ",") + "%" }}
            }},
            legend: {{ show: false }}
          }}).render();
        </script>
        """
        components.html(html, height=360, scrolling=False)
    except Exception as e:
        _falhar_grafico_seguro("Erro ao renderizar Ranking UF", e)


def grafico_receita_canal(df_filtrado: pd.DataFrame) -> None:
    """Rosca centralizada com KPI totalizador interativo no centro."""
    df_rec = df_filtrado[df_filtrado["Grupo_DRE"] == "Receita Bruta"]
    if df_rec.empty:
        st.info("Sem dados de receita por canal.")
        return

    try:
        por_canal = df_rec.groupby("Canal")["Valor"].sum().sort_values(ascending=False)
        labels = por_canal.index.tolist()
        valores = [round(float(v), 2) for v in por_canal.values]

        html = f"""
        {CSS_NUMEROS_GRAFICO}
        <style>
          #chart_canal {{ width: 100%; display: flex; justify-content: center; }}
        </style>
        <div id="chart_canal"></div>
        <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
        <script>
          const fmtMoeda = (v) => {{
            const n = Number(v);
            if (isNaN(n)) return v;
            if (n >= 1e6) return "R$ " + (n / 1e6).toFixed(1).replace(".", ",") + " mi";
            if (n >= 1e3) return "R$ " + (n / 1e3).toFixed(0) + " mil";
            return "R$ " + n.toFixed(0);
          }};

          new ApexCharts(document.querySelector("#chart_canal"), {{
            series: {json.dumps(valores)},
            labels: {json.dumps(labels)},
            chart: {{
              type: "donut",
              width: "100%",
              height: 350,
              foreColor: "#E2E8F0",
              background: "transparent"
            }},
            plotOptions: {{
              pie: {{
                customScale: 0.95,
                donut: {{
                  size: "68%",
                  labels: {{
                    show: true,
                    name: {{
                      show: true,
                      fontSize: "11px",
                      fontWeight: 700,
                      color: "#94A3B8",
                      offsetY: -6
                    }},
                    value: {{
                      show: true,
                      fontSize: "21px",
                      fontWeight: 800,
                      color: "#FFFFFF",
                      offsetY: 6,
                      formatter: (v) => fmtMoeda(v)
                    }},
                    total: {{
                      show: true,
                      label: "RECEITA TOTAL",
                      fontSize: "11px",
                      fontWeight: 700,
                      color: "#02d6d6",
                      formatter: (w) => {{
                        const soma = w.globals.seriesTotals.reduce((a, b) => a + b, 0);
                        return fmtMoeda(soma);
                      }}
                    }}
                  }}
                }}
              }}
            }},
            colors: ["#2563EB", "#008b8b", "#0284c7", "#475569"],
            stroke: {{ colors: ["#1b1b1f"], width: 3 }},
            dataLabels: {{
              formatter: (val) => val.toFixed(1).replace(".", ",") + "%",
              style: {{ fontSize: "11px", fontWeight: 700, colors: ["#FFFFFF"] }},
              dropShadow: {{ enabled: false }}
            }},
            legend: {{
              position: "bottom",
              horizontalAlign: "center",
              labels: {{ colors: "#E2E8F0" }}
            }},
            tooltip: {{
              theme: "dark",
              y: {{ formatter: (v) => "R$ " + (v / 1e6).toFixed(2).replace(".", ",") + " mi" }}
            }}
          }}).render();
        </script>
        """
        components.html(html, height=360, scrolling=False)
    except Exception as e:
        _falhar_grafico_seguro("Erro ao renderizar Rosca de Canais", e)


def grafico_peso_frete_uf(df_filtrado: pd.DataFrame) -> None:
    """Peso do Frete (%) sobre a Receita Bruta por UF."""
    if df_filtrado.empty:
        st.info("Sem dados de frete para o filtro selecionado.")
        return

    try:
        piv = df_filtrado.pivot_table(
            index="UF", columns="Grupo_DRE", values="Valor", aggfunc="sum", fill_value=0.0
        ).reset_index()

        if "Frete & Logística" not in piv.columns or "Receita Bruta" not in piv.columns:
            st.info("Colunas de Receita ou Frete ausentes.")
            return

        piv["Peso_Frete"] = (piv["Frete & Logística"] / piv["Receita Bruta"] * 100.0).fillna(0.0)
        piv = piv.sort_values("Peso_Frete", ascending=False)

        ufs = piv["UF"].tolist()
        pesos = [round(float(v), 1) for v in piv["Peso_Frete"]]
        cores = ["#DC2626" if v >= 18 else ("#D97706" if v >= 12 else "#02d6d6") for v in pesos]

        html = f"""
        {CSS_NUMEROS_GRAFICO}
        <div id="chart_frete_uf"></div>
        <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
        <script>
          new ApexCharts(document.querySelector("#chart_frete_uf"), {{
            series: [{{ name: "Peso do Frete (%)", data: {json.dumps(pesos)} }}],
            chart: {{
              type: "bar",
              height: 350,
              foreColor: "#E2E8F0",
              toolbar: {{ show: false }},
              background: "transparent"
            }},
            colors: {json.dumps(cores)},
            plotOptions: {{ bar: {{ horizontal: true, distributed: true, barHeight: "68%", borderRadius: 4 }} }},
            dataLabels: {{
              enabled: true,
              formatter: (v) => v.toFixed(1).replace(".", ",") + "%",
              style: {{ fontSize: "10.5px", fontWeight: 700, colors: ["#141414"] }},
              background: {{
                enabled: true,
                foreColor: "#FFFFFF",
                padding: 3,
                borderRadius: 4,
                borderWidth: 0,
                opacity: 0.78,
                dropShadow: {{ enabled: false }}
              }}
            }},
            xaxis: {{
              categories: {json.dumps(ufs)},
              labels: {{ formatter: (v) => v + "%", style: {{ colors: "#94A3B8", fontWeight: 600 }} }},
              axisBorder: {{ color: "#2e2e2e" }}
            }},
            yaxis: {{
              labels: {{ style: {{ colors: "#FFFFFF", fontWeight: 700, fontSize: "11.5px" }} }}
            }},
            grid: {{
              borderColor: "#262626",
              strokeDashArray: 4,
              xaxis: {{ lines: {{ show: true }} }},
              yaxis: {{ lines: {{ show: false }} }}
            }},
            tooltip: {{ theme: "dark", y: {{ formatter: (v) => v.toFixed(1).replace(".", ",") + "% da receita" }} }},
            legend: {{ show: false }}
          }}).render();
        </script>
        """
        components.html(html, height=360, scrolling=False)
    except Exception as e:
        _falhar_grafico_seguro("Erro ao renderizar Peso do Frete por UF", e)


def grafico_frete_por_canal(df_filtrado: pd.DataFrame) -> None:
    """Distribuição do gasto com Frete & Logística por Canal."""
    df_frete = df_filtrado[df_filtrado["Grupo_DRE"] == "Frete & Logística"]
    if df_frete.empty:
        st.info("Sem lançamentos de frete para o período.")
        return

    try:
        por_canal = df_frete.groupby("Canal")["Valor"].sum().sort_values(ascending=False)
        labels = por_canal.index.tolist()
        valores = [round(float(v), 2) for v in por_canal.values]

        html = f"""
        {CSS_NUMEROS_GRAFICO}
        <style>#chart_frete_canal {{ width: 100%; display: flex; justify-content: center; }}</style>
        <div id="chart_frete_canal"></div>
        <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
        <script>
          const fmtMoeda = (v) => {{
            const n = Number(v);
            if (isNaN(n)) return v;
            if (n >= 1e6) return "R$ " + (n / 1e6).toFixed(2).replace(".", ",") + " mi";
            if (n >= 1e3) return "R$ " + (n / 1e3).toFixed(0) + " mil";
            return "R$ " + n.toFixed(0);
          }};

          new ApexCharts(document.querySelector("#chart_frete_canal"), {{
            series: {json.dumps(valores)},
            labels: {json.dumps(labels)},
            chart: {{
              type: "donut",
              width: "100%",
              height: 350,
              foreColor: "#E2E8F0",
              background: "transparent"
            }},
            plotOptions: {{
              pie: {{
                customScale: 0.95,
                donut: {{
                  size: "68%",
                  labels: {{
                    show: true,
                    name: {{ show: true, fontSize: "11px", fontWeight: 700, color: "#94A3B8", offsetY: -6 }},
                    value: {{ show: true, fontSize: "20px", fontWeight: 800, color: "#FFFFFF", offsetY: 6, formatter: fmtMoeda }},
                    total: {{
                      show: true,
                      label: "FRETE TOTAL",
                      fontSize: "11px",
                      fontWeight: 700,
                      color: "#02d6d6",
                      formatter: (w) => fmtMoeda(w.globals.seriesTotals.reduce((a, b) => a + b, 0))
                    }}
                  }}
                }}
              }}
            }},
            colors: ["#D97706", "#2563EB", "#008b8b", "#475569"],
            stroke: {{ colors: ["#1b1b1f"], width: 3 }},
            dataLabels: {{
              formatter: (val) => val.toFixed(1).replace(".", ",") + "%",
              style: {{ fontSize: "11px", fontWeight: 700, colors: ["#FFFFFF"] }},
              dropShadow: {{ enabled: false }}
            }},
            legend: {{ position: "bottom", horizontalAlign: "center", labels: {{ colors: "#E2E8F0" }} }},
            tooltip: {{ theme: "dark", y: {{ formatter: fmtMoeda }} }}
          }}).render();
        </script>
        """
        components.html(html, height=360, scrolling=False)
    except Exception as e:
        _falhar_grafico_seguro("Erro ao renderizar Frete por Canal", e)


def renderizar_mapa_geoespacial(
    df_mapa: pd.DataFrame, metrica_tamanho: str, estilo_vis: str
) -> None:
    """Renderiza o mapa interativo 3D/2D via PyDeck (ou fallback st.map)."""
    if df_mapa.empty:
        st.warning("Nenhum estado atende aos filtros selecionados para o mapa.")
        return

    try:
        d = df_mapa.copy()

        def _definir_rgb(m: float) -> list[int]:
            if m >= 15:
                return [2, 214, 160, 215]
            if m >= 0:
                return [245, 158, 11, 215]
            return [239, 68, 68, 225]

        d["cor_rgb"] = d["Margem %"].map(_definir_rgb)
        valores_base = d[metrica_tamanho].abs()
        max_val = float(valores_base.max()) if valores_base.max() > 0 else 1.0
        d["escala_norm"] = valores_base / max_val

        d["Receita_Txt"] = d["Receita Bruta"].map(formatar_moeda)
        d["Lucro_Txt"] = d["Lucro Líquido"].map(formatar_moeda)
        d["Frete_Txt"] = d["Frete & Logística"].map(formatar_moeda)
        d["Margem_Txt"] = d["Margem %"].map(lambda v: f"{v:.1f}%".replace(".", ","))

        with st.container(border=True):
            if TEM_PYDECK:
                if estilo_vis == "Colunas 3D":
                    camada = pdk.Layer(
                        "ColumnLayer",
                        data=d,
                        get_position="[Lon, Lat]",
                        get_elevation="escala_norm * 650000 + 40000",
                        elevation_scale=1,
                        radius=65000,
                        get_fill_color="cor_rgb",
                        pickable=True,
                        auto_highlight=True,
                    )
                    pitch_mapa = 42
                else:
                    camada = pdk.Layer(
                        "ScatterplotLayer",
                        data=d,
                        get_position="[Lon, Lat]",
                        get_radius="escala_norm * 190000 + 45000",
                        get_fill_color="cor_rgb",
                        get_line_color=[255, 255, 255, 200],
                        line_width_min_pixels=2,
                        pickable=True,
                        auto_highlight=True,
                    )
                    pitch_mapa = 0

                estado_camera = pdk.ViewState(
                    latitude=float(d["Lat"].mean()),
                    longitude=float(d["Lon"].mean()),
                    zoom=3.6 if len(d) > 3 else 5.0,
                    pitch=pitch_mapa,
                )

                tooltip_mapa = {
                    "html": (
                        "<b>{Estado} ({UF})</b><br/>"
                        "Gerente: {Gerente_Regional}<br/>"
                        "Modal: {Modal_Principal}<hr style='margin:4px 0;border-color:#444'/>"
                        "Receita: <b>{Receita_Txt}</b><br/>"
                        "Frete: <b>{Frete_Txt}</b><br/>"
                        "Lucro: <b>{Lucro_Txt}</b><br/>"
                        "Margem: <b>{Margem_Txt}</b>"
                    ),
                    "style": {
                        "backgroundColor": "#141414",
                        "color": "#F8FAFC",
                        "border": "1px solid #02d6d6",
                        "borderRadius": "8px",
                        "fontSize": "12px",
                    },
                }

                st.pydeck_chart(
                    pdk.Deck(
                        layers=[camada],
                        initial_view_state=estado_camera,
                        map_style="dark",
                        tooltip=tooltip_mapa,
                    ),
                    use_container_width=True,
                    height=520,
                )
            else:
                d["Cor_Hex"] = d["Margem %"].map(
                    lambda m: "#02d6a0" if m >= 15 else ("#f59e0b" if m >= 0 else "#ef4444")
                )
                d["Raio"] = d["escala_norm"] * 180_000 + 45_000
                st.map(d, latitude="Lat", longitude="Lon", size="Raio", color="Cor_Hex", zoom=3)

            st.caption(
                "🟢 Verde: Margem ≥ 15%  |  🟠 Laranja: Margem entre 0% e 15%  |  🔴 Vermelho: Operação no Prejuízo (< 0%)"
            )
    except Exception as e:
        _falhar_grafico_seguro("Erro ao renderizar Mapa Geoespacial", e)