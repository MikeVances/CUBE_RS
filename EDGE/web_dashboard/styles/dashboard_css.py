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

    .metric-card.status-error {
        border: 1px solid rgba(220, 53, 69, 0.4);
        background-color: rgba(220, 53, 69, 0.08);
    }

    .metric-card.status-error .metric-card-marker {
        background-color: #dc3545;
    }

    .metric-card.status-ok .metric-card-marker {
        background-color: #238636;
    }
    .metric-card small {
        color: var(--edge-muted);
    }

    /* Карточки назначений реле */
    .relay-section {
        margin-top: 16px;
    }
    .relay-section h5 {
        margin-bottom: 8px;
    }
    .relay-category {
        margin-bottom: 14px;
    }
    .relay-category-title {
        font-size: 0.85rem;
        color: var(--edge-muted);
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .relay-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
    }
    .relay-card {
        background-color: var(--edge-panel-light);
        border: 1px solid var(--edge-border);
        border-radius: 8px;
        padding: 10px;
    }
    .relay-card small {
        color: var(--edge-muted);
    }
    .relay-card-channel {
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--edge-text);
        margin-top: 2px;
    }
    .relay-card-meta {
        font-size: 0.75rem;
        color: var(--edge-muted);
        margin-top: 2px;
    }
    .relay-card-state {
        display: inline-flex;
        align-items: center;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        margin-top: 8px;
        font-weight: 600;
    }
    .relay-card-state.relay-state-on {
        background-color: rgba(46, 160, 67, 0.2);
        color: #2ea043;
    }
    .relay-card-state.relay-state-off {
        background-color: rgba(255, 255, 255, 0.1);
        color: #c9d1d9;
    }
    .relay-card-state.relay-state-unknown {
        background-color: rgba(210, 153, 34, 0.25);
        color: #d29922;
    }
    .relay-card-state.relay-state-assigned {
        background-color: rgba(99, 110, 123, 0.25);
        color: #c9d1d9;
    }
    .relay-card-state.relay-state-emergency.relay-state-on {
        background-color: rgba(220, 53, 69, 0.25);
        color: #dc3545;
    }
    .relay-card-state.relay-state-emergency.relay-state-off {
        background-color: rgba(46, 160, 67, 0.2);
        color: #2ea043;
    }

    .relay-pill {
        display: inline-flex;
        align-items: center;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-left: 6px;
    }
    .relay-pill.relay-pill-on {
        background-color: rgba(46, 160, 67, 0.2);
        color: #2ea043;
    }
    .relay-pill.relay-pill-off {
        background-color: rgba(255, 255, 255, 0.1);
        color: #c9d1d9;
    }
    .relay-pill.relay-pill-unknown {
        background-color: rgba(210, 153, 34, 0.25);
        color: #d29922;
    }
    .relay-pill.relay-pill-emergency.relay-pill-on {
        background-color: rgba(220, 53, 69, 0.25);
        color: #dc3545;
    }
    .relay-pill.relay-pill-emergency.relay-pill-off {
        background-color: rgba(46, 160, 67, 0.2);
        color: #2ea043;
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
