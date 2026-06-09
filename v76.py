import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import requests
import warnings

# Tắt cảnh báo
warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Trade Master v93", layout="wide")

# ==========================================
# 2. BỘ MÁY LẤY DỮ LIỆU "VƯỢT RÀO"
# ==========================================
def fetch_data_robust(symbol, tf):
    """Lấy dữ liệu có giả lập trình duyệt để tránh bị Yahoo chặn"""
    try:
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        target_tf = yf_map.get(tf, '1d')
        
        # Đặc trị VNINDEX trên Cloud: Ưu tiên khung Ngày nếu khung Giờ bị chặn
        if symbol == "^VNINDEX" and 'h' in tf:
            target_tf = '1d'
            
        period = '730d' if target_tf == '1h' else 'max'
        
        # Tạo session giả lập trình duyệt
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        df = yf.download(symbol, period=period, interval=target_tf, progress=False, session=session, timeout=15)
        
        if df.empty: return None
        
        # Làm phẳng dữ liệu Multi-Index
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Gộp nến 4h thủ công nếu cần
        if tf == '4h':
            df = df.resample('4H').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            
        return df
    except:
        return None

# ==========================================
# 3. TÍNH TOÁN CHỈ BÁO
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        
        # RSI Wilder's
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 4. GIAO DIỆN WEB
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center;'>🏆 Master Trade Dashboard v93</h1>", unsafe_allow_html=True)
    st.write(f"<p style='text-align: center;'>Cập nhật: {datetime.now().strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.expander(f"💠 {asset['name']}", expanded=True):
            data_rows = []
            # Thêm vòng lặp tải dữ liệu
            for tf in TIMEFRAMES:
                raw_df = fetch_data_robust(asset['symbol'], tf)
                df = calculate_indicators(raw_df)
                if df is not None:
                    last = df.iloc[-1]
                    p, r, r9, r45, m20 = last['Close'], last['rsi'], last['rsi9'], last['rsi45'], last['ma20']
                    
                    # Xác định trạng thái
                    if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                    elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                    else: r_stat = "🟡 YẾU"
                    
                    wave = "🟢 TĂNG" if p > m20 else "🔴 GIẢM"
                    
                    data_rows.append({
                        "KHUNG": tf.upper(),
                        "SÓNG": wave,
                        "RSI 9/45": r_stat,
                        "GIÁ": f"{p:,.1f}",
                        "RSI": int(r)
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows))
            else:
                st.warning(f"🔄 Đang kết nối lại nguồn dữ liệu cho {asset['name']}...")

    # Tự động làm mới
    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
