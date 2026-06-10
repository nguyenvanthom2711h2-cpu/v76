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
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, # Futures ổn định hơn trên Cloud
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# Danh sách khung thời gian
TIMEFRAMES = ['1h', '4h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade Dashboard v125", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Tính MA
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        # RSI Wilder's chuẩn TradingView
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
# 3. TRUY XUẤT DỮ LIỆU ĐỘC LẬP (FIX LẶP GIÁ)
# ==========================================
def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    return df.resample(rule).agg(logic).dropna()

# QUAN TRỌNG: Key của cache phải chứa cả 'tf' để không bị trùng số liệu
@st.cache_data(ttl=60)
def fetch_data_v125(symbol, tf):
    try:
        # Tải nến gốc tùy theo khung yêu cầu
        if 'h' in tf: fetch_tf, period = '1h', '730d'
        else: fetch_tf, period = '1d', 'max'
            
        # Thêm timeout và auto-headers ngầm của yfinance
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=20)
        
        if df.empty: return None
        # Sửa lỗi MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Gộp nến cho các khung không có sẵn
        rule_map = {'4h':'4H', '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'}
        if tf in rule_map:
            df = resample_ohlc(df, rule_map[tf])
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    if val == "YẾU": return 'color: #f1c40f; font-weight: bold'
    return ''

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Trade Dashboard v125</h1>", unsafe_allow_html=True)
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {datetime.now(VN_TZ).strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang phân tích {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                # Yahoo ko có nến Giờ cho VN-INDEX
                if asset['name'] == "VN-INDEX" and 'h' in tf: continue
                
                df = fetch_data_v125(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p = float(last['Close'])
                    if asset_price == 0: asset_price = p
                    
                    r, r9, r45 = float(last['rsi']), float(last['rsi9']), float(last['rsi45'])
                    
                    # Logic Trạng thái
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    # Xét đồng thuận
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        if r_code == 1 and prev['code'] == 1: agreement = "MUA (↑)"
                        elif r_code == -1 and prev['code'] == -1: agreement = "BÁN (↓)"
                    
                    sync_list.append({"code": r_code})
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": "TĂNG" if p > float(last['ma20']) else "GIẢM",
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p > float(last['ma50']) else "GIẢM",
                        "RSI": int(r),
                        "Giá": f"{p:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá: {asset_price:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50']))
            else:
                status.update(label=f"❌ {asset['name']} lỗi kết nối. Đang thử lại...", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
