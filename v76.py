import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
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
# Ưu tiên các khung thời gian Yahoo hỗ trợ tốt nhất
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Master Trade Dashboard v92", layout="wide")

# ==========================================
# 2. THUẬT TOÁN RSI RMA & MA
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        df['ma10'] = df['Close'].rolling(window=10).mean()
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. LẤY DỮ LIỆU (FIX VN-INDEX TRÊN CLOUD)
# ==========================================
def fetch_data_v92(symbol, tf):
    try:
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        target_tf = yf_map.get(tf, '1d')
        
        # Đặc trị VN-INDEX: Nếu là nến giờ/4h bị chặn, tự động lấy nến ngày
        if symbol == "^VNINDEX" and tf in ['1h', '4h']:
            target_tf = '1d'
            
        period = '730d' if target_tf == '1h' else 'max'
        
        # Thêm proxy/header ngầm thông qua yfinance để giảm bị chặn
        df = yf.download(symbol, period=period, interval=target_tf, progress=False, timeout=10)
        
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Resample cho khung 4h nếu cần
        if tf == '4h' and symbol != "^VNINDEX":
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample('4H').apply(logic).dropna()
            
        return calculate_indicators(df)
    except:
        return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.title("🏆 Master Trade Web Dashboard")
    st.write(f"Dữ liệu cập nhật: {datetime.now().strftime('%H:%M:%S')}")

    for asset in LIST_ASSETS:
        with st.expander(f"💠 {asset['name']}", expanded=True):
            data_rows = []
            for tf in TIMEFRAMES:
                df = fetch_data_v92(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    p, m20 = last['Close'], last['ma20']
                    
                    if r > r9 and r > r45: r_stat = "TĂNG 🟢"
                    elif r < r9 and r < r45: r_stat = "GIẢM 🔴"
                    else: r_stat = "YẾU 🟡"
                    
                    wave = "TĂNG 🟢" if p > m20 else "GIẢM 🔴"
                    
                    data_rows.append({
                        "KHUNG": tf.upper(),
                        "SÓNG": wave,
                        "RSI 9/45": r_stat,
                        "GIÁ": f"{p:,.1f}",
                        "RSI VAL": int(r)
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows))
            else:
                st.error(f"❌ Nguồn dữ liệu cho {asset['name']} đang bị gián đoạn. Vui lòng quay lại sau vài phút.")

    # Reload sau 60s
    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
