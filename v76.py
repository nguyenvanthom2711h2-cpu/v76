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
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# Danh sách đầy đủ 12 khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Pro Trade Dashboard v126", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RMA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 10: return None
    try:
        df = df.copy()
        # Đảm bảo tiêu đề cột phẳng
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA TẦNG (CHỐNG LẶP GIÁ)
# ==========================================
def resample_ohlc(df, rule):
    try:
        df.index = pd.to_datetime(df.index)
        logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        return df.resample(rule).agg(logic).dropna()
    except: return df

@st.cache_data(ttl=60)
def fetch_data_v126(symbol, tf):
    """Tải dữ liệu độc lập cho 12 khung để tránh lặp số và thiếu khung"""
    try:
        # Xác định fetch_tf và period dựa trên yêu cầu
        if 'm' in tf: 
            fetch_tf, period = tf, '5d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']): 
            fetch_tf, period = '1h', '730d'
        else: 
            fetch_tf, period = '1d', 'max'

        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=20)
        if df.empty: return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Logic gộp nến cho các khung không có sẵn trên Yahoo
        rule_map = {
            '2h':'2H', '4h':'4H', '8h':'8H', '12h':'12H', 
            '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'
        }
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
    if val == "YẾU": return 'color: #f1c40f; font-weight: bold'
    return ''

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Master Dashboard v126</h1>", unsafe_allow_html=True)
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {datetime.now(VN_TZ).strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            
            for tf in TIMEFRAMES:
                # Yahoo ko có nến phút/giờ cho VN-INDEX
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                df = fetch_data_v126(asset['symbol'], tf)
                if df is not None and not df.empty:
                    last = df.iloc[-1]
                    p = float(last['Close'])
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    
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
                    
                    sync_list.append({"code": r_code})
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": "TĂNG" if p > float(last['ma20']) else "GIẢM",
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p > float(last['ma50']) else "GIẢM",
                        "RSI": int(r),
                        "Giá HT": f"{p:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Đồng bộ hoàn tất", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50']))
            else:
                status.update(label=f"❌ {asset['name']} lỗi kết nối dữ liệu.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
