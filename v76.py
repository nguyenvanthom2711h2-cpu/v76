import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade v149", layout="wide")

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 60: return None 
    try:
        df = df.copy()
        # Đảm bảo cột chuẩn
        col = 'Close'
        
        # MA
        df['ma10'] = df[col].rolling(10).mean()
        df['ma20'] = df[col].rolling(20).mean()
        df['ma50'] = df[col].rolling(50).mean()
        
        # RSI Wilder's
        delta = df[col].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 3. HÀM TẢI DỮ LIỆU SIÊU CẤP (CHỐNG LỖI YAHOO)
# ==========================================
def fetch_data_v149(symbol, tf):
    try:
        # Bỏ qua khung nhỏ cho VN-INDEX
        if symbol == "^VNINDEX" and any(x in tf for x in ['m', 'h', 'H']):
            return None
            
        # Xác định Interval gốc
        if tf in ['15m', '30m']: 
            f_tf, p = tf, '60d'
        elif any(x in tf for x in ['h', '2h', '4h', '8h', '12h']): 
            f_tf, p = '1h', '730d' 
        else: 
            f_tf, p = '1d', 'max'
            
        # Tải dữ liệu
        df = yf.download(symbol, period=p, interval=f_tf, progress=False, timeout=20)
        
        if df.empty: return None

        # --- QUAN TRỌNG: SAN PHẲNG TIÊU ĐỀ COLUMNS (SỬA LỖI MỚI NHẤT) ---
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Đảm bảo index là Datetime
        df.index = pd.to_datetime(df.index)

        # Logic Resampling
        rule_map = {
            '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', 
            '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'
        }
        
        if tf in rule_map and tf != f_tf:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold;'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v149</h2>", unsafe_allow_html=True)
    
    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_placeholder = st.empty()
            table_placeholder = st.empty()
            
            data_rows = []
            with st.spinner(f"Đang đồng bộ dữ liệu {asset['name']}..."):
                for tf in TIMEFRAMES:
                    df_ind = fetch_data_v149(asset['symbol'], tf)
                    
                    if df_ind is not None and len(df_ind) > 0:
                        last = df_ind.iloc[-1]
                        
                        # Kiểm tra xem có dữ liệu tính toán ko
                        if pd.isna(last['rsi45']): continue
                        
                        p_val = float(last['Close'])
                        r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                        
                        # Phân tích RSI
                        if r > r9 and r > r45: r_stat = "TĂNG"
                        elif r < r9 and r < r45: r_stat = "GIẢM"
                        elif r9 > r > r45: r_stat = "CHỈNH (-)"
                        elif r45 > r > r9: r_stat = "HỒI (+)"
                        else: r_stat = "YẾU"
                        
                        # Phân tích Xu hướng
                        wave = "TĂNG" if p_val > last['ma20'] else "GIẢM"
                        p50 = "TĂNG" if p_val > last['ma50'] else "GIẢM"
                        m1020 = "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM"

                        data_rows.append({
                            "KHUNG": tf.upper(), 
                            "SÓNG MA20": wave, 
                            "RSI 9/45": r_stat,
                            "P/MA50": p50, 
                            "MA 10/20": m1020,
                            "RSI": int(r), 
                            "GIÁ": f"{p_val:,.1f}"
                        })

            if data_rows:
                status_placeholder.success(f"✅ {asset['name']} | Cập nhật: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                # Dùng table để hiển thị ổn định
                table_placeholder.table(pd.DataFrame(data_rows).style.map(style_text))
            else:
                status_placeholder.warning(f"⚠️ {asset['name']}: Yahoo chỉ hỗ trợ từ khung Ngày (1D) trở lên.")

    # Refresh
    time.sleep(300)
    st.rerun()

if __name__ == "__main__":
    main()
