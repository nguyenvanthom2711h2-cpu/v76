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
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade v167", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE THỰC (Fix lỗi đứng giá)
# ==========================================
def get_live_price_v167(symbol):
    if "BTC" in symbol:
        try:
            # Lấy giá trực tiếp từ sàn Binance (không bị cache)
            res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=3)
            return float(res.json()['price'])
        except: pass
    
    try:
        t = yf.Ticker(symbol)
        df = t.history(period='1d', interval='1m')
        if not df.empty: return float(df['Close'].iloc[-1])
        return t.fast_info['last_price']
    except: return None

# ==========================================
# 3. THUẬT TOÁN
# ==========================================
def detect_divergence(df, order=5):
    try:
        if len(df) < 35: return "-"
        high = df['High'].values
        low = df['Low'].values
        rsi = df['rsi_val'].values
        hi = argrelextrema(high, np.greater, order=order)[0]
        li = argrelextrema(low, np.less, order=order)[0]
        if len(li) >= 2:
            i2, i1 = li[-2], li[-1]
            if low[i1] < low[i2] and rsi[i1] > rsi[i2]:
                if (len(df) - 1 - i1) < 12: return "HỘI TỤ (MUA) 🚀"
        if len(hi) >= 2:
            i2, i1 = hi[-2], hi[-1]
            if high[i1] > high[i2] and rsi[i1] < rsi[i2]:
                if (len(df) - 1 - i1) < 12: return "PHÂN KỲ (BÁN) 📉"
        return "-"
    except: return "-"

def calculate_indicators(df):
    if df is None or len(df) < 50: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        c = 'Close'
        df['ma10'] = df[c].rolling(10).mean()
        df['ma20'] = df[c].rolling(20).mean()
        df['ma50'] = df[c].rolling(50).mean()
        delta = df[c].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        ag = gain.ewm(alpha=1/14, adjust=False).mean()
        al = loss.ewm(alpha=1/14, adjust=False).mean()
        df['rsi_val'] = 100 - (100 / (1 + ag / al))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        df['div_status'] = detect_divergence(df)
        return df
    except: return None

def fetch_data_v167(symbol, tf):
    try:
        p = '5d' if 'm' in tf else ('730d' if 'h' in tf else 'max')
        f_tf = '1h' if ('h' in tf and tf != '1h') else ('1d' if tf == '3d' else tf)
        df = yf.download(symbol, period=p, interval=f_tf, progress=False, timeout=15)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        rule = {'2h':'2h','4h':'4h','8h':'8h','12h':'12h','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
        if tf in rule:
            df = df.resample(rule[tf]).agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
        return calculate_indicators(df)
    except: return None

def style_text(val):
    if val in ["TĂNG", "HỒI (+)", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "CHỈNH (-)", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v167</h2>", unsafe_allow_html=True)
    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph = st.empty()
            table_ph = st.empty()
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                live_p = get_live_price_v167(asset['symbol'])
                rows = []
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                    df = fetch_data_v167(asset['symbol'], tf)
                    if df is not None:
                        last = df.iloc[-1]
                        p_val = live_p if live_p else float(last['Close'])
                        r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                        if r > r9 and r > r45: rs = "TĂNG"
                        elif r < r9 and r < r45: rs = "GIẢM"
                        elif r9 > r > r45: rs = "CHỈNH (-)"
                        else: rs = "HỒI (+)"
                        rows.append({
                            "Khung": tf.upper(), 
                            "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": rs, 
                            "Phân kỳ RSI": last['div_status'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), 
                            "Giá": f"{p_val:,.1f}"
                        })
                if rows:
                    status_ph.success(f"💠 {asset['name']} | Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
