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

st.set_page_config(page_title="Master Trade Dashboard v132", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN RSI RMA (CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        # Tính MA (SMA)
        df['ma10'] = df['Close'].rolling(10).mean()
        df['ma20'] = df['Close'].rolling(20).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        # --- THUẬT TOÁN RSI WILDER'S (RMA) CHUẨN ---
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # TradingView dùng alpha = 1/period và adjust=False
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU "SẠCH" (FIX LỖI MẤT KẾT NỐI)
# ==========================================
def clean_df(df):
    """Xử lý lỗi Multi-Index của Yahoo để lấy đúng cột Close"""
    if df is None or df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

@st.cache_data(ttl=60)
def fetch_master_data(symbol):
    """Tải dữ liệu mồi cực dài để RSI hội tụ chuẩn"""
    try:
        # Nguồn nến nhỏ (7 ngày)
        d15m = clean_df(yf.download(symbol, period='7d', interval='15m', progress=False))
        # Nguồn nến giờ (730 ngày - Giới hạn của Yahoo)
        d1h = clean_df(yf.download(symbol, period='730d', interval='1h', progress=False))
        # Nguồn nến ngày (Max lịch sử để RSI45 chuẩn)
        d1d = clean_df(yf.download(symbol, period='max', interval='1d', progress=False))
        
        return {"15m": d15m, "1h": d1h, "1d": d1d}
    except: return None

def get_tf_data(master, tf, is_vnindex=False):
    """Gộp nến chính xác từng khung thời gian"""
    try:
        rule_map = {'30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
        
        # Chọn nguồn dữ liệu
        if 'm' in tf: src = master['15m']
        elif any(x in tf for x in ['h', 'H']): 
            src = master['1h'] if not is_vnindex else master['1d'] # VNINDEX dùng 1D thay cho 1H
        else: src = master['1d']
        
        if src is None or src.empty: return None
        
        df = src.copy()
        if tf in rule_map:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    return 'color: #f1c40f; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Trade Dashboard v132</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ dữ liệu {asset['name']}...", expanded=True) as status:
            master = fetch_master_data(asset['symbol'])
            if master is None or master['1d'] is None:
                st.error(f"❌ {asset['name']} không thể kết nối Yahoo Finance.")
                continue

            # Lấy giá live từ nến mới nhất
            live_p = float(master['1h' if master['1h'] is not None else '1d']['Close'].iloc[-1])
            data_rows = []
            sync_list = []
            
            for tf in TIMEFRAMES:
                # VN-INDEX bỏ qua khung phút
                if asset['name'] == "VN-INDEX" and 'm' in tf: continue
                
                df_ind = get_tf_data(master, tf, is_vnindex=(asset['name'] == "VN-INDEX"))
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    p_val = float(last['Close'])
                    r, r9, r45 = float(last['rsi']), float(last['rsi9']), float(last['rsi45'])
                    
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
                status.update(label=f"💠 {asset['name']} | Giá: {live_p:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
