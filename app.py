import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import numpy as np
import json
import time

# ----------------- 页面配置 -----------------
st.set_page_config(
    page_title="Pro Trading Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------- 自定义专业金融终端 CSS -----------------
st.markdown("""
<style>
  html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], .block-container {
    background: #0e1117 !important;
    color: #d1d4dc !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  .block-container {
    padding: 0.2rem 0.5rem 0 !important;
    max-width: 100% !important;
  }
  [data-testid="stVerticalBlock"] {
    gap: 0.15rem !important;
  }
  header, footer {
    display: none !important;
  }

  /* 紧凑型胶囊按钮 */
  .stButton button {
    background: #1e222d !important;
    color: #9db2c6 !important;
    border: 1px solid #2a2e39 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    height: 32px !important;
    min-height: 32px !important;
    padding: 0 10px !important;
    border-radius: 6px !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
  }
  .stButton button:hover {
    background: #2a2e39 !important;
    color: #2962ff !important;
    border-color: #2962ff !important;
  }
  .stButton button:active {
    background: #2962ff !important;
    color: #ffffff !important;
    transform: scale(0.96) !important;
  }

  /* 下拉选单美化 */
  [data-testid="stSelectbox"] > div > div {
    background: #1e222d !important;
    color: #f0f3fa !important;
    border: 1px solid #2a2e39 !important;
    border-radius: 6px !important;
    min-height: 32px !important;
    height: 32px !important;
  }
  [data-testid="stSelectbox"] > div > div > div {
    color: #f0f3fa !important;
    font-weight: 600 !important;
    font-size: 13px !important;
  }
  [data-testid="stSelectbox"] svg {
    fill: #787b86 !important;
  }
  div[data-baseweb="popover"] ul {
    background: #1e222d !important;
    border: 1px solid #2a2e39 !important;
    border-radius: 6px !important;
  }
  div[data-baseweb="popover"] li {
    background: #1e222d !important;
    color: #d1d4dc !important;
    font-size: 13px !important;
  }
  div[data-baseweb="popover"] li:hover {
    background: #2962ff !important;
    color: #ffffff !important;
  }
</style>
""", unsafe_allow_html=True)

# ----------------- 参数与周期字典 -----------------
SYMBOL_CONFIG = {"黄金 GOLD": "GC=F", "BTC/USDT": "BTC/USDT"}
TIME_CONFIG = {
    "7m":"7min","10m":"10min","15m":"15min","20m":"20min",
    "23m":"23min","30m":"30min","45m":"45min","90m":"90min",
    "1h":"1h","2h":"2h","3h":"3h","4h":"4h","6h":"6h",
    "8h":"8h","10h":"10h","12h":"12h","16h":"16h",
    "1d":"1D","2d":"2D","3d":"3D","4d":"4D","5d":"5D",
    "6d":"6D","7d":"7D","8d":"8D","9d":"9D","10d":"10D",
    "15d":"15D","20d":"20D","45d":"45D",
}
BAR_SECONDS = {
    "7m":420,"10m":600,"15m":900,"20m":1200,"23m":1380,
    "30m":1800,"45m":2700,"90m":5400,
    "1h":3600,"2h":7200,"3h":10800,"4h":14400,"6h":21600,
    "8h":28800,"10h":36000,"12h":43200,"16h":57600,
    "1d":86400,"2d":172800,"3d":259200,"4d":345600,"5d":432000,
    "6d":518400,"7d":604800,"8d":691200,"9d":777600,"10d":864000,
    "15d":1296000,"20d":1728000,"45d":3888000,
}
period_keys = list(TIME_CONFIG.keys())

if "selected_label" not in st.session_state:
    st.session_state.selected_label = "1h"
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "黄金 GOLD"

# ----------------- 顶部紧凑控制栏 -----------------
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([0.25, 0.25, 0.12, 0.38])

with ctrl_c1:
    is_gold = (st.session_state.selected_symbol == "黄金 GOLD")
    if st.button("✦ 黄金 GOLD" if is_gold else "黄金 GOLD", key="btn_gold", use_container_width=True):
        st.session_state.selected_symbol = "黄金 GOLD"
        st.rerun()

with ctrl_c2:
    is_btc = (st.session_state.selected_symbol == "BTC/USDT")
    if st.button("✦ BTC/USDT" if is_btc else "BTC/USDT", key="btn_btc", use_container_width=True):
        st.session_state.selected_symbol = "BTC/USDT"
        st.rerun()

with ctrl_c3:
    c_prev, c_next = st.columns(2)
    with c_prev:
        if st.button("◀", key="btn_prev", use_container_width=True):
            idx = period_keys.index(st.session_state.selected_label)
            st.session_state.selected_label = period_keys[(idx - 1) % len(period_keys)]
            st.rerun()
    with c_next:
        if st.button("▶", key="btn_next", use_container_width=True):
            idx = period_keys.index(st.session_state.selected_label)
            st.session_state.selected_label = period_keys[(idx + 1) % len(period_keys)]
            st.rerun()

with ctrl_c4:
    new_label = st.selectbox(
        "周期选择",
        period_keys,
        index=period_keys.index(st.session_state.selected_label),
        label_visibility="collapsed",
        key="select_period"
    )
    if new_label != st.session_state.selected_label:
        st.session_state.selected_label = new_label
        st.rerun()

selected_label = st.session_state.selected_label
selected_symbol_label = st.session_state.selected_symbol
symbol = SYMBOL_CONFIG[selected_symbol_label]
rule = TIME_CONFIG[selected_label]
bar_seconds = BAR_SECONDS.get(selected_label, 3600)
is_btc_symbol = (symbol == "BTC/USDT")

# ----------------- 数据抓取与重采样 -----------------
BASE_FETCH_LIMIT = 50000

def get_base_interval(r_str):
    r = r_str.lower()
    if r.endswith('d'): return 'day'
    elif r.endswith('h'): return 'hour'
    return 'minute'

@st.cache_data(ttl=120)
def fetch_btc_1m(total_limit):
    exchange = ccxt.okx()
    per_call = 300
    all_bars = []
    since = exchange.milliseconds() - total_limit * 60 * 1000
    now = exchange.milliseconds()
    while since < now:
        try:
            bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1m', since=since, limit=per_call)
            if not bars: break
            all_bars += bars
            last_ts = bars[-1][0]
            if last_ts <= since: break
            since = last_ts + 60 * 1000
            if len(all_bars) >= total_limit: break
        except Exception:
            break
    return all_bars

@st.cache_data(ttl=120)
def get_btc_base_df():
    bars = fetch_btc_1m(BASE_FETCH_LIMIT)
    if not bars:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    return df[~df.index.duplicated(keep='last')].sort_index()

@st.cache_data(ttl=300)
def get_gold_df(base_type):
    try:
        ticker = yf.Ticker("GC=F")
        if base_type == 'minute':
            df = ticker.history(period="60d", interval="5m")
        elif base_type == 'hour':
            df = ticker.history(period="730d", interval="1h")
        else:
            df = ticker.history(period="10y", interval="1d")
        if df.empty:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        df = df[['Open','High','Low','Close','Volume']]
        df.columns = ['open','high','low','close','volume']
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        return df[~df.index.duplicated(keep='last')].sort_index()
    except Exception:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

@st.cache_data(ttl=120)
def resample_data(cur_symbol, cur_rule):
    base_type = get_base_interval(cur_rule)
    df = get_gold_df(base_type) if cur_symbol == "GC=F" else get_btc_base_df()
    if df.empty:
        return pd.DataFrame()
    
    resampled = df.resample(cur_rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna(subset=['open','high','low','close'])
    
    if resampled.empty:
        return pd.DataFrame()
        
    ema12 = resampled['close'].ewm(span=12, adjust=False).mean()
    ema26 = resampled['close'].ewm(span=26, adjust=False).mean()
    resampled['macd']   = ema12 - ema26
    resampled['macd_s'] = resampled['macd'].ewm(span=9, adjust=False).mean()
    resampled['macd_h'] = resampled['macd'] - resampled['macd_s']
    resampled['ema24']  = resampled['close'].ewm(span=24, adjust=False).mean()
    resampled['ema52']  = resampled['close'].ewm(span=52, adjust=False).mean()
    resampled['ema104'] = resampled['close'].ewm(span=104, adjust=False).mean()
    return resampled.tail(2000)

df = resample_data(symbol, rule)

candles, ema24_data, ema52_data, ema104_data = [], [], [], []
macd_data, signal_data, hist_data = [], [], []
prev_h = None

if not df.empty:
    for idx, row in df.iterrows():
        t = int(idx.timestamp())
        candles.append({
            "time": t,
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close'])
        })
        if pd.notna(row['ema24']):  ema24_data.append({"time": t, "value": float(row['ema24'])})
        if pd.notna(row['ema52']):  ema52_data.append({"time": t, "value": float(row['ema52'])})
        if pd.notna(row['ema104']): ema104_data.append({"time": t, "value": float(row['ema104'])})
        if pd.notna(row['macd']):   macd_data.append({"time": t, "value": float(row['macd'])})
        if pd.notna(row['macd_s']): signal_data.append({"time": t, "value": float(row['macd_s'])})
        if pd.notna(row['macd_h']):
            v = float(row['macd_h'])
            if v >= 0:
                color = "#089981" if (prev_h is None or pd.isna(prev_h) or v >= prev_h) else "rgba(8,153,129,0.4)"
            else:
                color = "#f23645" if (prev_h is None or pd.isna(prev_h) or v <= prev_h) else "rgba(242,54,69,0.4)"
            hist_data.append({"time": t, "value": v, "color": color})
            prev_h = v

last_price = candles[-1]['close'] if candles else 0.0
last_open  = candles[-1]['open']  if candles else 0.0
last_candle_time = candles[-1]['time'] if candles else 0

data_json = json.dumps({
    "candles": candles,
    "ema24": ema24_data,
    "ema52": ema52_data,
    "ema104": ema104_data,
    "macd": macd_data,
    "signal": signal_data,
    "hist": hist_data,
})

current_label_text = f"{selected_symbol_label} · {selected_label}"

# ----------------- 前端 Lightweight Charts HTML/JS -----------------
html_content = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0;
    background: #131722;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, sans-serif;
    color: #d1d4dc;
  }}
  #wrap1 {{ position: relative; width: 100%; }}
  #chart1, #chart2 {{ width: 100%; }}

  /* 顶部 HUD 数据联动栏 */
  #hudBar {{
    position: absolute; top: 8px; left: 10px;
    z-index: 50; display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
    pointer-events: none; user-select: none;
    font-size: 11px; font-family: monospace;
  }}
  .hud-badge {{
    background: rgba(30, 34, 45, 0.85);
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 4px; padding: 3px 8px;
    font-weight: 700; color: #2962ff; font-size: 12px;
  }}
  .hud-item {{
    background: rgba(19, 23, 34, 0.7);
    padding: 2px 6px; border-radius: 3px;
    border: 1px solid rgba(255, 255, 255, 0.05);
  }}
  .hud-val {{ font-weight: 600; margin-left: 2px; }}

  /* 悬浮微光行情卡片 */
  #floatBox {{
    position: absolute; top: 8px; right: 10px;
    background: rgba(20, 24, 35, 0.85);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    border-radius: 8px; padding: 8px 12px;
    z-index: 100; font-family: -apple-system, BlinkMacSystemFont, monospace;
    text-align: right; cursor: move; user-select: none;
    min-width: 130px; transition: border-color 0.2s;
  }}
  #floatBox:hover {{ border-color: rgba(41, 98, 255, 0.5); }}
  .box-header {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 10px; color: #787b86; margin-bottom: 2px;
  }}
  .live-dot {{
    width: 6px; height: 6px; border-radius: 50%;
    background: #089981; display: inline-block;
    box-shadow: 0 0 6px #089981; animation: pulse 1.8s infinite;
  }}
  @keyframes pulse {{
    0% {{ opacity: 0.4; transform: scale(0.9); }}
    50% {{ opacity: 1; transform: scale(1.15); }}
    100% {{ opacity: 0.4; transform: scale(0.9); }}
  }}
  #priceVal {{ font-size: 20px; font-weight: 800; color: #089981; line-height: 1.1; }}
  #priceDiff {{ font-size: 11px; font-weight: 600; color: #787b86; margin-top: 2px; }}
  #timerRow {{
    font-size: 11px; color: #f5c400; margin-top: 5px;
    border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 4px;
    display: flex; justify-content: space-between;
  }}
</style>
</head>
<body>
<div id="wrap1">
  <div id="hudBar">
    <div class="hud-badge">{current_label_text}</div>
    <div class="hud-item" id="hudOhlc">
      O<span class="hud-val" id="hudO">--</span>
      H<span class="hud-val" id="hudH">--</span>
      L<span class="hud-val" id="hudL">--</span>
      C<span class="hud-val" id="hudC">--</span>
    </div>
    <div class="hud-item">
      <span style="color:#ff9800;">EMA24:</span><span class="hud-val" id="hudE24">--</span>
      <span style="color:#ba68c8;margin-left:4px;">EMA52:</span><span class="hud-val" id="hudE52">--</span>
      <span style="color:#90caf9;margin-left:4px;">EMA104:</span><span class="hud-val" id="hudE104">--</span>
    </div>
  </div>

  <div id="floatBox">
    <div class="box-header">
      <span class="live-dot"></span>
      <span style="letter-spacing:0.5px;">LIVE FEED</span>
    </div>
    <div id="priceVal">{last_price:.2f}</div>
    <div id="priceDiff">-- (--.--%)</div>
    <div id="timerRow">
      <span style="color:#787b86;">K线倒计时</span>
      <span id="timerVal">--:--</span>
    </div>
  </div>

  <div id="chart1"></div>
</div>
<div id="chart2"></div>

<script>
const data = {data_json};
const BAR_SEC = {bar_seconds};
const LAST_TS = {last_candle_time};
const IS_BTC = {'true' if is_btc_symbol else 'false'};
const INIT_PRICE = {last_price};
const INIT_OPEN = {last_open};

/* --- 浮动挂件平滑拖拽 --- */
(function(){{
  const el = document.getElementById('floatBox');
  let ox, oy, sx, sy, drag = false;
  el.addEventListener('touchstart', e => {{
    const t = e.touches[0]; const r = el.getBoundingClientRect();
    ox = r.left; oy = r.top; sx = t.clientX; sy = t.clientY; drag = true;
    el.style.right = 'auto'; el.style.left = ox + 'px'; el.style.top = oy + 'px';
    e.preventDefault();
  }}, {{passive:false}});
  document.addEventListener('touchmove', e => {{
    if(!drag) return; const t = e.touches[0];
    el.style.left = (ox + t.clientX - sx) + 'px';
    el.style.top = (oy + t.clientY - sy) + 'px';
    e.preventDefault();
  }}, {{passive:false}});
  document.addEventListener('touchend', () => drag = false);

  el.addEventListener('mousedown', e => {{
    const r = el.getBoundingClientRect();
    ox = r.left; oy = r.top; sx = e.clientX; sy = e.clientY; drag = true;
    el.style.right = 'auto'; el.style.left = ox + 'px'; el.style.top = oy + 'px';
  }});
  document.addEventListener('mousemove', e => {{
    if(!drag) return;
    el.style.left = (ox + e.clientX - sx) + 'px';
    el.style.top = (oy + e.clientY - sy) + 'px';
  }});
  document.addEventListener('mouseup', () => drag = false);
}})();

/* --- 图表主题参数 --- */
const BG_THEME = '#131722';
const CHART_LAYOUT = {{
  background: {{ color: BG_THEME }},
  textColor: '#787b86',
  fontSize: 11,
}};
const GRID_STYLE = {{
  vertLines: {{ color: 'rgba(42, 46, 57, 0.45)' }},
  horzLines: {{ color: 'rgba(42, 46, 57, 0.45)' }},
}};
const TIME_SCALE = {{
  borderColor: 'rgba(42, 46, 57, 0.8)',
  timeVisible: true,
  secondsVisible: false,
}};
const LOC_CONFIG = {{
  timeFormatter: ts => {{
    const d = new Date((ts + 8 * 3600) * 1000);
    return String(d.getUTCMonth() + 1).padStart(2, '0') + '/' +
           String(d.getUTCDate()).padStart(2, '0') + ' ' +
           String(d.getUTCHours()).padStart(2, '0') + ':' +
           String(d.getUTCMinutes()).padStart(2, '0');
  }}
}};

const W = window.innerWidth;
const H = window.innerHeight || 680;
const H1 = Math.floor(H * 0.65);
const H2 = Math.floor(H * 0.33);

/* --- 主图 (K线 + EMA) --- */
const chart1 = LightweightCharts.createChart(document.getElementById('chart1'), {{
  width: W, height: H1, layout: CHART_LAYOUT, grid: GRID_STYLE,
  timeScale: TIME_SCALE, localization: LOC_CONFIG,
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: 'rgba(42, 46, 57, 0.8)', autoScale: true }},
}});

const candleSeries = chart1.addCandlestickSeries({{
  upColor: '#089981', downColor: '#f23645',
  borderUpColor: '#089981', borderDownColor: '#f23645',
  wickUpColor: '#089981', wickDownColor: '#f23645',
  lastValueVisible: true, priceLineVisible: true,
}});
candleSeries.setData(data.candles);

[['#ff9800', data.ema24], ['#ba68c8', data.ema52], ['#90caf9', data.ema104]].forEach(([color, sData]) => {{
  const s = chart1.addLineSeries({{
    color: color, lineWidth: 1.2,
    lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false
  }});
  s.setData(sData);
}});

/* --- 副图 (MACD) --- */
const chart2 = LightweightCharts.createChart(document.getElementById('chart2'), {{
  width: W, height: H2, layout: CHART_LAYOUT, grid: GRID_STYLE,
  timeScale: TIME_SCALE, localization: LOC_CONFIG,
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: 'rgba(42, 46, 57, 0.8)', autoScale: true }},
}});

const histSeries = chart2.addHistogramSeries({{
  lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false
}});
histSeries.setData(data.hist);

const macdLine = chart2.addLineSeries({{
  color: '#2962ff', lineWidth: 1.2, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false
}});
macdLine.setData(data.macd);

const signalLine = chart2.addLineSeries({{
  color: '#ff6d00', lineWidth: 1.2, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false
}});
signalLine.setData(data.signal);

/* --- 价格与倒计时刷新 --- */
function updatePriceBox(p, o) {{
  const el = document.getElementById('priceVal');
  const diff = p - o;
  const pct = o > 0 ? (diff / o * 100) : 0;
  const s = diff >= 0 ? '+' : '';
  el.textContent = p.toFixed(2);
  el.style.color = diff >= 0 ? '#089981' : '#f23645';
  const diffEl = document.getElementById('priceDiff');
  diffEl.textContent = s + diff.toFixed(2) + ' (' + s + pct.toFixed(2) + '%)';
  diffEl.style.color = diff >= 0 ? '#089981' : '#f23645';
}}
updatePriceBox(INIT_PRICE, INIT_OPEN);

function updateTimer() {{
  let rem = LAST_TS + BAR_SEC - Math.floor(Date.now() / 1000);
  let str = '';
  if (rem <= 0) {{
    str = '⏰ 已收盘';
  }} else if (rem >= 3600) {{
    const h = Math.floor(rem / 3600), m = Math.floor((rem % 3600) / 60), s = rem % 60;
    str = h + 'h ' + String(m).padStart(2,'0') + 'm ' + String(s).padStart(2,'0') + 's';
  }} else if (rem >= 60) {{
    const m = Math.floor(rem / 60), s = rem % 60;
    str = m + 'm ' + String(s).padStart(2,'0') + 's';
  }} else {{
    str = rem + 's';
  }}
  document.getElementById('timerVal').textContent = str;
}}
updateTimer();
setInterval(updateTimer, 1000);

/* --- 十字光标 HUD 联动 --- */
chart1.subscribeCrosshairMove(param => {{
  if (!param.time || !param.seriesData.get(candleSeries)) {{
    if (data.candles.length > 0) {{
      const last = data.candles[data.candles.length - 1];
      document.getElementById('hudO').textContent = last.open.toFixed(2);
      document.getElementById('hudH').textContent = last.high.toFixed(2);
      document.getElementById('hudL').textContent = last.low.toFixed(2);
      document.getElementById('hudC').textContent = last.close.toFixed(2);
    }}
    return;
  }}
  const c = param.seriesData.get(candleSeries);
  if (c) {{
    document.getElementById('hudO').textContent = c.open.toFixed(2);
    document.getElementById('hudH').textContent = c.high.toFixed(2);
    document.getElementById('hudL').textContent = c.low.toFixed(2);
    document.getElementById('hudC').textContent = c.close.toFixed(2);
    const isUp = c.close >= c.open;
    document.getElementById('hudC').style.color = isUp ? '#089981' : '#f23645';
  }}
}});

/* --- 实时行情推送 --- */
async function fetchLive() {{
  try {{
    if (IS_BTC) {{
      const r = await fetch('https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT');
      const j = await r.json();
      const p = parseFloat(j.data[0].last), o = parseFloat(j.data[0].open24h);
      if (!isNaN(p) && data.candles.length > 0) {{
        const lb = data.candles[data.candles.length - 1];
        candleSeries.update({{ ...lb, close: p, high: Math.max(lb.high, p), low: Math.min(lb.low, p) }});
        updatePriceBox(p, o);
      }}
    }} else {{
      const r = await fetch('https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=1m&range=1d');
      const j = await r.json();
      const p = j.chart.result[0].meta.regularMarketPrice;
      const o = j.chart.result[0].meta.chartPreviousClose;
      if (p && !isNaN(p) && data.candles.length > 0) {{
        const lb = data.candles[data.candles.length - 1];
        candleSeries.update({{ ...lb, close: p, high: Math.max(lb.high, p), low: Math.min(lb.low, p) }});
        updatePriceBox(p, o || lb.open);
      }}
    }}
  }} catch (e) {{}}
}}
fetchLive();
setInterval(fetchLive, 4000);

/* --- 双图 Crosshair & 视口同步 --- */
const pairs = [[chart1, candleSeries], [chart2, histSeries]];
let syncing = false;
pairs.forEach(([sc]) => {{
  sc.subscribeCrosshairMove(p => {{
    if (syncing) return;
    syncing = true;
    pairs.forEach(([tc, ts]) => {{
      if (tc === sc) return;
      if (p.time) {{
        tc.setCrosshairPosition(ts.coordinateToPrice(p.point ? p.point.y : 0) ?? 0, p.time, ts);
      }} else {{
        tc.clearCrosshairPosition();
      }}
    }});
    syncing = false;
  }});
  sc.timeScale().subscribeVisibleLogicalRangeChange(r => {{
    if (syncing || !r) return;
    syncing = true;
    pairs.forEach(([tc]) => {{
      if (tc !== sc) tc.timeScale().setVisibleLogicalRange(r);
    }});
    syncing = false;
  }});
}});

window.addEventListener('resize', () => {{
  const nw = window.innerWidth;
  pairs.forEach(([c]) => c.applyOptions({{ width: nw }}));
}});
</script>
</body>
</html>
"""

st.components.v1.html(html_content, height=720, scrolling=False)