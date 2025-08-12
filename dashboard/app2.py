import streamlit as st
import plotly.graph_objects as go
import numpy as np

# Тестовые значения
current_temp = 22.1
setpoint_temp = 21.5
min_temp = 0
max_temp = 40

# Цветовые зоны
zones = [
    (min_temp, 15, "#3ac6f7"),   # Холод
    (15, 25, "#a6f77b"),         # Норма
    (25, max_temp, "#ffe066")    # Тепло
]

# Иконки по дуге (эмодзи)
icons = [
    ("🔥", 30),   # Огонь (нагрев)
    ("💨", 0),    # Вентилятор (вверху)
    ("❄️", -30)   # Снежинка (охлаждение)
]

def gauge_arc(fig, r=0.9, width=0.12, theta0=-225, theta1=45, color="#444"):
    # Добавляет дугу на фигуру Plotly
    fig.add_shape(
        type="path",
        path=describe_arc(0, 0, r, theta0, theta1, width),
        line_color=color,
        fillcolor=color,
        layer="below"
    )

def describe_arc(x, y, r, start_angle, end_angle, width):
    # SVG path для дуги толщиной width
    start_rad = np.deg2rad(start_angle)
    end_rad = np.deg2rad(end_angle)
    r_outer = r
    r_inner = r - width
    x0 = x + r_outer * np.cos(start_rad)
    y0 = y + r_outer * np.sin(start_rad)
    x1 = x + r_outer * np.cos(end_rad)
    y1 = y + r_outer * np.sin(end_rad)
    x2 = x + r_inner * np.cos(end_rad)
    y2 = y + r_inner * np.sin(end_rad)
    x3 = x + r_inner * np.cos(start_rad)
    y3 = y + r_inner * np.sin(start_rad)
    large_arc = 1 if end_angle - start_angle > 180 else 0
    path = (
        f"M {x0},{y0} "
        f"A {r_outer},{r_outer} 0 {large_arc} 1 {x1},{y1} "
        f"L {x2},{y2} "
        f"A {r_inner},{r_inner} 0 {large_arc} 0 {x3},{y3} "
        f"Z"
    )
    return path

# Создаём фигуру
fig = go.Figure()

# Цветные зоны
for z_start, z_end, color in zones:
    theta0 = -225 + 270 * (z_start - min_temp) / (max_temp - min_temp)
    theta1 = -225 + 270 * (z_end - min_temp) / (max_temp - min_temp)
    gauge_arc(fig, r=1, width=0.18, theta0=theta0, theta1=theta1, color=color)

# Тонкая линия-указатель (target)
theta_target = -225 + 270 * (setpoint_temp - min_temp) / (max_temp - min_temp)
fig.add_shape(type="line",
    x0=0, y0=0, x1=0.82*np.cos(np.deg2rad(theta_target)), y1=0.82*np.sin(np.deg2rad(theta_target)),
    line=dict(color="#ff4b4b", width=5),
    layer="above"
)

# Основная стрелка (текущая температура)
theta_val = -225 + 270 * (current_temp - min_temp) / (max_temp - min_temp)
fig.add_shape(type="line",
    x0=0, y0=0, x1=0.7*np.cos(np.deg2rad(theta_val)), y1=0.7*np.sin(np.deg2rad(theta_val)),
    line=dict(color="#00ff00", width=12),
    layer="above"
)

# Центральная температура
fig.add_trace(go.Scatter(
    x=[0], y=[-0.15],
    text=[f"<span style='font-size:60px;'>{current_temp:.1f}°</span>"],
    mode="text",
    showlegend=False
))

# Подпись целевой температуры
fig.add_trace(go.Scatter(
    x=[0], y=[-0.35],
    text=[f"<span style='font-size:22px;color:#aaa'>Цель: {setpoint_temp:.1f}°</span>"],
    mode="text",
    showlegend=False
))

# Иконки по дуге
for icon, angle in icons:
    x = 0.92 * np.cos(np.deg2rad(angle))
    y = 0.92 * np.sin(np.deg2rad(angle))
    fig.add_trace(go.Scatter(
        x=[x], y=[y],
        text=[f"<span style='font-size:32px'>{icon}</span>"],
        mode="text",
        showlegend=False
    ))

# Настройки осей и фона
fig.update_xaxes(visible=False, range=[-1.1, 1.1])
fig.update_yaxes(visible=False, range=[-1.1, 1.1])
fig.update_layout(
    width=700, height=500,
    margin=dict(l=0, r=0, t=60, b=0),
    paper_bgcolor="#222",
    plot_bgcolor="#222",
    font=dict(color="#d0ffb7", family="Arial"),
    title=dict(text="<b>Temperature</b>", x=0.5, y=0.95, font=dict(size=36)),
)

st.set_page_config(page_title="Temperature Gauge", layout="centered")
st.plotly_chart(fig, use_container_width=True) 