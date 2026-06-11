import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz
import os, sys, contextlib

# Tắt cảnh báo
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

# 12 Khung thời gian yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Pro Master Dashboard v135", layout="wide")

@contextlib.contextmanager
def mute_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try: yield
        finally: sys.stdout = old_stdout

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Xử lý lỗi Multi-index của Yahoo mới
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['ma10'] = df['Close'].rolling(10, min_periods=1).mean()
        df['ma20'] = df['Close'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        # RSI chuẩn TradingView
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA TẦNG (FIX NAMEERROR)
# ==========================================
def resample_ohlc(df, rule):
    try:
        df.index = pd.to_datetime(df.index)
        logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        return df.resample(rule).agg(logic).dropna()
    except: return df

@st.cache_data(ttl=60)
def fetch_data_stable(symbol, tf):
    """Hàm lấy dữ liệu duy nhất và ổn định nhất"""
    try:
        # Xác định fetch gốc để đảm bảo đủ dữ liệu tính RSI
        if 'm' in tf and '1m' not in tf: 
            f_tf, period = tf, '7d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']):
            f_tf, period = '1h', '730d'
        else:
            f_tf, period = '1d', 'max'
            
        with mute_stdout():
            df = yf.download(symbol, period=period, interval=f_tf, progress=False, timeout=20)
        
        if df.empty: return None
        
        # Gộp nến cho khung trung gian
        rule_map = {'30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
        if tf in rule_map and tf != f_tf:
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v135</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang phân tích {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                # Chặn khung phút cho VN-INDEX để tránh lỗi Yahoo
                if asset['name'] == "VN-INDEX" and 'm' in tf: continue
                
                # SỬA LỖI TÊN HÀM TẠI ĐÂY
                df = fetch_data_stable(asset['symbol'], tf)
                
                if df is not None:
                    last = df.iloc[-1]
                    p_val = float(last['Close'])
                    if asset_price == 0: asset_price = p_val
                    
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    
                    # Logic trạng thái
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
                        "Sóng": "TĂNG" if p_val > float(last['ma20']) else "GIẢM",
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p_val > float(last['ma50']) else "GIẢM",
                        "MA 10/20": "TĂNG" if float(last['ma10']) > float(last['ma20']) else "GIẢM",
                        "RSI": int(r),
                        "Giá": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {asset_price:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                st.error(f"❌ {asset['name']} không có dữ liệu.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
