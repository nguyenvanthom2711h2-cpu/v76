import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
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
    {"name": "BITCOIN", "symbol": "BTC-USD", "binance": "BTCUSDT"},
    {"name": "VÀNG", "symbol": "GC=F", "binance": None}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "binance": None}
]
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '1w']

st.set_page_config(page_title="Master Trade v179", layout="wide")

# ==========================================
# 2. LẤY DỮ LIỆU TỪ BINANCE (CHO BITCOIN)
# ==========================================
def fetch_binance_v179(symbol, interval):
    """Lấy nến từ Binance - Tuyệt đối không dùng Yahoo"""
    try:
        mapping = {'15m':'15m', '30m':'30m', '1h':'1h', '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '1d':'1d', '1w':'1w'}
        bin_int = mapping.get(interval, '1h')
        # Thêm random param để bypass cache của server
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={bin_int}&limit=150&t={random.random()}"
        res = requests.get(url, timeout=5).json()
        df = pd.DataFrame(res, columns=['ts', 'Open', 'High', 'Low', 'Close', 'Vol', 'C_ts', 'Q_vol', 'Tr', 'T_b', 'T_q', 'Ig'])
        df[['Open', 'High', 'Low', 'Close']] = df[['Open', 'High', 'Low', 'Close']].astype(float)
        return df
    except: return None

def get_live_price_v179(symbol):
    if "BTC" in symbol:
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT&t={random.random()}"
            return float(requests.get(url, timeout=3).json()['price']), "Binance API"
        except: return None, "Offline"
    
    try:
        t = yf.Ticker(symbol)
        df = t.history(period='1d', interval='1m')
        if not df.empty: return df['Close'].iloc[-1], "Yahoo Live"
        return t.fast_info['last_price'], "Yahoo Fast"
    except: return None, "Yahoo Blocked"

# ==========================================
# 3. THUẬT TOÁN CHỈ BÁO
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 40: return None
    df = df.copy()
    c = 'Close'
    df['ma10'] = df[c].rolling(10).mean()
    df['ma20'] = df[c].rolling(20).mean()
    df['ma50'] = df[c].rolling(50).mean()
    delta = df[c].diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, adjust=False).mean()
    al = loss.ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + ag / al))
    df['rsi9'] = df['rsi'].rolling(9).mean()
    df['rsi45'] = df['rsi'].rolling(45).mean()
    
    df['div'] = "-"
    hi = argrelextrema(df['High'].values, np.greater, order=5)[0]
    li = argrelextrema(df['Low'].values, np.less, order=5)[0]
    if len(li) >= 2 and df[c].iloc[li[-1]] < df[c].iloc[li[-2]] and df['rsi'].iloc[li[-1]] > df['rsi'].iloc[li[-2]]:
        if (len(df)-1-li[-1]) < 10: df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
    if len(hi) >= 2 and df[c].iloc[hi[-1]] > df[c].iloc[hi[-2]] and df['rsi'].iloc[hi[-1]] < df['rsi'].iloc[hi[-2]]:
        if (len(df)-1-hi[-1]) < 10: df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
    return df

# ==========================================
# 4. GIAO DIỆN
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v179</h2>", unsafe_allow_html=True)
    
    if st.sidebar.button("♻️ XOÁ CACHE & TẢI LẠI"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph, table_ph = st.empty(), st.empty()
            
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                # 1. LẤY GIÁ LIVE
                live_p, src = get_live_price_v179(asset['symbol'])
                
                rows = []
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                    
                    # 2. LẤY DỮ LIỆU NẾN
                    if asset['binance']:
                        df_raw = fetch_binance_v179(asset['binance'], tf)
                    else:
                        try:
                            t = yf.Ticker(asset['symbol'])
                            df_raw = t.history(period='max' if 'd' in tf else '5d', interval=tf)
                        except: df_raw = None
                    
                    df = calculate_indicators(df_raw)
                    
                    if df is not None:
                        last = df.iloc[-1]
                        p_val = live_p if live_p else last['Close']
                        r = last['rsi']
                        rs = "TĂNG" if (r > last['rsi9'] and r > last['rsi45']) else "GIẢM"
                        
                        rows.append({
                            "Khung": tf.upper(), 
                            "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": rs, "Phân kỳ RSI": last['div'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), "Giá": f"{p_val:,.1f}"
                        })
                    else:
                        rows.append({"Khung": tf.upper(), "Xu hướng": "Dữ liệu lỗi", "Giá": f"{live_p:,.1f}" if live_p else "-"})

                if rows:
                    status_ph.success(f"💠 {asset['name']} | Nguồn: {src} | {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
