import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import warnings
import pytz
import requests
import random
from scipy.signal import argrelextrema

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m']

st.set_page_config(page_title="Master Trade v172", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE (ƯU TIÊN BINANCE TUYỆT ĐỐI)
# ==========================================
def get_live_price_v172(symbol):
    if "BTC" in symbol:
        try:
            # Gọi trực tiếp Binance API - Bypass hoàn toàn Yahoo
            url = f"https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT&nocache={random.random()}"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                return float(res.json()['price']), "Binance API"
        except: pass
    
    try:
        # Với Vàng và Index, dùng Yahoo nhưng ép tải mới
        ticker = yf.Ticker(symbol)
        df = ticker.history(period='1d', interval='1m')
        if not df.empty:
            return float(df['Close'].iloc[-1]), "Yahoo Live"
        return ticker.fast_info['last_price'], "Yahoo FastInfo"
    except:
        return None, "Error"

# ==========================================
# 3. THUẬT TOÁN RSI & PHÂN KỲ
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 40: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
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
        
        # Detect Divergence
        high, low, rsi = df['High'].values, df['Low'].values, df['rsi_val'].values
        li = argrelextrema(low, np.less, order=5)[0]
        hi = argrelextrema(high, np.greater, order=5)[0]
        df['div'] = "-"
        if len(li) >= 2 and low[li[-1]] < low[li[-2]] and rsi[li[-1]] > rsi[li[-2]]:
            if (len(df)-1-li[-1]) < 10: df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
        if len(hi) >= 2 and high[hi[-1]] > high[hi[-2]] and rsi[hi[-1]] < rsi[hi[-2]]:
            if (len(df)-1-hi[-1]) < 10: df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
        return df
    except: return None

def fetch_history_v172(symbol, tf):
    try:
        ticker = yf.Ticker(symbol)
        p = '5d' if 'm' in tf else ('730d' if 'h' in tf else 'max')
        f_tf = '1h' if ('h' in tf and tf != '1h') else ('1d' if tf == '3d' else tf)
        df = ticker.history(period=p, interval=f_tf)
        if df.empty: return None
        rule = {'2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME'}
        if tf in rule:
            df = df.resample(rule[tf]).agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "CHỈNH (-)", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v172</h2>", unsafe_allow_html=True)
    
    if st.sidebar.button("♻️ RESET APP & CACHE"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph = st.empty()
            table_ph = st.empty()
            
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                # Lấy giá Live trước
                live_p, source = get_live_price_v172(asset['symbol'])
                
                rows = []
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                    
                    df = fetch_history_v172(asset['symbol'], tf)
                    p_val = live_p if live_p else (df['Close'].iloc[-1] if df is not None else 0)
                    
                    if df is not None:
                        last = df.iloc[-1]
                        r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                        if r > r9 and r > r45: rs = "TĂNG"
                        elif r < r9 and r < r45: rs = "GIẢM"
                        elif r9 > r > r45: rs = "CHỈNH (-)"
                        else: rs = "HỒI (+)"
                        
                        rows.append({
                            "Khung": tf.upper(), 
                            "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": rs, "Phân kỳ RSI": last['div'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), "Giá": f"{p_val:,.1f}"
                        })
                    else:
                        rows.append({
                            "Khung": tf.upper(), "Xu hướng": "Yahoo Blocked", "RSI 9/45": "Lỗi 404",
                            "Phân kỳ RSI": "-", "Giá/MA50": "-", "MA 10/20": "-",
                            "RSI": 0, "Giá": f"{p_val:,.1f}"
                        })

                if rows:
                    status_ph.success(f"💠 {asset['name']} | Nguồn: {source} | Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
