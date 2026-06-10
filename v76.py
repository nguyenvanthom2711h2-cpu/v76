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
    {"name": "VÀNG", "symbol": "GC=F"}, # Dùng Futures để Yahoo dễ nhả dữ liệu hơn
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1m']

st.set_page_config(page_title="Pro Trade Dashboard v118", layout="wide")

# ==========================================
# 2. TÍNH TOÁN KỸ THUẬT (RMA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        df['ma10'] = df['Close'].rolling(window=10).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU Độc Lập (SỬA LỖI TRÙNG SỐ)
# ==========================================
# Dùng cache theo cả symbol và tf để không bị trùng số liệu
@st.cache_data(ttl=60) 
def fetch_data_v118(symbol, tf):
    try:
        # Giả lập trình duyệt để tránh bị Yahoo chặn
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        
        # Phân loại khung để tải dữ liệu gốc
        if 'h' in tf: fetch_tf, period = '1h', '730d'
        else: fetch_tf, period = '1d', 'max'
            
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, session=session, timeout=15)
        if df.empty: return None
        
        # Xử lý gộp nến 4h thủ công
        if tf == '4h':
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            df = df.resample('4H').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            
        return calculate_indicators(df)
    except: return None

def get_live_price(symbol):
    try:
        data = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=5)
        if not data.empty:
            if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
            return float(data['Close'].iloc[-1])
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_table(val):
    color = 'white'
    if val in ["TĂNG", "HỒI (+)"]: color = "#00ff88"
    elif val in ["GIẢM", "CHỈNH (-)"]: color = "#ff4444"
    elif val == "YẾU": color = "#f1c40f"
    return f'color: {color}; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v118</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Cập nhật thực: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            live_p = get_live_price(asset['symbol'])
            live_p_str = f"{live_p:,.1f}" if live_p else "---"
            
            data_rows = []
            for tf in TIMEFRAMES:
                # Yahoo ko có nến Giờ cho VN-Index
                if asset['name'] == "VN-INDEX" and 'h' in tf: continue
                
                df = fetch_data_v118(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    # Chỉ dùng giá Live cho khung 1H
                    p_val = live_p if (tf == '1h' and live_p) else last['Close']
                    r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat = "TĂNG"
                    elif r < r9 and r < r45: r_stat = "GIẢM"
                    elif r > r45 and r < r9: r_stat = "CHỈNH (-)"
                    elif r < r45 and r > r9: r_stat = "HỒI (+)"
                    else: r_stat = "YẾU"
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": "TĂNG" if p_val > last['ma20'] else "GIẢM",
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM",
                        "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                        "RSI": int(r),
                        "Giá HT": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá: {live_p_str}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_table, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                status.update(label=f"❌ {asset['name']} hiện đang mất kết nối dữ liệu.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
