import streamlit as st

MAPA_MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

MESES_CURTO = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

ESTILO_PAINEL = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --marca:          #02d6d6;
    --sidebar:        #041355;
    --fundo:          #141414;
    --cartao:         #d4d4d4;
    --cartao-escura:  #1b1b1f;
    --tinta:          #141414;
    --tinta-suave:    #2b2b2b;
    --linha:          #E2E8F0;
    --borda-escura:   rgba(255, 255, 255, 0.11);
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, sans-serif !important;
}

.stApp { background-color: var(--fundo) !important; }

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 1550px;
}

.stAppDeployButton, [data-testid="stElementToolbar"], [data-testid="stHeaderActionElements"] {
    display: none !important;
}

/* Títulos e textos sobre o fundo escuro principal (#141414) */
[data-testid="stAppViewContainer"] h1 {
    color: #F8FAFC !important;
    font-weight: 800 !important;
}
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {
    color: #E2E8F0 !important;
    font-weight: 600 !important;
}
[data-testid="stCaptionContainer"] * {
    color: #A1A1AA !important;
}
[data-testid="stWidgetLabel"] p {
    color: #E4E4E7 !important;
    font-weight: 600 !important;
}

/* Containers com borda (gráficos e barra de filtros do mapa) em tom escuro consistente */
[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stLayoutWrapper"] > div[style*="border"] {
    background: var(--cartao-escura) !important;
    border: 1px solid var(--borda-escura) !important;
    border-radius: 12px !important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stWidgetLabel"] p,
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p,
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] *,
[data-testid="stVerticalBlockBorderWrapper"] h3 {
    color: var(--cartao) !important;
}

/* Cards de KPI (#d4d4d4 com faixa superior ciano #02d6d6) */
[data-testid="stMetric"] {
    background: var(--cartao) !important;
    border: 1px solid var(--linha) !important;
    border-top: 3px solid var(--marca) !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
    transition: transform .15s ease, box-shadow .15s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(2, 214, 214, 0.18) !important;
}
[data-testid="stMetricLabel"] * {
    color: var(--tinta-suave) !important;
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] * {
    color: var(--tinta) !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
}

/* Sidebar azul marinho (#041355) */
[data-testid="stSidebar"] { background-color: var(--sidebar) !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *,
[data-testid="stSidebar"] summary span,
[data-testid="stSidebar"] label {
    color: #F8FAFC !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255, 255, 255, 0.08) !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255, 255, 255, 0.18) !important;
    border-left: 4px solid transparent !important;
    border-radius: 8px !important;
    justify-content: flex-start !important;
    font-weight: 600 !important;
    transition: all .15s ease;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(2, 214, 214, 0.22) !important;
    border-left-color: var(--marca) !important;
}

/* Divisor de seção com barra lateral ciano */
.secao { display: flex; align-items: center; gap: 10px; margin: 0.4rem 0 0.8rem; }
.secao-barra { width: 4px; height: 20px; background: var(--marca); border-radius: 99px; }
.secao-texto { font-size: 1.02rem; font-weight: 700; color: var(--cartao); }
.secao-nota { font-size: 0.78rem; color: #A1A1AA; margin-left: auto; }

/* Selo discreto de status do pipeline */
.selo-pipeline {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 4px 11px;
    border-radius: 99px;
    font-size: 0.74rem;
    font-weight: 600;
    margin-top: 0.25rem;
}
.selo-ponto { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.selo-ok { background: rgba(16, 185, 129, 0.14); color: #34D399; border: 1px solid rgba(52, 211, 153, 0.3); }
.selo-backup { background: rgba(245, 158, 11, 0.16); color: #FBBF24; border: 1px solid rgba(251, 191, 36, 0.35); }
</style>
"""


def aplicar_estilo() -> None:
    """Injeta a folha de estilos CSS na página atual."""
    st.markdown(ESTILO_PAINEL, unsafe_allow_html=True)


def secao(titulo: str, nota: str = "") -> None:
    """Cabeçalho de seção padronizado com barra ciano à esquerda."""
    nota_html = f'<span class="secao-nota">{nota}</span>' if nota else ""
    st.markdown(
        f'<div class="secao"><div class="secao-barra"></div>'
        f'<span class="secao-texto">{titulo}</span>{nota_html}</div>',
        unsafe_allow_html=True,
    )


def selo_status_dados(status_dict: dict, modo_clone: bool = False) -> None:
    """Exibe um selo discreto informando a origem dos dados e horário da carga."""
    quando = status_dict.get("quando")
    hora_str = f" · {quando.strftime('%H:%M:%S')}" if quando else ""

    if modo_clone:
        classe = "selo-backup"
        texto = f"Contingência Ativa (Clone) · Snapshot Local{hora_str}"
    elif status_dict.get("estado") == "ok":
        classe = "selo-ok"
        ms = status_dict.get("latencia_ms", 0)
        texto = f"Pipeline Ativo · Excel Oficial ({ms:.0f} ms){hora_str}"
    else:
        classe = "selo-backup"
        texto = f"Fallback de Dados · Snapshot CSV{hora_str}"

    st.markdown(
        f'<div class="selo-pipeline {classe}"><span class="selo-ponto"></span>{texto}</div>',
        unsafe_allow_html=True,
    )


def formatar_moeda(valor: float) -> str:
    """Formata valores em R$ abreviado (mil / mi) no padrão brasileiro."""
    sinal = "-" if valor < 0 else ""
    v = abs(float(valor))
    if v >= 1_000_000:
        num = f"{v / 1_000_000:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{sinal}R$ {num} mi"
    if v >= 1_000:
        num = f"{v / 1_000:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{sinal}R$ {num} mil"
    num = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {num}"
