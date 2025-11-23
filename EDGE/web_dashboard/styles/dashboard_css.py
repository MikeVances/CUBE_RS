"""
file: EDGE/web_dashboard/styles/dashboard_css.py
description: Общие стили для Streamlit-дэшборда EDGE.
"""

from __future__ import annotations

__all__ = ["DASHBOARD_CSS"]


DASHBOARD_CSS = """
<style>
    /* Палитра темы */
    :root {
        --edge-bg: #0d1117;
        --edge-panel: #161b22;
        --edge-panel-dark: #1c2128;
        --edge-panel-light: #21262d;
        --edge-border: #30363d;
        --edge-text: #e6edf3;
        --edge-muted: #8b949e;
        --edge-accent: #58a6ff;
    }

    /* Общий фон приложения */
    .stApp {
        background-color: var(--edge-bg);
        color: var(--edge-text);
    }

    /* Заголовки и Markdown */
    h1, h2, h3, h4, h5, h6,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        color: var(--edge-accent) !important;
    }

    /* Сайдбар и его содержимое */
    section[data-testid="stSidebar"],
    div[data-testid="stSidebarContent"],
    .css-1d391kg {
        background-color: #0b0f15 !important;
        color: var(--edge-text) !important;
    }

    div[data-testid="stHeader"],
    div[data-testid="stToolbar"] {
        background-color: var(--edge-bg) !important;
        border-bottom: 1px solid var(--edge-border);
    }

    div[data-testid="stDecoration"] {
        background: var(--edge-bg) !important;
    }

    section[data-testid="stSidebar"] * {
        color: var(--edge-text) !important;
    }

    .stSidebar h1, .stSidebar h2, .stSidebar h3,
    .stSidebar div, .stSidebar p, .stSidebar button,
    .stSidebar a {
        color: var(--edge-text) !important;
    }

    /* Кнопки */
    .stButton button {
        background-color: var(--edge-panel-light);
        color: var(--edge-text);
        border: 1px solid var(--edge-border);
        border-radius: 6px;
    }
    .stButton button:hover {
        border-color: var(--edge-accent);
    }

    /* Табы */
    .stTabs [data-baseweb="tab"] {
        color: var(--edge-muted);
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab"] > div {
        border-bottom: 2px solid transparent;
    }
    .stTabs [aria-selected="true"] > div {
        border-bottom: 2px solid var(--edge-accent);
        color: var(--edge-text);
    }

    /* Элементы управления */
    .stExpander, .stCheckbox, .stSelectbox {
        color: var(--edge-text);
    }

    .stExpander details {
        border: 1px solid var(--edge-border);
        border-radius: 8px;
        background-color: var(--edge-panel);
        margin-bottom: 10px;
    }

    .stExpander summary {
        background-color: var(--edge-panel-dark);
        color: var(--edge-text);
        padding: 8px 12px;
        border-radius: 8px 8px 0 0;
    }

    .stExpander summary:hover {
        border-color: var(--edge-accent);
    }

    .stExpander details[open] {
        background-color: var(--edge-panel);
    }

    .stExpander span,
    label[data-baseweb="checkbox"],
    label[data-baseweb="checkbox"] > div {
        color: var(--edge-text) !important;
    }


    label[data-baseweb="checkbox"] > div {
        color: var(--edge-text) !important;
    }

    /* Контейнеры помещений */
    .room-frame {
        background-color: var(--edge-panel);
        border: 1px solid var(--edge-border);
        border-radius: 16px;
        padding: 18px 18px 12px;
        margin-bottom: 22px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }

    .room-frame .stTabs {
        margin-top: 10px;
    }

    /* Карточки помещений и overview */
    .overview-card, .room-panel {
        background-color: var(--edge-panel);
        border: 1px solid var(--edge-border);
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 16px;
    }

    /* KPI-тайлы */
    .kpi-box {
        background-color: var(--edge-panel-light);
        border-left: 4px solid var(--edge-accent);
        border-radius: 8px;
        padding: 14px 18px;
    }
    .kpi-box h4 {
        margin: 0;
        color: var(--edge-muted);
        font-size: 0.9rem;
    }
    .kpi-box p {
        margin: 6px 0 0;
        font-size: 1.6rem;
        color: var(--edge-text);
    }

    /* Сетка метрик помещений и устройств */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        width: 100%;
    }
    .metric-card {
        background-color: var(--edge-panel-light);
        border-radius: 8px;
        border: 1px solid var(--edge-border);
        padding: 12px;
    }
    .metric-card small {
        color: var(--edge-muted);
    }

    /* Карточки устройств */
    .device-card {
        background-color: var(--edge-panel-dark);
        border-radius: 8px;
        border: 1px solid var(--edge-border);
        padding: 12px;
        margin-bottom: 10px;
    }

    /* Индикаторы статуса */
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
</style>
"""
