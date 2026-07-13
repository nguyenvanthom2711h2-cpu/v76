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

VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

# ==========================================
# 1. HÀM LẤY GIÁ & NẾN TỪ BYBIT (CỰC KỲ ỔN ĐỊNH)
# ==========================================
def fetch_bybit_v183(interval):
    """Dùng Bybit API thay cho Binance/Yahoo để tránh bị chặn IP"""
    try:
        # Mapping timeframe sang Bybit (phút)
        mapping = {'15m':'15', '30m':'30', '1h':'60', '2h':'120', '4h':'240', '8h':'480', '12h':'720', '1d':'D', '1w':'W'}
        itv = mapping.get(interval, '60')
        
        # Gọi API Bybit công khai
        url = f"https://api.bybit.com/v5/market/kline?category=inverse&symbol=BTCUSD&interval={itv}&limit=150"
        res = requests.get(url, timeout=5).json()
        
        # Bybit trả về list: [start_time, open, high, low, close, volume, turnover]
        raw_data = res['result']['list']
        df = pd.DataFrame(raw_data, columns=['ts', 'Open', 'High', 'Low', 'Close', 'Vol', 'Turnover'])
        
        # Bybit trả về dữ liệu từ mới đến cũ -> Đảo ngược lại
        df = df.iloc[::-1].reset_index(drop=True)
        
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        return None

def get_bybit_live():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=inverse&symbol=BTCUSD"
        res = requests.get(url, timeout=3).json()
        return float(res['result']['list'][0]['lastPrice'])
    except:
        return None

# ==========================================
# 2. CHỈ BÁO & LOGIC (GIỮ NGUYÊN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 45: return None
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
    df['rsi9'], df['rsi45'] = df['rsi'].rolling(9).mean(), df['rsi'].rolling(45).mean()
    
    # Phân kỳ
    hi = argrelextrema(df['High'].values, np.greater, order=5)[0]
    li = argrelextrema(df['Low'].values, np.less, order=5)[0]
    df['div'] = "-"
    if len(li) >= 2 and df[c].iloc[li[-1]] < df[c].iloc[li[-2]] and df['rsi'].iloc[li[-1]] > df['rsi'].iloc[li[-2]]:
        if (len(df)-1-li[-1]) < 10: df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
    if len(hi) >= 2 and df[c].iloc[hi[-1]] > df[c].iloc[hi[-2]] and df['rsi'].iloc[hi[-1]] < df['rsi'].iloc[hi[-2]]:
        if (len(df)-1-hi[-1]) < 10: df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
    return df

def style_text(val):
    if val in ["TĂNG", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

# ==========================================
# 3. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v183</h2>", unsafe_allow_html=True)
    
    # Ép buộc Reset cache mỗi khi load lại
    st.cache_data.clear()

    # Chỉ tập trung giải quyết BITCOIN trước
    tabs = st.tabs(["BITCOIN", "VÀNG & VNINDEX"])

    with tabs[0]:
        status_ph = st.empty()
        table_ph = st.empty()
        with st.spinner("Đang lấy dữ liệu từ Bybit..."):
            live_p = get_bybit_live()
            rows = []
            for tf in ['15m', '30m', '1h', '2h', '4h', '8h', '1d']:
                df_raw = fetch_bybit_v183(tf)
                df = calculate_indicators(df_raw)
                if df is not None:
                    last = df.iloc[-1]
                    p_val = live_p if live_p else last['Close']
                    r = last['rsi']
                    rs = "TĂNG" if (r > last['rsi9'] and r > last['rsi45']) else "GIẢM"
                    rows.append({
                        "Khung": tf.upper(), "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                        "RSI 9/45": rs, "Phân kỳ RSI": last['div'],
                        "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                        "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                        "RSI": int(r), "Giá": f"{p_val:,.1f}"
                    })
            
            if rows:
                status_ph.success(f"💠 BITCOIN | Nguồn: Bybit Live | {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                table_ph.table(pd.DataFrame(rows).style.map(style_text))
            else:
                st.error("Bybit API cũng đang bị chặn IP. Vui lòng chuyển sang Cách 1 (Hugging Face).")

    with tabs[1]:
        st.info("Yahoo Finance đang khóa IP của máy chủ này. Vàng và VN-INDEX tạm thời không khả dụng.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
