import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz
import telebot  # Dòng quan trọng đã được thêm lại ở đây

# Tắt cảnh báo rác
warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

# Khởi tạo bộ nhớ Telegram trong Session State của Streamlit
if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# Đầy đủ 12 khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Pro Trade Dashboard v141", layout="wide")

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RMA CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Đảm bảo tiêu đề cột phẳng (không Multi-index)
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        
        # SMA chuẩn
        df['ma10'] = df['Close'].rolling(window=10, min_periods=1).mean()
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        
        # RSI Wilder's (EMA alpha=1/14)
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(window=9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(window=45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA TẦNG (ANTI-BLOCK)
# ==========================================
@st.cache_data(ttl=60)
def fetch_master_data(symbol, tf):
    """Tải dữ liệu độc lập cho từng khung để tránh lặp giá và lỗi IP"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        if 'm' in tf and '1m' not in tf: 
            f_tf, period = tf, '7d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']): 
            f_tf, period = '1h', '730d'
        else: 
            f_tf, period = '1d', 'max'
            
        df = yf.download(symbol, period=period, interval=f_tf, progress=False, timeout=20)
        
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)

        # Logic gộp nến cho các khung trung gian
        rule_map = {'30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
        if tf in rule_map and tf != f_tf:
            df.index = pd.to_datetime(df.index)
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Master Dashboard v141</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    # Khởi tạo bot Telegram
    bot = telebot.TeleBot(TOKEN)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ dữ liệu {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                # Yahoo VN-Index không hỗ trợ khung nhỏ
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                df_ind = fetch_master_data(asset['symbol'], tf)
                if df_ind is not None and not df_ind.empty:
                    last = df_ind.iloc[-1]
                    p_val = float(last['Close'])
                    if asset_price == 0: asset_price = p_val
                    
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    
                    # Logic Trạng thái
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    # Xét đồng thuận gửi Telegram
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        key = f"{asset['name']}_{prev['tf']}_{tf}"
                        if r_code == 1 and prev['code'] == 1:
                            agreement = "MUA (↑)"
                            if st.session_state.last_alerts.get(key) != "BUY":
                                try:
                                    bot.send_message(CHAT_ID, f"🚀 **ĐỒNG THUẬN MUA: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p_val:,.1f}`", parse_mode='Markdown')
                                    st.session_state.last_alerts[key] = "BUY"
                                except: pass
                        elif r_code == -1 and prev['code'] == -1:
                            agreement = "BÁN (↓)"
                            if st.session_state.last_alerts.get(key) != "SELL":
                                try:
                                    bot.send_message(CHAT_ID, f"🔻 **ĐỒNG THUẬN BÁN: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p_val:,.1f}`", parse_mode='Markdown')
                                    st.session_state.last_alerts[key] = "SELL"
                                except: pass
                        else: st.session_state.last_alerts[key] = "NONE"

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
                status.update(label=f"💠 {asset['name']} | Giá HT: {asset_price:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50']))
            else:
                status.update(label=f"❌ {asset['name']} hiện đang mất kết nối dữ liệu.", state="error")

    # Tự động làm mới trang
    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
