import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import warnings
import pytz
import requests
from scipy.signal import argrelextrema

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "binance": "BTCUSDT"},
    {"name": "VÀNG", "symbol": "GC=F", "binance": None}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "binance": None}
]
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '1w', '1m']

st.set_page_config(page_title="Master Trade v176", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ & DỮ LIỆU CRYPTO (BINANCE DỰ PHÒNG)
# ==========================================
def get_binance_data_v176(symbol, interval):
    """Sử dụng nhiều endpoint Binance để tránh bị chặn IP"""
    endpoints = [
        f"https://api1.binance.com/api/v3/klines",
        f"https://api2.binance.com/api/v3/klines",
        f"https://api3.binance.com/api/v3/klines"
    ]
    mapping = {'15m':'15m', '30m':'30m', '1h':'1h', '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '1d':'1d', '1w':'1w', '1m':'1M'}
    bin_int = mapping.get(interval, '1h')
    
    for url in endpoints:
        try:
            params = {'symbol': symbol, 'interval': bin_int, 'limit': 200}
            res = requests.get(url, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                df = pd.DataFrame(data, columns=['ts', 'Open', 'High', 'Low', 'Close', 'Vol', 'Close_ts', 'Quote_vol', 'Trades', 'Taker_buy_base', 'Taker_buy_quote', 'Ignore'])
                df[['Open', 'High', 'Low', 'Close']] = df[['Open', 'High', 'Low', 'Close']].astype(float)
                return df
        except:
            continue
    return None

def get_crypto_live_v176(symbol):
    """Lấy giá live Bitcoin từ Binance hoặc CoinGecko dự phòng"""
    try:
        res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=3)
        return float(res.json()['price'])
    except:
        try:
            res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd", timeout=3)
            return float(res.json()['bitcoin']['usd'])
        except: return None

# ==========================================
# 3. HÀM LẤY DỮ LIỆU YAHOO (GIẢ LẬP TRÌNH DUYỆT)
# ==========================================
def fetch_yahoo_v176(symbol, tf):
    try:
        # Cấu hình headers để tránh Yahoo block IP Cloud
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        p = '5d' if 'm' in tf else ('730d' if 'h' in tf else 'max')
        f_tf = '1h' if ('h' in tf and tf != '1h') else ('1d' if tf == '3d' else tf)
        
        # Dùng yfinance với session để ổn định hơn
        df = yf.download(symbol, period=p, interval=f_tf, progress=False, timeout=10)
        
        if df.empty or len(df) < 2: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        rule = {'2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME'}
        if tf in rule:
            df = df.resample(rule[tf]).agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
        return df
    except: return None

# ==========================================
# 4. CHỈ BÁO & LOGIC (GIỮ NGUYÊN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 40: return None
    try:
        df = df.copy()
        c = 'Close'
        df['ma10'] = df[c].rolling(10).mean()
        df['ma20'] = df[c].rolling(20).mean()
        df['ma50'] = df[c].rolling(50).mean()
        delta = df[c].diff()
        gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
        ag = gain.ewm(alpha=1/14, adjust=False).mean()
        al = loss.ewm(alpha=1/14, adjust=False).mean()
        df['rsi_val'] = 100 - (100 / (1 + ag / al))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        
        hi = argrelextrema(df['High'].values, np.greater, order=5)[0]
        li = argrelextrema(df['Low'].values, np.less, order=5)[0]
        df['div'] = "-"
        if len(li) >= 2 and df['Low'].iloc[li[-1]] < df['Low'].iloc[li[-2]] and df['rsi_val'].iloc[li[-1]] > df['rsi_val'].iloc[li[-2]]:
            if (len(df)-1-li[-1]) < 10: df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
        if len(hi) >= 2 and df['High'].iloc[hi[-1]] > df['High'].iloc[hi[-2]] and df['rsi_val'].iloc[hi[-1]] < df['rsi_val'].iloc[hi[-2]]:
            if (len(df)-1-hi[-1]) < 10: df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
        return df
    except: return None

def style_text(val):
    if val in ["TĂNG", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

# ==========================================
# 5. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v176</h2>", unsafe_allow_html=True)
    
    if st.sidebar.button("♻️ RESET DỮ LIỆU"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph, table_ph = st.empty(), st.empty()
            rows = []
            
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                # --- LẤY GIÁ LIVE ---
                if asset['binance']:
                    live_p = get_crypto_live_v176(asset['binance'])
                else:
                    try:
                        t_live = yf.Ticker(asset['symbol']).history(period='1d')
                        live_p = t_live['Close'].iloc[-1] if not t_live.empty else None
                    except: live_p = None

                # --- LẤY DỮ LIỆU CÁC KHUNG ---
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                    
                    # Tải df tương ứng nguồn
                    if asset['binance']:
                        df_raw = get_binance_data_v176(asset['binance'], tf)
                    else:
                        df_raw = fetch_yahoo_v176(asset['symbol'], tf)
                    
                    df_ind = calculate_indicators(df_raw)
                    
                    if df_ind is not None:
                        last = df_ind.iloc[-1]
                        p_val = live_p if live_p else last['Close']
                        r = last['rsi_val']
                        rs = "TĂNG" if (r > last['rsi9'] and r > last['rsi45']) else "GIẢM"
                        rows.append({
                            "Khung": tf.upper(), "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": rs, "Phân kỳ RSI": last['div'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), "Giá": f"{p_val:,.1f}"
                        })
                
                if rows:
                    status_ph.success(f"💠 {asset['name']} | Live: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))
                else:
                    status_ph.error(f"⚠️ Yahoo & Binance đang chặn kết nối cho {asset['name']}. Đang thử lại...")
                    time.sleep(2)
                    st.rerun()

    time.sleep(120)
    st.rerun()

if __name__ == "__main__":
    main()
