import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import telebot
import warnings

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Pro Trade Dashboard v91", layout="wide")

# ==========================================
# 2. TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 30: return None
    try:
        df = df.copy()
        # SMA 10, 20, 50
        df['ma10'] = df['Close'].rolling(window=10).mean()
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        
        # RSI Wilder's chuẩn
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45).mean()
        return df
    except Exception as e:
        return None

# ==========================================
# 3. LẤY DỮ LIỆU (FIX LỖI MULTI-INDEX)
# ==========================================
def fetch_data(symbol, tf):
    try:
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        fetch_tf = '1d' if (symbol == "^VNINDEX" and 'h' in tf) else (yf_map.get(tf, '1h' if 'h' in tf else '1d'))
        period = '730d' if fetch_tf == '1h' else 'max'
        
        # Tải dữ liệu
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False)
        if df.empty: return None
        
        # Xử lý Multi-Index nếu có (Yahoo mới thường bị lỗi này)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Đảm bảo có cột Close
        if 'Close' not in df.columns: return None

        # Gộp nến cho khung 4h
        if tf == '4h':
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample('4H').apply(logic).dropna()
            
        return calculate_indicators(df)
    except:
        return None

# ==========================================
# 4. GIAO DIỆN WEB
# ==========================================
def main():
    st.header("🏆 Master Trade Live Dashboard")
    st.write(f"Cập nhật cuối: {datetime.now().strftime('%H:%M:%S')}")
    
    # Nút bấm thủ công
    if st.button('🔄 Làm mới ngay lập tức'):
        st.rerun()

    for asset in LIST_ASSETS:
        with st.expander(f"💠 {asset['name']}", expanded=True):
            data_rows = []
            cols = st.columns(len(TIMEFRAMES))
            
            for tf in TIMEFRAMES:
                df = fetch_data(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    p, m20, m50 = last['Close'], last['ma20'], last['ma50']
                    
                    # Trạng thái
                    if r > r9 and r > r45: r_stat, r_col = "TĂNG", "green"
                    elif r < r9 and r < r45: r_stat, r_col = "GIẢM", "red"
                    else: r_stat, r_col = "YẾU", "orange"
                    
                    wave = "TĂNG" if p > m20 else "GIẢM"
                    w_col = "green" if wave == "TĂNG" else "red"
                    
                    data_rows.append({
                        "KHUNG": tf.upper(),
                        "SÓNG": wave,
                        "RSI 9/45": r_stat,
                        "GIÁ": f"{p:,.1f}",
                        "RSI": int(r)
                    })
            
            if data_rows:
                res_df = pd.DataFrame(data_rows)
                st.dataframe(res_df, use_container_width=True)
            else:
                st.warning(f"Đang chờ dữ liệu cho {asset['name']}...")

    # Cơ chế tự động reload sau 1 phút
    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
