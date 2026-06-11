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
    {"name": "VÀNG (Spot)", "symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade Dashboard v127", layout="wide")

# ==========================================
# 2. THUẬT TOÁN RSI RMA (CHUẨN 100% TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 30: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # MA chuẩn (SMA)
        df['ma10'] = df['Close'].rolling(10).mean()
        df['ma20'] = df['Close'].rolling(20).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        # --- THUẬT TOÁN RSI WILDER'S (RMA) ---
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # Wilder's dùng alpha = 1/period và adjust=False để hội tụ chuẩn
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        df['rsi_val'] = 100 - (100 / (1 + rs))
        
        # RSI Signals (SMA của RSI)
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐỘC LẬP
# ==========================================
def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    return df.resample(rule).agg(logic).dropna()

@st.cache_data(ttl=60)
def fetch_data_v127(symbol, tf):
    try:
        # Tải dữ liệu "mồi" cực dài để RSI chính xác (300 nến trở lên)
        if 'm' in tf: fetch_tf, period = tf, '7d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']): 
            fetch_tf, period = '1h', '730d' # Tải nến giờ trong 2 năm
        else: 
            fetch_tf, period = '1d', 'max' # Tải nến ngày tối đa lịch sử

        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=20)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # Logic gộp nến cho các khung trung gian
        rule_map = {'2h':'2H', '4h':'4H', '8h':'8H', '12h':'12H', '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'}
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v127</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ dữ liệu {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            
            # Lấy giá live từ khung 1D để làm header
            df_price = fetch_data_v127(asset['symbol'], '1d')
            live_p = df_price['Close'].iloc[-1] if df_price is not None else 0

            for tf in TIMEFRAMES:
                # VN-INDEX bỏ qua khung nhỏ
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                df = fetch_data_v127(asset['symbol'], tf)
                if df is not None and not df.empty:
                    last = df.iloc[-1]
                    p_val = last['Close']
                    r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                    
                    # Xác định trạng thái RSI 9/45
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r > r45 and r < r9: r_stat, r_code = "CHỈNH (-)", 0
                    elif r < r45 and r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    # Xét đồng thuận
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        if r_code == 1 and prev['code'] == 1: agreement = "MUA (↑)"
                        elif r_code == -1 and prev['code'] == -1: agreement = "BÁN (↓)"
                    
                    sync_list.append({"tf": tf, "code": r_code})
                    
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
                status.update(label=f"💠 {asset['name']} | Giá HT: {live_p:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
