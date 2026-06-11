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

# Đầy đủ 12 khung thời gian theo yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade Dashboard v131", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 10: return None
    try:
        df = df.copy()
        # Đảm bảo cột Close là 1 chiều
        if isinstance(df['Close'], pd.DataFrame):
            df['Close'] = df['Close'].iloc[:, 0]
            
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        df['ma10'] = df['Close'].rolling(window=10, min_periods=1).mean()
        
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
# 3. "XƯỞNG ĐÚC NẾN" - RESAMPLE TỪ DỮ LIỆU GỐC
# ==========================================
def resample_ohlc(df, rule):
    try:
        df.index = pd.to_datetime(df.index)
        logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        return df.resample(rule).agg(logic).dropna()
    except: return df

@st.cache_data(ttl=60)
def fetch_master_data(symbol):
    """Tải 3 khối dữ liệu gốc để gộp cho tất cả các khung"""
    try:
        # Nguồn 1: Nến 15m (lịch sử 5 ngày)
        df_15m = yf.download(symbol, period='5d', interval='15m', progress=False)
        # Nguồn 2: Nến 1h (lịch sử 2 năm)
        df_1h = yf.download(symbol, period='730d', interval='1h', progress=False)
        # Nguồn 3: Nến 1d (Toàn bộ lịch sử)
        df_1d = yf.download(symbol, period='max', interval='1d', progress=False)
        
        # Làm phẳng tiêu đề cho cả 3
        res = {}
        for k, d in [("15m", df_15m), ("1h", df_1h), ("1d", df_1d)]:
            if not d.empty:
                if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
                res[k] = d
            else: res[k] = None
        return res
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Master Dashboard v131</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Cập nhật: {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đúc nến đa khung cho {asset['name']}...", expanded=True) as status:
            master = fetch_master_data(asset['symbol'])
            if not master or master['1d'] is None:
                st.error(f"❌ {asset['name']} mất kết nối dữ liệu.")
                continue

            live_p = float(master['15m' if master['15m'] is not None else '1h']['Close'].iloc[-1])
            data_rows = []
            sync_list = []
            
            for tf in TIMEFRAMES:
                # Yahoo ko có nến phút/giờ cho VN-INDEX
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                # Chọn nguồn để đúc
                if '15m' in tf: src = master['15m']
                elif '30m' in tf or 'h' in tf or 'H' in tf: src = master['1h']
                else: src = master['1d']
                
                if src is None: continue

                # Gộp nến
                rule_map = {'30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
                df_tf = resample_ohlc(src, rule_map[tf]) if tf in rule_map else src
                
                df_ind = calculate_indicators(df_tf)
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
                status.update(label=f"💠 {asset['name']} | Giá HT: {live_p:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
