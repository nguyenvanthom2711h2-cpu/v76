import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz
import requests

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG (Thế giới)", "symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# 12 Khung thời gian yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v124", layout="wide")

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RMA CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Tính MA
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        
        # RSI Wilder's (RMA)
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐỘC LẬP (CHỐNG LẶP SỐ)
# ==========================================
def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    return df.resample(rule).agg(logic).dropna()

@st.cache_data(ttl=30)
def fetch_data_v124(symbol, tf):
    """Tải dữ liệu độc lập cho từng khung để tránh lặp số"""
    try:
        # Giả lập Browser để tránh bị Yahoo chặn IP
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        if 'm' in tf: fetch_tf, period = tf, '5d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']): fetch_tf, period = '1h', '730d'
        else: fetch_tf, period = '1d', 'max'

        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=15)
        
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # Logic gộp nến cho các khung trung gian
        rule_map = {'2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}
        if tf in rule_map and tf != fetch_tf:
            df = resample_ohlc(df, rule_map[tf])
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    return 'color: #f1c40f; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v124</h1>", unsafe_allow_html=True)
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {datetime.now(VN_TZ).strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.expander(f"💠 {asset['name']}", expanded=True):
            data_rows = []
            sync_list = []
            
            for tf in TIMEFRAMES:
                # Yahoo ko có nến phút/giờ cho VN-INDEX
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                df = fetch_data_v124(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p, r, r9, r45 = float(last['Close']), float(last['rsi']), float(last['rsi9']), float(last['rsi45'])
                    
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        if r_code == 1 and prev['code'] == 1: agreement = "MUA (↑)"
                        elif r_code == -1 and prev['code'] == -1: agreement = "BÁN (↓)"
                    
                    sync_list.append({"code": r_code, "tf": tf})
                    wave = "TĂNG" if p > float(last['ma20']) else "GIẢM"
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": wave,
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "RSI": int(r),
                        "Giá": f"{p:,.1f}"
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45']))
            else:
                st.error(f"❌ {asset['name']} đang mất kết nối. Đang thử lại nguồn dữ liệu quốc tế...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
