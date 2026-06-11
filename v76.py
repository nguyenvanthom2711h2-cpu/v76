import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz
import requests

# Tắt cảnh báo rác
warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

# Khởi tạo bộ nhớ Telegram (Fix lỗi NameError)
if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
# Đầy đủ 12 khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade Dashboard v140", layout="wide")

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RMA CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        # Đảm bảo cột Close phẳng
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df['ma10'] = df['Close'].rolling(10).mean()
        df['ma20'] = df['Close'].rolling(20).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA TẦNG (ANTI-BLOCK)
# ==========================================
def resample_ohlc(df, rule):
    try:
        df.index = pd.to_datetime(df.index)
        logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        return df.resample(rule).agg(logic).dropna()
    except: return df

@st.cache_data(ttl=60)
def fetch_master_data(symbol, tf):
    """Tải dữ liệu độc lập cho từng khung để tránh lặp giá và lỗi IP"""
    try:
        # Giả lập trình duyệt để Yahoo không chặn
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        if 'm' in tf and '1m' not in tf: f_tf, period = tf, '7d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']): f_tf, period = '1h', '730d'
        else: f_tf, period = '1d', 'max'
            
        df = yf.download(symbol, period=period, interval=f_tf, progress=False, timeout=20)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # Gộp nến cho các khung trung gian
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
    return 'color: #f1c40f; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Master Dashboard v140</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    bot = telebot.TeleBot(TOKEN)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                # VN-INDEX bỏ qua khung phút/giờ lẻ
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                df_ind = fetch_master_data(asset['symbol'], tf)
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    p_val = float(last['Close'])
                    if asset_price == 0: asset_price = p_val
                    
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        key = f"{asset['name']}_{prev['tf']}_{tf}"
                        if r_code == 1 and prev['code'] == 1:
                            agreement = "MUA (↑)"
                            if st.session_state.last_alerts.get(key) != "BUY":
                                try: bot.send_message(CHAT_ID, f"🚀 **ĐỒNG THUẬN MUA: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p_val:,.1f}`", parse_mode='Markdown')
                                except: pass
                                st.session_state.last_alerts[key] = "BUY"
                        elif r_code == -1 and prev['code'] == -1:
                            agreement = "BÁN (↓)"
                            if st.session_state.last_alerts.get(key) != "SELL":
                                try: bot.send_message(CHAT_ID, f"🔻 **ĐỒNG THUẬN BÁN: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p_val:,.1f}`", parse_mode='Markdown')
                                except: pass
                                st.session_state.last_alerts[key] = "SELL"
                        else: st.session_state.last_alerts[key] = "NONE"

                    sync_list.append({"tf": tf, "code": r_code})
                    def sign(v1, v2): return "TĂNG" if v1 > v2 else "GIẢM"
                    
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
                status.update(label=f"❌ {asset['name']} mất kết nối.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
