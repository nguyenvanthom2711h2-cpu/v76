import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz
import telebot

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG (Spot)", "symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# Đầy đủ 12 khung thời gian yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Pro Master Dashboard v142", layout="wide")

# ==========================================
# 2. THUẬT TOÁN RSI RMA (CHUẨN 100% TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 5: return None
    try:
        df = df.copy()
        # Đảm bảo tiêu đề phẳng
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['ma10'] = df['Close'].rolling(10, min_periods=1).mean()
        df['ma20'] = df['Close'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        
        # RMA chuẩn TradingView
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. XỬ LÝ DỮ LIỆU ĐA TẦNG (FIX THIẾU KHUNG)
# ==========================================
def resample_ohlc(df, rule):
    try:
        df.index = pd.to_datetime(df.index)
        logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        return df.resample(rule).agg(logic).dropna()
    except: return df

@st.cache_data(ttl=60)
def fetch_master_data(symbol, tf):
    """Tải dữ liệu mồi cực dài để tính toán 12 khung không bị lỗi"""
    try:
        # Nhóm 1: Phút
        if 'm' in tf and tf != '1m' and tf != '3m':
            f_tf, period = tf, '7d'
        # Nhóm 2: Giờ (Lấy 1H để gộp ra 2H, 4H, 8H, 12H)
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']):
            f_tf, period = '1h', '730d'
        # Nhóm 3: Ngày (Lấy 1D để gộp ra 3D, 1W, 1M, 3M)
        else:
            f_tf, period = '1d', 'max'

        df = yf.download(symbol, period=period, interval=f_tf, progress=False, timeout=20)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # Thực hiện Resample nếu khung yêu cầu không có sẵn trên Yahoo
        rule_map = {
            '2h':'2H', '4h':'4H', '8h':'8H', '12h':'12H', 
            '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'
        }
        if tf in rule_map and tf != f_tf:
            df = resample_ohlc(df, rule_map[tf])
            
        return calculate_indicators(df)
    except: return None

def get_live_p(symbol):
    try:
        data = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=5)
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        return float(data['Close'].iloc[-1])
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v142</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    bot = telebot.TeleBot(TOKEN)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ 12 khung cho {asset['name']}...", expanded=True) as status:
            live_p = get_live_p(asset['symbol'])
            live_p_str = f"{live_p:,.1f}" if live_p else "---"
            
            data_rows = []
            sync_list = []
            
            for tf in TIMEFRAMES:
                # VN-INDEX bỏ qua khung phút/giờ lẻ (Yahoo ko hỗ trợ)
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h']):
                    if tf not in ['1d', '1w', '1m', '3m']: continue
                
                df = fetch_master_data(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p_val = float(last['Close'])
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
                    
                    sync_list.append({"tf": tf, "code": r_code})
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": "TĂNG" if p_val > float(last['ma20']) else "GIẢM",
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p_val > float(last['ma50']) else "GIẢM",
                        "RSI": int(r),
                        "Giá": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {live_p_str}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50']))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
