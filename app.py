import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import json
import sqlite3
import os
import time

# 页面基础配置
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# -------------------------------------------------------------
# 1. 样式定制：深色极简风格 + 强制移动端控件不折行
# -------------------------------------------------------------
st.markdown("""
<style>
  html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], .block-container {
    background: #000 !important;
  }
  .block-container { padding: 0.1rem 0.3rem 0 !important; }
  [data-testid="stVerticalBlock"] { gap: 0.04rem !important; }
  header, footer { display: none !important; }

  /* 核心修复：强制移动端水平排布，严禁折行掉下来 */
  [data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    gap: 4px !important;
  }
  [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    min-width: 0 !important;
    flex: 1 1 auto !important;
  }

  .stButton button {
    background: #111 !important;
    color: #bbb !important;
    border: 1px solid #2a2a2a !important;
    font-size: 13px !important;
    font-weight: bold !important;
    height: 32px !important;
    min-height: 32px !important;
    padding: 0 4px !important;
    border-radius: 4px !important;
    transition: all .08s !important;
  }
  .stButton button:active {
    background: #1a6aff !important;
    color: #fff !important;
    transform: scale(.92) !important;
  }

  [data-testid="stSelectbox"] > div > div {
    background: #111 !important;
    color: #fff !important;
    border: 1px solid #2a2a2a !important;
    min-height: 32px !important;
    height: 32px !important;
  }
  [data-testid="stSelectbox"] > div > div > div {
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 13px !important;
  }
  [data-testid="stSelectbox"] svg {
    fill: #fff !important;
  }
  div[data-baseweb="popover"] li {
    background: #111 !important;
    color: #fff !important;
  }
  div[data-baseweb="popover"] li:hover {
    background: #1a6aff !important;
    color: #fff !important;
  }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. SQLite 本地数据持久化引擎
# -------------------------------------------------------------
DB_FILE = "market_data.db"

def init_db():
    """初始化本地 SQLite 数据库表结构"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                symbol TEXT,
                timeframe TEXT,
                time INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (symbol, timeframe, time)
            )
        """)
        conn.commit()

init_db()

def load_klines_from_db(symbol, timeframe):
    """从本地 SQLite 数据库读取历史数据"""
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query(
            "SELECT time, open, high, low, close, volume FROM klines WHERE symbol=? AND timeframe=? ORDER BY time ASC",
            conn, params=(symbol, timeframe)
        )
    if not df.empty:
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df.set_index('time', inplace=True)
    return df

def save_klines_to_db(symbol, timeframe, df_new):
    """将最新 K 线增量写入本地 SQLite 数据库"""
    if df_new.empty:
        return
    records = []
    for idx, row in df_new.iterrows():
        ts_ms = int(idx.timestamp() * 1000)
        records.append((
            symbol, timeframe, ts_ms,
            float(row['open']), float(row['high']), float(row['low']),
            float(row['close']), float(row['volume'])
        ))
    with sqlite3.connect(DB_FILE) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO klines VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            records
        )
        conn.commit()

# -------------------------------------------------------------
# 3. 基础参数与配置
# -------------------------------------------------------------
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

# -------------------------------------------------------------
# 4. 界面控件布局（第一行：品种；第二行：紧凑型左右翻页周期栏）
# -------------------------------------------------------------
r1c1, r1c2 = st.columns(2)
with r1c1:
    lbl = "● 黄金 GOLD" if st.session_state.selected_symbol == "黄金 GOLD" else "黄金 GOLD"
    if st.button(lbl, key="btn_gold", use_container_width=True):
        st.session_state.selected_symbol = "黄金 GOLD"
with r1c2:
    lbl = "● BTC/USDT" if st.session_state.selected_symbol == "BTC/USDT" else "BTC/USDT"
    if st.button(lbl, key="btn_btc", use_container_width=True):
        st.session_state.selected_symbol = "BTC/USDT"

# 紧凑排列：左右按钮宽度固定，中间下拉框填充，确保同排不换行
r2c1, r2c2, r2c3 = st.columns([0.18, 0.64, 0.18])
with r2c1:
    if st.button("◀", key="prev_period", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx - 1) % len(period_keys)]
with r2c2:
    new_label = st.selectbox(
        "周期选择", period_keys,
        index=period_keys.index(st.session_state.selected_label),
        label_visibility="collapsed",
        key="period_select"
    )
    st.session_state.selected_label = new_label
with r2c3:
    if st.button("▶", key="next_period", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx + 1) % len(period_keys)]

selected_label = st.session_state.selected_label
selected_symbol_label = st.session_state.selected_symbol
symbol = SYMBOL_CONFIG[selected_symbol_label]
rule = TIME_CONFIG[selected_label]
bar_seconds = BAR_SECONDS.get(selected_label, 3600)
is_btc = (symbol == "BTC/USDT")

# -------------------------------------------------------------
# 5. 数据抓取与增量同步逻辑（支持 SQLite 缓存）
# -------------------------------------------------------------
def get_base_granularity(rule_str):
    r = rule_str.lower()
    if r.endswith('d'): return 'day'
    elif r.endswith('h'): return 'hour'
    return 'minute'

@st.cache_data(ttl=60)
def sync_btc_data(rule_str):
    """根据周期动态选择底阶粒度，并与本地 SQLite 进行增量同步"""
    r = rule_str.lower()
    if r.endswith('d'):
        tf = '1D'
        default_bars = 1500  # 约 4 年日线，完美合成 8d/15d/45d
        interval_ms = 86400 * 1000
    elif r.endswith('h'):
        tf = '1H'
        default_bars = 2000
        interval_ms = 3600 * 1000
    else:
        tf = '1m'
        default_bars = 4000
        interval_ms = 60 * 1000

    # 先从 SQLite 读取
    df_local = load_klines_from_db('BTC/USDT', tf)
    exchange = ccxt.okx({'enableRateLimit': True})
    now = exchange.milliseconds()

    if df_local.empty:
        since = now - (default_bars * interval_ms)
    else:
        since = int(df_local.index[-1].timestamp() * 1000) + 1

    # 若距离上次更新超过 1 个周期，则执行增量拉取
    if (now - since) > interval_ms:
        try:
            bars = exchange.fetch_ohlcv('BTC/USDT', timeframe=tf, since=since, limit=300)
            if bars:
                df_new = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
                df_new['time'] = pd.to_datetime(df_new['time'], unit='ms')
                df_new.set_index('time', inplace=True)
                save_klines_to_db('BTC/USDT', tf, df_new)
                df_local = load_klines_from_db('BTC/USDT', tf)
        except Exception:
            pass

    return df_local

@st.cache_data(ttl=180)
def sync_gold_data(base_type):
    """黄金数据拉取（支持持久化与异常兜底）"""
    tf = '1D' if base_type == 'day' else ('1H' if base_type == 'hour' else '5m')
    df_local = load_klines_from_db('GC=F', tf)
    
    # 若本地为空或过旧，重新抓取
    if df_local.empty or (time.time() - df_local.index[-1].timestamp() > 3600):
        ticker = yf.Ticker("GC=F")
        try:
            if base_type == 'minute':
                df = ticker.history(period="60d", interval="5m")
            elif base_type == 'hour':
                df = ticker.history(period="730d", interval="1h")
            else:
                df = ticker.history(period="10y", interval="1d")
            
            if not df.empty:
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                df.columns = ['open', 'high', 'low', 'close', 'volume']
                df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
                save_klines_to_db('GC=F', tf, df)
                df_local = df
        except Exception:
            pass
            
    return df_local

@st.cache_data(ttl=60)
def resample_data(symbol, rule):
    base_type = get_base_granularity(rule)
    df = sync_gold_data(base_type) if symbol == "GC=F" else sync_btc_data(rule)

    if df.empty:
        return pd.DataFrame()

    # 关键修复：加入 origin='start' 与去重，确保 8d、15d 等任意多日周期精准切分
    resampled = df.resample(rule, origin='start').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    ).dropna(subset=['open', 'high', 'low', 'close'])

    resampled = resampled[~resampled.index.duplicated(keep='last')].sort_index()

    if resampled.empty:
        return pd.DataFrame()

    # 指标计算
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

# -------------------------------------------------------------
# 6. 数据打包与时间戳单调递增保障
# -------------------------------------------------------------
candles, ema24_data, ema52_data, ema104_data = [], [], [], []
macd_data, signal_data, hist_data = [], [], []
prev_h = None
seen_timestamps = set()

if not df.empty:
    for idx, row in df.iterrows():
        t = int(idx.timestamp())
        # 严防重复时间戳导致 TradingView 图表崩溃黑屏
        if t in seen_timestamps:
            continue
        seen_timestamps.add(t)

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
                color = "#26A69A" if (prev_h is None or pd.isna(prev_h) or v >= prev_h) else "#B2DFDB"
            else:
                color = "#FF5252" if (prev_h is None or pd.isna(prev_h) or v <= prev_h) else "#FFCDD2"
            hist_data.append({"time": t, "value": v, "color": color})
            prev_h = v

last_price = candles[-1]['close'] if candles else 0.0
last_open  = candles[-1]['open']  if candles else 0.0
last_candle_time = candles[-1]['time'] if candles else 0

data_json = json.dumps({
    "candles": candles, "ema24": ema24_data, "ema52": ema52_data,
    "ema104": ema104_data, "macd": macd_data, "signal": signal_data, "hist": hist_data,
})

current_label_text = f"{selected_symbol_label} · {selected_label}"

# -------------------------------------------------------------
# 7. 前端 HTML + TradingView Lightweight Charts 图表渲染
# -------------------------------------------------------------
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

(function(){{
  const el=document.getElementById('floatBox');
  let ox,oy,sx,sy,drag=false;
  el.addEventListener('touchstart',e=>{{
    const t=e.touches[0];const r=el.getBoundingClientRect();
    ox=r.left;oy=r.top;sx=t.clientX;sy=t.clientY;drag=true;
    el.style.right='auto';el.style.left=ox+'px';el.style.top=oy+'px';
    e.preventDefault();
  }},{{passive:false}});
  document.addEventListener('touchmove',e=>{{
    if(!drag)return;const t=e.touches[0];
    el.style.left=(ox+t.clientX-sx)+'px';
    el.style.top=(oy+t.clientY-sy)+'px';
    e.preventDefault();
  }},{{passive:false}});
  document.addEventListener('touchend',()=>drag=false);
  el.addEventListener('mousedown',e=>{{
    const r=el.getBoundingClientRect();
    ox=r.left;oy=r.top;sx=e.clientX;sy=e.clientY;drag=true;
    el.style.right='auto';el.style.left=ox+'px';el.style.top=oy+'px';
  }});
  document.addEventListener('mousemove',e=>{{
    if(!drag)return;
    el.style.left=(ox+e.clientX-sx)+'px';
    el.style.top=(oy+e.clientY-sy)+'px';
  }});
  document.addEventListener('mouseup',()=>drag=false);
}})();

const BG='#000';
const CL={{background:{{color:BG}},textColor:'#ccc'}};
const CG={{vertLines:{{color:'#1a1a1a'}},horzLines:{{color:'#1a1a1a'}}}};
const CT={{timeVisible:true,secondsVisible:false,borderColor:'#2a2a2a'}};
const CLoc={{timeFormatter:ts=>{{
  const d=new Date((ts+8*3600)*1000);
  return String(d.getUTCMonth()+1).padStart(2,'0')+'/'+
         String(d.getUTCDate()).padStart(2,'0')+' '+
         String(d.getUTCHours()).padStart(2,'0')+':'+
         String(d.getUTCMinutes()).padStart(2,'0');
}}}};

const W=window.innerWidth,H=window.innerHeight;
const CTRL=62,avail=H-CTRL;
const H1=Math.floor(avail*0.63),H2=Math.floor(avail*0.35);

const chart1=LightweightCharts.createChart(document.getElementById('chart1'),{{
  width:W,height:H1,layout:CL,grid:CG,timeScale:CT,localization:CLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#2a2a2a'}},
}});

const candle=chart1.addCandlestickSeries({{
  upColor:'#26A69A',downColor:'#FF5252',borderVisible:false,
  wickUpColor:'#26A69A',wickDownColor:'#FF5252',
  lastValueVisible:true,priceLineVisible:true,
}});
if(data.candles && data.candles.length > 0){{
  candle.setData(data.candles);
}}

[['#FF6D00',data.ema24],['#AA00FF',data.ema52],['#FFFFFF',data.ema104]].forEach(([c,d])=>{{
  if(d && d.length > 0){{
    const s=chart1.addLineSeries({{color:c,lineWidth:1,
      lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
    s.setData(d);
  }}
}});

const chart2=LightweightCharts.createChart(document.getElementById('chart2'),{{
  width:W,height:H2,layout:CL,grid:CG,timeScale:CT,localization:CLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#2a2a2a'}},
}});

const hist=chart2.addHistogramSeries({{lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
if(data.hist && data.hist.length > 0){{ hist.setData(data.hist); }}

const macdS=chart2.addLineSeries({{color:'#2962FF',lineWidth:1,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
if(data.macd && data.macd.length > 0){{ macdS.setData(data.macd); }}

const sigS=chart2.addLineSeries({{color:'#FF6D00',lineWidth:1,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
if(data.signal && data.signal.length > 0){{ sigS.setData(data.signal); }}

function updatePriceBox(p,o){{
  const el=document.getElementById('priceVal');
  const diff=p-o,pct=o>0?diff/o*100:0,s=diff>=0?'+':'';
  el.textContent=p.toFixed(2);
  el.style.color=p>=o?'#26A69A':'#FF5252';
  document.getElementById('priceDiff').textContent=s+diff.toFixed(2)+' ('+s+pct.toFixed(2)+'%)';
}}
updatePriceBox(INIT_PRICE,INIT_OPEN);

function updateTimer(){{
  let rem=LAST_TS+BAR_SEC-Math.floor(Date.now()/1000);
  let str;
  if(rem<=0)str='⏰ 收盘';
  else if(rem>=3600){{const h=Math.floor(rem/3600),m=Math.floor((rem%3600)/60),s=rem%60;
    str=h+'h '+String(m).padStart(2,'0')+'m '+String(s).padStart(2,'0')+'s';}}
  else if(rem>=60){{const m=Math.floor(rem/60),s=rem%60;
    str=m+'m '+String(s).padStart(2,'0')+'s';}}
  else str=rem+'s';
  document.getElementById('timerVal').textContent='⏱ '+str;
}}
updateTimer();setInterval(updateTimer,1000);

async function fetchLive(){{
  try{{
    if(IS_BTC){{
      const r=await fetch('https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT');
      const j=await r.json();
      const p=parseFloat(j.data[0].last),o=parseFloat(j.data[0].open24h);
      if(!isNaN(p)&&data.candles.length>0){{
        const lb=data.candles[data.candles.length-1];
        candle.update({{...lb,close:p,high:Math.max(lb.high,p),low:Math.min(lb.low,p)}});
        updatePriceBox(p,o);
      }}
    }}else{{
      const r=await fetch('https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=1m&range=1d');
      const j=await r.json();
      const p=j.chart.result[0].meta.regularMarketPrice;
      const o=j.chart.result[0].meta.chartPreviousClose;
      if(p&&!isNaN(p)&&data.candles.length>0){{
        const lb=data.candles[data.candles.length-1];
        candle.update({{...lb,close:p,high:Math.max(lb.high,p),low:Math.min(lb.low,p)}});
        updatePriceBox(p,o||lb.open);
      }}
    }}
  }}catch(e){{}}
}}
fetchLive();setInterval(fetchLive,5000);

const pairs=[[chart1,candle],[chart2,hist]];
let syncing=false;
pairs.forEach(([sc])=>{{
  sc.subscribeCrosshairMove(p=>{{
    if(syncing)return;syncing=true;
    pairs.forEach(([tc,ts])=>{{if(tc===sc)return;
      if(p.time){{tc.setCrosshairPosition(ts.coordinateToPrice(p.point?p.point.y:0)??0,p.time,ts);}}
      else tc.clearCrosshairPosition();
    }});syncing=false;
  }});
  sc.timeScale().subscribeVisibleLogicalRangeChange(r=>{{
    if(syncing||!r)return;syncing=true;
    pairs.forEach(([tc])=>{{if(tc!==sc)tc.timeScale().setVisibleLogicalRange(r);}});
    syncing=false;
  }});
}});

window.addEventListener('resize',()=>{{
  const nw=window.innerWidth;
  pairs.forEach(([c])=>c.applyOptions({{width:nw}}));
}});
</script>
</body>
</html>
"""

st.components.v1.html(html, height=700, scrolling=False)