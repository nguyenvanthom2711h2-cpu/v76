import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
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
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Real-time Trade Dashboard v98", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE (BỎ QUA CACHING)
# ==========================================
def get_realtime_price(symbol):
    """Lấy giá trực tiếp từ bảng điện Yahoo bằng nến 1 phút mới nhất"""
    try:
        # Tải nến 1 phút gần nhất, không dùng cache
        data = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=10)
        if not data.empty:
            # Sửa lỗi tiêu đề nhiều tầng của Yahoo bản mới
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return data['Close'].iloc[-1]
    except:
        return None
    return None

# ==========================================
# 3. TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 4. TẢI DỮ LIỆU LỊCH SỬ (CÓ CACHE NGẮN)
# ==========================================
@st.cache_data(ttl=60) # Lưu 60 giây để tránh bị Yahoo chặn IP
def fetch_history_v98(symbol, tf):
    try:
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        fetch_tf = yf_map.get(tf, '1h' if 'h' in tf else '1d')
        period = '730d' if fetch_tf == '1h' else 'max'
        
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False)
        if df.empty: return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if tf in ['4h', '8h', '12h']:
            df = df.resample(tf.upper()).agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 5. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Trade Dashboard v98</h1>", unsafe_allow_html=True)
    
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Lấy giá Live cho từng asset ngay tại lúc loop chạ
