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

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v121", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN (SMA & RSI RMA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Tính MA chuẩn
        df['ma10'] = df['Close'].rolling(10, min_periods=1).mean()
        df['ma20'] = df['Close'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        # RSI Wilder's (RMA) chuẩn TradingView
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
# 3. MÁY XỬ LÝ DỮ LIỆU (FIX LỖI KEYERROR)
# ==========================================
def clean_columns(df):
    """San phẳng tiêu đề Multi-Index của Yahoo Finance"""
    if df is not None and not df.empty:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    return df

def resample_ohlc(df, rule):
    """Gộp nến an toàn với tên cột đã được làm sạch"""
    if df is None or df.empty: return None
    try:
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        # Chỉ lấy những cột tồn tại trong df để tránh KeyError
        logic = {k: v for k, v in logic.items() if k in df.columns}
        return df.resample(rule).agg(logic).dropna()
    except: return None

@st.cache_data(ttl=60)
def fetch_master_data(symbol, tf_type):
    try:
        if tf_type == "small":
            # Tải nến 1h mồi
            df = yf.download(symbol, period='730d', interval='1h', progress=False)
        else:
            # Tải nến 1d mồi
            df = yf.download(symbol, period='max', interval='1d', progress=False)
        
        return clean_columns(df)
    except: return None

def get_live_p(symbol):
    try:
        data = yf.download(symbol, period='1d', interval='1m', progress=False)
        data = clean_columns(data)
        return float(data['Close'].iloc[-1])
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    color = 'white'
    if val in ["TĂNG", "HỒI (+)"]: color = "#00ff88"
    elif val in ["GIẢM", "CHỈNH (-)"]: color = "#ff4444"
    elif val == "YẾU": color = "#f1c40f"
    return f'color: {color}; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v121</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            real_p = get_live_p(asset['symbol'])
            real_p_str = f"{real_p:,.1f}" if real_p else "---"
            
            base_small = fetch_master_data(asset['symbol'], "small")
            base_large = fetch_master_data(asset['symbol'], "large")
            
            data_rows = []
            sync_list = []
            
            for tf in TIMEFRAMES:
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                df_source = base_small if any(x in tf for x in ['m', 'h', 'H']) else base_large
                if df_source is None: continue
                
                rule_map = {'15m':'15min','30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}
                
                # Resample nếu cần
                df_tf = resample_ohlc(df_source, rule_map[tf]) if tf in rule_map else df_source
                
                df_ind = calculate_indicators(df_tf)
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    p_val = last['Close']
                    r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                    
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
                        "Sóng": "TĂNG" if p_val > last['ma20'] else "GIẢM",
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM",
                        "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                        "RSI": int(r),
                        "Giá": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {real_p_str}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                status.update(label=f"❌ {asset['name']} lỗi kết nối.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
