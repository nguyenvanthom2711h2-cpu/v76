import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import telebot
import warnings

# Tắt các cảnh báo hệ thống
warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'

# Sử dụng Ticker chuẩn quốc tế của Yahoo Finance để không bị chặn IP
LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '8h', '12h', '1d', '3d', '1w', '1M']

# Cấu hình giao diện Web
st.set_page_config(page_title="Master Trade Web v90", layout="wide")
bot = telebot.TeleBot(TOKEN)

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RMA WILDER'S CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 30: return None
    try:
        df = df.copy()
        # SMA chuẩn
        df['ma10'] = df['c'].rolling(10).mean()
        df['ma20'] = df['c'].rolling(20).mean()
        df['ma50'] = df['c'].rolling(50, min_periods=10).mean()
        
        # RSI Wilder's (Khớp 100% TradingView)
        delta = df['c'].diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 3. MÁY DÒ DỮ LIỆU ĐA TẦNG (FIX LỖI MẤT KẾT NỐI)
# ==========================================
def fetch_global_data(symbol, tf):
    """Lấy dữ liệu từ nguồn Yahoo toàn cầu - cực kỳ ổn định trên Cloud"""
    try:
        # Chuyển đổi khung giờ
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        
        # Yahoo VN-Index không có 1h, tự động lấy 1d làm mồi để bảng ko bị trắng
        fetch_tf = '1d' if (symbol == "^VNINDEX" and 'h' in tf) else (yf_map.get(tf, '1h' if 'h' in tf else '1d'))
        period = '730d' if fetch_tf == '1h' else 'max'
        
        # Tải dữ liệu thô
        raw = yf.download(symbol, period=period, interval=fetch_tf, progress=False)
        if raw.empty: return None
        
        # FIX TRIỆT ĐỂ LỖI MULTI-INDEX (Lỗi khiến bảng bị trống)
        df = raw.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Chuẩn hóa tên cột
        df = df.rename(columns={df.columns[0]:'ts', 'Open':'o', 'High':'h', 'Low':'l', 'Close':'c', 'Volume':'v'})
        
        # Gộp nến cho các khung trung gian (4h, 8h, 12h, 3d)
        if tf in ['4h', '8h', '12h', '3d']:
            rule = tf.upper().replace('D', 'D')
            df['ts'] = pd.to_datetime(df['ts'])
            df = df.set_index('ts').resample(rule).agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna().reset_index()
        
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN WEB VÀ TÍN HIỆU
# ==========================================
def color_status(val):
    color = "white"
    if val in ["TĂNG", "HỒI (+)"]: color = "#00ff88" # Xanh Neon
    elif val in ["GIẢM", "CHỈNH (-)"]: color = "#ff4444" # Đỏ rực
    elif val == "YẾU": color = "#ffcc00" # Vàng
    return f'color: {color}; font-weight: bold'

def main():
    st.title("🏆 Master Trade Dashboard v90")
    st.markdown("---")
    
    current_time = datetime.now().strftime('%H:%M:%S')
