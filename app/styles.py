"""
Global CSS styles injected into every Streamlit page.
Call inject_styles() at the top of each page render.
"""
import streamlit as st # type: ignore


def inject_styles():
    st.markdown("""
    <style>
    /* ── Google Font ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Global ── */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* ── Hide Streamlit default chrome ── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* ── Main content padding ── */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1100px;
    }

    /* ── Page title ── */
    h1 {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #1a1a2e !important;
        margin-bottom: 0.25rem !important;
    }

    /* ── Section headings ── */
    h2 {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        color: #1a1a2e !important;
        margin-top: 1.5rem !important;
        margin-bottom: 0.5rem !important;
    }

    h3 {
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        color: #2c3e50 !important;
    }

    /* ── Body text ── */
    p, li, .stMarkdown {
        font-size: 0.95rem !important;
        color: #2c3e50 !important;
        line-height: 1.6 !important;
    }

    /* ── Caption / small text ── */
    .stCaption, small {
        font-size: 0.8rem !important;
        color: #7f8c8d !important;
    }

    /* ── Primary button ── */
    .stButton > button[kind="primary"] {
        background-color: #2980b9 !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 1.2rem !important;
        transition: background-color 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #2471a3 !important;
    }

    /* ── Secondary button ── */
    .stButton > button:not([kind="primary"]) {
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        border: 1px solid #bdc3c7 !important;
        color: #2c3e50 !important;
        background-color: white !important;
        transition: border-color 0.2s ease !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        border-color: #2980b9 !important;
        color: #2980b9 !important;
    }

    /* ── Input fields ── */
    .stTextInput > div > div > input {
        border-radius: 6px !important;
        border: 1px solid #bdc3c7 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 0.75rem !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #2980b9 !important;
        box-shadow: 0 0 0 2px rgba(41,128,185,0.15) !important;
    }

    /* ── Select box ── */
    .stSelectbox > div > div {
        border-radius: 6px !important;
        border: 1px solid #bdc3c7 !important;
        font-size: 0.9rem !important;
    }

    /* ── Radio buttons ── */
    .stRadio > div {
        gap: 0.4rem !important;
    }
    .stRadio label {
        font-size: 0.9rem !important;
        color: #2c3e50 !important;
        padding: 0.4rem 0 !important;
    }

    /* ── Progress bar ── */
    .stProgress > div > div > div {
        background-color: #2980b9 !important;
        border-radius: 4px !important;
    }
    .stProgress > div > div {
        background-color: #ecf0f1 !important;
        border-radius: 4px !important;
    }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        color: #2c3e50 !important;
        background-color: #f8f9fa !important;
        border-radius: 6px !important;
        border: 1px solid #ecf0f1 !important;
    }
    .streamlit-expanderContent {
        border: 1px solid #ecf0f1 !important;
        border-top: none !important;
        border-radius: 0 0 6px 6px !important;
        padding: 0.75rem !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px !important;
        border-bottom: 2px solid #ecf0f1 !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        color: #7f8c8d !important;
        border-radius: 6px 6px 0 0 !important;
        padding: 0.5rem 1.2rem !important;
        border: none !important;
        background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: #2980b9 !important;
        border-bottom: 2px solid #2980b9 !important;
        font-weight: 600 !important;
    }

    /* ── Metric cards ── */
    [data-testid="metric-container"] {
        background-color: #f8f9fa !important;
        border: 1px solid #ecf0f1 !important;
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    [data-testid="metric-container"] label {
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        color: #7f8c8d !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #1a1a2e !important;
    }

    /* ── Alerts ── */
    .stAlert {
        border-radius: 6px !important;
        font-size: 0.9rem !important;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #1a1a2e !important;
        padding-top: 1rem !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        background-color: transparent !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        color: #ecf0f1 !important;
        font-size: 0.85rem !important;
        text-align: left !important;
        border-radius: 6px !important;
        margin-bottom: 2px !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: rgba(255,255,255,0.1) !important;
        border-color: rgba(255,255,255,0.3) !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] .stCaption {
        color: #ecf0f1 !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.15) !important;
    }

    /* ── Form ── */
    [data-testid="stForm"] {
        border: 1px solid #ecf0f1 !important;
        border-radius: 8px !important;
        padding: 1.5rem !important;
        background-color: #ffffff !important;
    }

    /* ── Divider ── */
    hr {
        border: none !important;
        border-top: 1px solid #ecf0f1 !important;
        margin: 1rem 0 !important;
    }

    /* ── Download button ── */
    .stDownloadButton > button {
        background-color: #27ae60 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }
    .stDownloadButton > button:hover {
        background-color: #229954 !important;
    }

    /* ── Info / warning / error boxes ── */
    [data-testid="stInfoBox"] {
        border-radius: 6px !important;
        font-size: 0.9rem !important;
    }

    /* ── Spinner ── */
    .stSpinner > div {
        border-top-color: #2980b9 !important;
    }
    </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = None):
    """Render a consistent page header."""
    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem;">
            <h1 style="margin-bottom: 0.25rem;">{title}</h1>
            {f'<p style="color: #7f8c8d; font-size: 0.9rem; margin-top: 0;">{subtitle}</p>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True
    )


def tier_badge(tier: int, label: str, score: float, size: str = "large"):
    """Render a color-coded maturity tier badge."""
    colors = {
        1: ("#e74c3c", "#fdecea"),
        2: ("#e67e22", "#fef3e2"),
        3: ("#f1c40f", "#fefde2"),
        4: ("#2980b9", "#e8f4fb"),
        5: ("#27ae60", "#e9f7ef"),
    }
    color, bg = colors.get(tier, ("#95a5a6", "#f8f9fa"))
    font_size = "2.2rem" if size == "large" else "1.1rem"
    score_size = "1.1rem" if size == "large" else "0.85rem"

    st.markdown(
        f"""
        <div style="
            background-color: {bg};
            border-left: 6px solid {color};
            padding: 1.25rem 1.5rem;
            border-radius: 8px;
            margin-bottom: 1.5rem;
        ">
            <div style="font-size: 0.8rem; color: #7f8c8d; margin-bottom: 0.25rem;
                        text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500;">
                Overall Maturity Level
            </div>
            <div style="font-size: {font_size}; font-weight: 700; color: {color};">
                Level {tier} — {label}
            </div>
            <div style="font-size: {score_size}; color: #2c3e50; margin-top: 0.25rem; font-weight: 500;">
                Overall Score: <strong>{score:.2f} / 5.00</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def stat_card(label: str, value: str, color: str = "#2980b9"):
    """Render a simple stat card."""
    st.markdown(
        f"""
        <div style="
            background: white;
            border: 1px solid #ecf0f1;
            border-top: 3px solid {color};
            border-radius: 8px;
            padding: 1rem 1.25rem;
            text-align: center;
        ">
            <div style="font-size: 0.75rem; color: #7f8c8d; text-transform: uppercase;
                        letter-spacing: 0.05em; font-weight: 500; margin-bottom: 0.5rem;">
                {label}
            </div>
            <div style="font-size: 1.6rem; font-weight: 700; color: #1a1a2e;">
                {value}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )