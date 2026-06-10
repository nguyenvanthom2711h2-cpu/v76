import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "fallback": "BTC-USD"},
    {"name": "VÀNG", "symbol": "XAUUSD=X", "fallback": "GC=F"}, # Nếu Spot lỗi thì lấy Futures
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "fallback": "^VNINDEX"}
]

# Đầy đủ 12 khung thời gian yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Pro Trade Dashboard v105", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 10: return None
    try:
        df = df.copy()
        # Tính MA chuẩn
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        
        # RSI chuẩn TradingView
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. MÁY TẢI DỮ LIỆU ĐA NGUỒN (SIÊU ỔN ĐỊNH)
# ==========================================
@st.cache_data(ttl=30)
def fetch_and_resample(symbol, tf, fallback_symbol):
    try:
        # Xác định khung gốc
        if any(x in tf for x in ['m', '1h']):
            fetch_tf = tf if 'm' in tf else '1h'
            period = '7d' if 'm' in tf else '730d'
        elif any(x in tf for x in ['2h', '4h', '8h', '12h']):
            fetch_tf, period = '1h', '730d'
        else:
            fetch_tf, period = '1d', 'max'

        # Tải dữ liệu (Thử mã chính, nếu lỗi dùng mã dự phòng)
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=10)
        if df.empty:
            df = yf.download(fallback_symbol, period=period, interval=fetch_tf, progress=False, timeout=10)
            
        if df.empty: return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df.index = pd.to_datetime(df.index)

        # Logic gộp nến (Resampling)
        rule_map = {
            '2h':'2H', '4h':'4H', '8h':'8H', '12h':'12H', 
            '3d':'3D', '1w':'W-MON', '1M':'ME', '3M':'3ME'
        }
        
        if tf in rule_map and tf != fetch_tf:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
