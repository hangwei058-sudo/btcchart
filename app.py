import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import json
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError

# 页面基础配置
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# 自定义深色主题与紧凑样式
st.markdown("""
<style>
  html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"],.block-container{
    background:#000!important;
  }
  .block-container{padding:0.1rem 0.3rem 0!important;}
  [data-testid="stVerticalBlock"]{gap:0.04rem!important;}
  header,footer{display:none!important;}
  .stButton button{
    background:#111!important;color:#bbb!important;
    border:1px solid #2a2a2a!important;
    font-size:12px!important;height:28px!important;
    min-height:28px!important;padding:0 4px!important;
    border-radius:4px!important;transition:all .08s!important;
  }
  .stButton button:active{
    background:#1a6aff!important;color:#fff!important;
    transform:scale(.88)!important;
  }
  [data-testid="stSelectbox"] > div > div {
    background:#111!important;color:#fff!important;
    border:1px solid #2a2a2a!important;
    min-height:28px!important;
  }
  [data-testid="stSelectbox"] > div > div > div {
    color:#fff!important;
    font-weight:600!important;
    font-size:14px!important;
  }
  [data-testid="stSelectbox"] svg {
    fill:#fff!important;
  }
  div[data-baseweb="popover"] li {
    background:#111!important;
    color:#fff!important;
  }
  div[data-baseweb="popover"] li:hover {
    background:#1a6aff!important;
    color:#fff!important;
  }
</style>
""", unsafe_allow_html=True)

# 品种与时间周期配置
SYMBOL_CONFIG = {"黄金 GOLD": "GC=F", "BTC/USDT": "BTC/USDT"}
TIME_CONFIG = {
    "7m":"7T","10m":"10T","15m":"15T","20m":"20T",
    "23m":"23T","30m":"30T","45m":"45T","90m":"90T",
    "1h":"1H","2h":"2H","3h":"3H","4h":"4H","6h":"6H",
    "8h":"8H","10h":"10H","12h":"12H","16h":"16H",
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

# 初始化 Session State
if "selected_label" not in st.session_state:
    st.session_state.selected_label = "1h"
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "黄金 GOLD"

# --- UI 控件 ---
# 第一行：品种切换按钮
r1c1, r1c2 = st.columns(2)
with r1c1:
    lbl = "● 黄金 GOLD" if st.session_state.selected_symbol=="黄金 GOLD" else "黄金 GOLD"
    if st.button(lbl, key="g", use_container_width=True):
        st.session_state.selected_symbol = "黄金 GOLD"
with r1c2:
    lbl = "● BTC/USDT" if st.session_state.selected_symbol=="BTC/USDT" else "BTC/USDT"
    if st.button(lbl, key="b", use_container_width=True):
        st.session_state.selected_symbol = "BTC/USDT"

# 第二行：◀ [周期下拉] ▶
r2c1, r2c2, r2c3 = st.columns([0.15, 0.70, 0.15])
with r2c1:
    if st.button("◀", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx-1)%len(period_keys)]
with r2c2:
    new_label = st.selectbox(
        "周期", period_keys,
        index=period_keys.index(st.session_state.selected_label),
        label_visibility="collapsed"
    )
    st.session_state.selected_label = new_label
with r2c3:
    if st.button("▶", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx+1)%len(period_keys)]

# --- 数据获取与处理 ---
selected_label = st.session_state.selected_label
selected_symbol_label = st.session_state.selected_symbol
symbol = SYMBOL_CONFIG[selected_symbol_label]
rule = TIME_CONFIG[selected_label]
bar_seconds = BAR_SECONDS.get(selected_label, 3600)
is_btc = (symbol == "BTC/USDT")

def get_base_interval(rule_str):
    r = rule_str.lower()
    if 'd' in r: return 'day'
    if 'h' in r: return 'hour'
    return 'minute'

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_with_retry(exchange, symbol, timeframe, since, limit):
    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)

@st.cache_data(ttl=120)
def get_btc_base_df(base_type):
    exchange = ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
    tf_map = {'minute': '1m', 'hour': '1h', 'day': '1D'}
    timeframe = tf_map.get(base_type, '1m')
    limit = 300
    total_bars_to_fetch = 2000 
    all_bars = []
    
    try:
        # 尝试一次性获取大部分数据
        all_bars = exchange.fetch_ohlcv(symbol='BTC/USDT', timeframe=timeframe, limit=total_bars_to_fetch)
    except Exception as e:
        print(f"Initial fetch failed: {e}. Falling back to iterative fetching.")
        # 如果交易所不支持一次性获取大量数据，则回退到循环获取
        now = exchange.milliseconds()
        msec_per_bar = {'1m': 60000, '1h': 3600000, '1D': 86400000}[timeframe]
        since = now - total_bars_to_fetch * msec_per_bar

        while len(all_bars) < total_bars_to_fetch:
            try:
                bars = fetch_with_retry(exchange, 'BTC/USDT', timeframe, since, limit)
                if not bars: break
                all_bars.extend(bars)
                since = bars[-1][0] + 1
                if len(bars) < limit: break
            except RetryError as re:
                print(f"Fetching BTC data failed after retries: {re}")
                break

    if not all_bars: return pd.DataFrame()

    df = pd.DataFrame(all_bars, columns=['time','open','high','low','close','volume'])
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
            df = ticker.history(period="max", interval="1d")
        
        if df.empty: return pd.DataFrame()
            
        df = df[['Open','High','Low','Close','Volume']]
        df.columns = ['open','high','low','close','volume']
        df.index = pd.to_datetime(df.index, utc=True).tz_convert('Asia/Shanghai').tz_localize(None)
        return df[~df.index.duplicated(keep='last')].sort_index()
    except Exception as e:
        print(f"Error fetching gold data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=120)
def process_market_data(sym, resample_rule):
    base_type = get_base_interval(resample_rule)
    df_base = get_gold_df(base_type) if sym == "GC=F" else get_btc_base_df(base_type)
    
    if df_base.empty: return pd.DataFrame()

    # 核心修复：确保对基础数据进行重采样
    df = df_base.resample(resample_rule).agg(
        {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
    ).dropna(subset=['open'])
    
    if df.empty: return pd.DataFrame()

    # 计算技术指标
    for span in [12, 26, 24, 52, 104]:
        df[f'ema{span}'] = df['close'].ewm(span=span, adjust=False).mean()
    df['macd']   = df['ema12'] - df['ema26']
    df['macd_s'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_h'] = df['macd'] - df['macd_s']
    
    return df.tail(2000)

df = process_market_data(symbol, rule)

# --- 数据序列化 ---
candles, ema24_data, ema52_data, ema104_data = [], [], [], []
macd_data, signal_data, hist_data = [], [], []

if not df.empty:
    df_rounded = df.round({'open': 2, 'high': 2, 'low': 2, 'close': 2, 'ema24': 2, 'ema52': 2, 'ema104': 2, 'macd': 4, 'macd_s': 4, 'macd_h': 4})
    
    timestamps = (df_rounded.index.astype('int64') // 10**9).tolist()

    # K线
    candles = [
        {"time": t, "open": o, "high": h, "low": l, "close": c}
        for t, o, h, l, c in zip(
            timestamps, 
            df_rounded['open'], 
            df_rounded['high'], 
            df_rounded['low'], 
            df_rounded['close']
        )
    ]

    # 指标线
    def extract_line_series(col_name):
        valid = df_rounded[col_name].dropna()
        if valid.empty: return []
        ts = (valid.index.astype('int64') // 10**9)
        return [{"time": t, "value": v} for t, v in zip(ts, valid)]

    ema24_data = extract_line_series('ema24')
    ema52_data = extract_line_series('ema52')
    ema104_data = extract_line_series('ema104')
    macd_data = extract_line_series('macd')
    signal_data = extract_line_series('macd_s')

    # MACD柱状图颜色
    hist_valid = df_rounded['macd_h'].dropna()
    if not hist_valid.empty:
        hist_ts = (hist_valid.index.astype('int64') // 10**9)
        prev_h = None
        for t, v in zip(hist_ts, hist_valid):
            color = ("#26A69A" if v >= (prev_h or v) else "#B2DFDB") if v >= 0 else ("#FF5252" if v <= (prev_h or v) else "#FFCDD2")
            hist_data.append({"time": t, "value": v, "color": color})
            prev_h = v

last_price = candles[-1]['close'] if candles else 0
last_open  = candles[-1]['open']  if candles else 0
last_candle_time = candles[-1]['time'] if candles else 0

data_json = json.dumps({
    "candles": candles, "ema24": ema24_data, "ema52": ema52_data,
    "ema104": ema104_data, "macd": macd_data, "signal": signal_data, "hist": hist_data,
})

# --- HTML & JavaScript ---
current_label_text = f"{selected_symbol_label} · {selected_label}"

html = f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  html,body{{margin:0;padding:0;background:#000;overflow:hidden;}}
  #chart1,#chart2{{width:100%;}}
  #wrap1{{position:relative;}}
  #floatBox{{
    position:absolute;top:8px;right:6px;
    background:rgba(10,10,10,0.88);
    border:1px solid #333;border-radius:6px;
    padding:5px 10px;z-index:999;
    font-family:monospace;text-align:right;
    cursor:move;user-select:none;min-width:110px;
  }}
  #priceVal{{font-size:17px;font-weight:bold;color:#26A69A;}}
  #priceDiff{{font-size:10px;color:#888;margin-top:1px;}}
  #timerRow{{font-size:11px;color:#FFD700;margin-top:3px;
    border-top:1px solid #222;padding-top:3px;}}
  #timerLabel{{font-size:9px;color:#555;}}
  #periodBadge{{
    position:absolute;top:8px;left:6px;
    background:rgba(10,10,10,0.88);
    border:1px solid #333;border-radius:6px;
    padding:4px 9px;z-index:999;
    font-family:monospace;font-size:13px;font-weight:bold;
    color:#1a9dff;user-select:none;
  }}
</style>
</head>
<body>
<div id="wrap1">
  <div id="chart1"></div>
  <div id="periodBadge">{current_label_text}</div>
  <div id="floatBox">
    <div id="priceVal">{last_price:.2f}</div>
    <div id="priceDiff">-- (--.--%)</div>
    <div id="timerRow">
      <div id="timerLabel">下根K线收盘</div>
      <div id="timerVal">--:--</div>
    </div>
  </div>
</div>
<div id="chart2"></div>

<script>
const data={data_json};
const BAR_SEC={bar_seconds};
const LAST_TS={last_candle_time};
const IS_BTC={'true' if is_btc else 'false'};
const INIT_PRICE={last_price};
const INIT_OPEN={last_open};

// --- Draggable FloatBox ---
(function(){{
  const el=document.getElementById('floatBox');
  let ox,oy,sx,sy,drag=false;
  const startDrag=e=>{
    const r=el.getBoundingClientRect();
    ox=r.left;oy=r.top;
    sx=e.clientX||e.touches[0].clientX;
    sy=e.clientY||e.touches[0].clientY;
    drag=true;
    el.style.right='auto';
    el.style.left=ox+'px';
    el.style.top=oy+'px';
    if(e.touches) e.preventDefault();
  };
  const doDrag=e=>{
    if(!drag)return;
    const cx=e.clientX||e.touches[0].clientX;
    const cy=e.clientY||e.touches[0].clientY;
    el.style.left=(ox+cx-sx)+'px';
    el.style.top=(oy+cy-sy)+'px';
    if(e.touches) e.preventDefault();
  };
  const stopDrag=()=>drag=false;
  el.addEventListener('mousedown',startDrag);
  document.addEventListener('mousemove',doDrag);
  document.addEventListener('mouseup',stopDrag);
  el.addEventListener('touchstart',startDrag,{{passive:false}});
  document.addEventListener('touchmove',doDrag,{{passive:false}});
  document.addEventListener('touchend',stopDrag);
}})();

const BG='#000';
const CL={{background:{{color:BG}},textColor:'#ccc'}};
const CG={{vertLines:{{color:'#1a1a1a'}},horzLines:{{color:'#1a1a1a'}}}};
const CT={{timeVisible:true,secondsVisible:false,borderColor:'#2a2a2a'}};
const CLoc={{timeFormatter:ts=>{{
  const d=new Date((ts)*1000); // lightweight-charts provides UTC timestamp
  const year=d.getFullYear(),mon=String(d.getMonth()+1).padStart(2,'0'),day=String(d.getDate()).padStart(2,'0');
  const h=String(d.getHours()).padStart(2,'0'),m=String(d.getMinutes()).padStart(2,'0');
  return `${year}-${mon}-${day} ${h}:${m}`;
}}}};

const W=window.innerWidth,H=window.innerHeight;
const CTRL=62,avail=H-CTRL;
const H1=Math.floor(avail*0.64),H2=Math.floor(avail*0.36);

// --- Chart 1 (Main) ---
const chart1=LightweightCharts.createChart(document.getElementById('chart1'),{{
  width:W,height:H1,layout:CL,grid:CG,timeScale:{{...CT, rightOffset: 5}},localization:CLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#2a2a2a'}},
}});
const candle=chart1.addCandlestickSeries({{
  upColor:'#26A69A',downColor:'#FF5252',borderVisible:false,
  wickUpColor:'#26A69A',wickDownColor:'#FF5252'
}});
if(data.candles && data.candles.length > 0) candle.setData(data.candles);

[['#FF6D00',data.ema24],['#AA00FF',data.ema52],['#FFFFFF',data.ema104]].forEach(([c,d])=>{{
  if(!d || d.length === 0) return;
  const s=chart1.addLineSeries({{color:c,lineWidth:1,
    lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false, priceFormat: {{ type: 'price', precision: 2, minMove: 0.01 }}});
  s.setData(d);
}});

// --- Chart 2 (MACD) ---
const chart2=LightweightCharts.createChart(document.getElementById('chart2'),{{
  width:W,height:H2,layout:CL,grid:CG,timeScale:{{...CT, rightOffset: 5}},localization:CLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#2a2a2a'}},
}});
if(data.hist && data.hist.length > 0){{
    const hist=chart2.addHistogramSeries({{priceFormat: {{ type: 'price', precision: 4, minMove: 0.0001 }}});
    hist.setData(data.hist);
}}
if(data.macd && data.macd.length > 0){{
    const macdS=chart2.addLineSeries({{color:'#2962FF',lineWidth:1,priceFormat: {{ type: 'price', precision: 4, minMove: 0.0001 }}});
    macdS.setData(data.macd);
}}
if(data.signal && data.signal.length > 0){{
    const sigS=chart2.addLineSeries({{color:'#FF6D00',lineWidth:1,priceFormat: {{ type: 'price', precision: 4, minMove: 0.0001 }}});
    sigS.setData(data.signal);
}}

// --- UI Updates & Syncing ---
function updatePriceBox(p,o){{
  const el=document.getElementById('priceVal');
  const diff=p-o,pct=o>0?diff/o*100:0,s=diff>=0?'+':'';
  el.textContent=p.toFixed(IS_BTC ? 2 : 2);
  el.style.color=p>=o?'#26A69A':'#FF5252';
  document.getElementById('priceDiff').textContent=s+diff.toFixed(2)+' ('+s+pct.toFixed(2)+'%)';
}}
updatePriceBox(INIT_PRICE,INIT_OPEN);

function updateTimer(){{
  if(!LAST_TS) return;
  let rem=LAST_TS+BAR_SEC-Math.floor(Date.now()/1000);
  let str;
  if(rem<=0)str='⏰ 收盘';
  else if(rem>=3600){{const h=Math.floor(rem/3600),m=Math.floor((rem%3600)/60);str=h+'h '+String(m).padStart(2,'0')+'m';}}
  else if(rem>=60){{const m=Math.floor(rem/60),s=rem%60;str=m+'m '+String(s).padStart(2,'0')+'s';}}
  else str=rem+'s';
  document.getElementById('timerVal').textContent='⏱ '+str;
}}
updateTimer();setInterval(updateTimer,1000);

async function fetchLive(){{
  try{{
    let url, parseFn;
    if(IS_BTC){{
      url = 'https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP';
      parseFn = j => {{
        if(!j || !j.data || j.data.length==0) return null;
        return {{ p:parseFloat(j.data[0].last), o:parseFloat(j.data[0].open24h) }};
      }};
    }} else {{
      url = `https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range=1d&interval=1m&_=${Date.now()}`;
      parseFn = j => {{
        if(!j || !j.chart || !j.chart.result || j.chart.result.length==0) return null;
        const meta = j.chart.result[0].meta;
        return {{ p:meta.regularMarketPrice, o:meta.chartPreviousClose }};
      }};
    }}
    const r=await fetch(url);
    const j=await r.json();
    const market = parseFn(j);
    if(market && !isNaN(market.p) && data.candles.length>0){{
        const lb=data.candles[data.candles.length-1];
        candle.update({{...lb,close:market.p,high:Math.max(lb.high,market.p),low:Math.min(lb.low,market.p)}});
        updatePriceBox(market.p,market.o||lb.open);
    }}
  }}catch(e){{ console.error("FetchLive Error:", e) }}
}}
fetchLive();setInterval(fetchLive,5000);

// Sync charts
const charts = [chart1, chart2];
charts.forEach(chart => {{
    chart.timeScale().subscribeVisibleLogicalRangeChange(timeRange => {{
        charts.forEach(otherChart => {{
            if (chart !== otherChart) {{
                otherChart.timeScale().setVisibleLogicalRange(timeRange);
            }}
        }});
    }});
    chart.subscribeCrosshairMove(param => {{
        charts.forEach(otherChart => {{
            if (chart !== otherChart) {{
                otherChart.moveCrosshair(param);
            }}
        }});
    }});
}});

window.addEventListener('resize',()=>{{
  const nw=window.innerWidth;
  charts.forEach(c=>c.applyOptions({{width:nw}}));
}});
</script>
</body>
</html>
"""

st.components.v1.html(html, height=H_calc, scrolling=False)

