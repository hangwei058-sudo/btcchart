import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

st.set_page_config(layout="wide")

TIME_CONFIG = {
    "5m": "5min", "7m": "7min", "10m": "10min", "15m": "15min", "20m": "20min",
    "30m": "30min", "45m": "45min", "1h": "1h", "90m": "90min", "2h": "2h",
    "3h": "3h", "4h": "4h", "5h": "5h", "6h": "6h", "7h": "7h",
    "8h": "8h", "10h": "10h", "12h": "12h", "1d": "1d", "2d": "2d",
    "3d": "3d", "10d": "10d"
}

st.sidebar.title("周期选择")
selected_label = st.sidebar.selectbox("选择:", list(TIME_CONFIG.keys()), index=3)
rule = TIME_CONFIG[selected_label]

# 根据选择的周期，动态决定要抓多少条1分钟数据，确保重采样后至少有几百根K线
MIN_BARS_NEEDED = 500  # 至少要保证有这么多根重采样后的K线
PERIOD_MINUTES = {
    "5m": 5, "7m": 7, "10m": 10, "15m": 15, "20m": 20, "30m": 30, "45m": 45,
    "1h": 60, "90m": 90, "2h": 120, "3h": 180, "4h": 240, "5h": 300, "6h": 360,
    "7h": 420, "8h": 480, "10h": 600, "12h": 720, "1d": 1440, "2d": 2880,
    "3d": 4320, "10d": 14400
}

@st.cache_data(ttl=60)
def fetch_all_ohlcv(symbol, timeframe, total_limit):
    exchange = ccxt.binance()
    per_call = 1000
    all_bars = []
    since = exchange.milliseconds() - total_limit * 60 * 1000
    while len(all_bars) < total_limit:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=per_call)
        if not bars:
            break
        all_bars += bars
        since = bars[-1][0] + 60 * 1000
        if len(bars) < per_call:
            break
        time.sleep(exchange.rateLimit / 1000)
    return all_bars

@st.cache_data(ttl=60)
def get_data(rule, label):
    # 动态计算需要多少1分钟数据：(目标K线数 + MACD所需的35个周期缓冲) * 每根K线分钟数
    minutes_per_bar = PERIOD_MINUTES[label]
    needed_minutes = (MIN_BARS_NEEDED + 50) * minutes_per_bar
    total_limit = max(needed_minutes, 6000)
    total_limit = min(total_limit, 50000)  # 防止请求量过大

    bars = fetch_all_ohlcv('BTC/USDT', '1m', total_limit)
    df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    df = df[~df.index.duplicated(keep='last')].sort_index()

    resampled = df.resample(rule).agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    ).dropna(subset=['open', 'high', 'low', 'close'])

    macd = resampled.ta.macd(close='close', fast=12, slow=26, signal=9)
    resampled['macd'] = macd.iloc[:, 0]
    resampled['macd_h'] = macd.iloc[:, 1]
    resampled['macd_s'] = macd.iloc[:, 2]

    return resampled

df = get_data(rule, selected_label)
st.write(f"共加载 {len(df)} 条 {selected_label} K线")

fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
    row_heights=[0.7, 0.3]
)

fig.add_trace(go.Candlestick(
    x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'],
    name='K线',
    increasing_line_color='#26A69A', increasing_fillcolor='#26A69A',
    decreasing_line_color='#FF5252', decreasing_fillcolor='#FF5252'
), row=1, col=1)

# 用同一个 df（不单独 dropna 子集），保证 K线和MACD的x轴完全对齐
colors = ['#26A69A' if (pd.notna(v) and v >= 0) else '#FF5252' for v in df['macd_h']]

fig.add_trace(go.Bar(x=df.index, y=df['macd_h'], marker_color=colors, name='MACD柱'), row=2, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['macd'], line=dict(color='blue', width=1.5),
                          name='DIF', connectgaps=False), row=2, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['macd_s'], line=dict(color='orange', width=1.5),
                          name='DEA', connectgaps=False), row=2, col=1)

fig.update_layout(
    height=800,
    xaxis_rangeslider_visible=False,   # 关闭底部小K线缩略图
    dragmode='pan',
    showlegend=False,
    margin=dict(l=40, r=40, t=40, b=40)
)
fig.update_yaxes(title_text="价格", row=1, col=1)
fig.update_yaxes(title_text="MACD", row=2, col=1, autorange=True)

st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
