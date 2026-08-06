import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
import os
import json
import time
import io
from pathlib import Path
import streamlit.components.v1 as components

# -------------------------------------------------------------------
# 0. THIẾT LẬP HỆ THỐNG VÀ BẢO MẬT
# -------------------------------------------------------------------
ALLOWED_DATA_DIR = Path("./Data_Server").resolve()
ALLOWED_DATA_DIR.mkdir(parents=True, exist_ok=True)

try:
    COOKIE_KEY = st.secrets["COOKIE_KEY"]
except (KeyError, FileNotFoundError):
    COOKIE_KEY = "fallback_unsafe_key_change_me_in_production"

USER_FILE = "users.json"

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if 'lines' not in data: data['lines'] = {}
            return data
    else:
        default_creds = {
            'usernames': {
                'admin': {
                    'name': 'Quản trị viên', 'password': 'admin123', 'role': 'admin',
                    'position': 'Giám Đốc', 'department': 'Ban Giám Đốc', 'line': 'Tất cả',
                    'permissions': {'view': True, 'edit_data': True, 'edit_line': True, 'edit_account': True}
                }
            },
            'lines': {}
        }
        stauth.Hasher.hash_passwords(default_creds)
        with open(USER_FILE, "w", encoding="utf-8") as f:
            json.dump(default_creds, f, ensure_ascii=False, indent=4)
        return default_creds

def save_users(creds):
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(creds, f, ensure_ascii=False, indent=4)

# -------------------------------------------------------------------
# 1. GIAO DIỆN ĐĂNG NHẬP & CSS TÙY CHỈNH
# -------------------------------------------------------------------
st.set_page_config(page_title="Dashboard OEE Toàn Diện", layout="wide", page_icon="🏭")

# Tiêm CSS tùy chỉnh để làm nổi bật nút Về Trang Chủ và các ô KPI
st.markdown("""
    <style>
    /* Làm nổi bật nút Về trang chủ Dashboard */
    .home-btn-container a {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
        color: white !important;
        padding: 10px 20px !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        text-align: center !important;
        display: block !important;
        text-decoration: none !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: 0.3s;
    }
    .home-btn-container a:hover {
        background: linear-gradient(135deg, #d97706 0%, #b45309 100%) !important;
        box-shadow: 0 6px 8px rgba(0,0,0,0.15);
    }
    </style>
""", unsafe_allow_html=True)

credentials = load_users()
authenticator = stauth.Authenticate(
    credentials, 'mes_secure_cookie', COOKIE_KEY, cookie_expiry_days=1
)

authenticator.login(location='main')

authentication_status = st.session_state.get('authentication_status')
name = st.session_state.get('name')
username = st.session_state.get('username')

if authentication_status == False:
    st.error('⛔ Tài khoản hoặc mật khẩu không chính xác!')
elif authentication_status == None:
    st.warning('🔐 Vui lòng nhập thông tin tài khoản để truy cập hệ thống MES.')
elif authentication_status:
    authenticator.logout('Đăng xuất', 'sidebar')
    
    current_user_info = credentials['usernames'].get(username, {})
    current_position = current_user_info.get('position', 'Nhân viên')
    current_department = current_user_info.get('department', 'Chưa rõ')
    current_line = current_user_info.get('line', 'Chưa rõ')
    
    # THANH SIDEBAR TÙY CHỈNH NÚT VỀ TRANG CHỦ
    with st.sidebar:
        st.markdown("### 📌 ĐIỀU HƯỚNG HỆ THỐNG")
        st.markdown('<div class="home-btn-container"><a href="#">🏠 VỀ TRANG CHỦ DASHBOARD</a></div>', unsafe_allow_html=True)
        st.markdown("---")

    st.title(f"🏭 Dashboard OEE Toàn Diện & Quản Trị")
    st.caption(f"👤 Tên: **{name}** | Vị trí: **{current_position}** | Phòng ban: **{current_department}** | Phụ trách: **{current_line}**")
    st.markdown("---")

    df = None 
    if os.path.exists("data_server.csv"):
        try:
            df = pd.read_csv("data_server.csv")
        except Exception:
            df = None

    approved_lines = [lname for lname, linfo in credentials.get('lines', {}).items() if linfo.get('status') == 'Đã phê duyệt']
    line_options = ["Chưa cập nhật", "Tất cả"] + approved_lines

    user_role = current_user_info.get('role', 'user')
    user_perms = current_user_info.get('permissions', {})
    
    can_view = user_perms.get('view', True)
    can_edit_data = user_perms.get('edit_data', False) or user_role == 'admin'
    can_edit_account = user_perms.get('edit_account', False) or user_role == 'admin'
    can_edit_line = user_perms.get('edit_line', False) or user_role == 'admin'

    menu_options = []
    if can_view: menu_options.extend(["🎛️ Dashboard OEE", "📊 Báo Cáo Downtime (HTML)", "🔍 Tra cứu & Dữ liệu"])
    if can_edit_line: menu_options.append("🏭 Quản Lý Máy Móc")
    if can_edit_account: menu_options.append("👤 Quản Lý Tài Khoản")
    if can_edit_data: menu_options.append("📂 Cập nhật File")
        
    if menu_options:
        if "admin_menu" not in st.session_state or st.session_state.admin_menu not in menu_options:
            st.session_state.admin_menu = menu_options[0]

        selected_tab = st.radio("Điều hướng:", menu_options, horizontal=True, key="admin_menu", label_visibility="collapsed")
        st.markdown("---")
        
        # ---------------------------------------------------------
        # TAB 1: DASHBOARD OEE (CÓ MÀU NỀN CHO 4 Ô CHỈ SỐ)
        # ---------------------------------------------------------
        if selected_tab == "🎛️ Dashboard OEE":
            st.subheader("🎛️ Dashboard OEE & Sản Xuất Tổng Quan")
            if df is None or df.empty:
                st.info("💡 Chưa có dữ liệu. Vui lòng vào tab '📂 Cập nhật File' để tải lên file dữ liệu.")
            else:
                total_records = len(df)
                status_col = next((col for col in df.columns if any(kw in str(col).lower() for kw in ["status", "kết quả", "trạng thái", "result"])), None)
                ng_count = len(df[df[status_col].astype(str).str.upper().isin(["NG", "FAIL", "LỖI", "REJECT"])]) if status_col else 0
                ok_count = total_records - ng_count
                ng_rate = round((ng_count / total_records) * 100, 2) if total_records > 0 else 0

                # Thêm màu nền nổi bật cho 4 ô chỉ số (KPI Cards)
                st.markdown("""
                    <style>
                    .kpi-card-1 { background-color: #eff6ff; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 6px; }
                    .kpi-card-2 { background-color: #f0fdf4; border-left: 5px solid #22c55e; padding: 15px; border-radius: 6px; }
                    .kpi-card-3 { background-color: #fef2f2; border-left: 5px solid #ef4444; padding: 15px; border-radius: 6px; }
                    .kpi-card-4 { background-color: #fefce8; border-left: 5px solid #eab308; padding: 15px; border-radius: 6px; }
                    </style>
                """, unsafe_allow_html=True)

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f'<div class="kpi-card-1"><span style="color: #1e3a8a; font-size: 13px; font-weight: bold;">📦 Tổng Sản Lượng</span><h2 style="color: #1d4ed8; margin: 5px 0 0 0;">{total_records:,} SP</h2></div>', unsafe_allow_html=True)
                with c2:
                    st.markdown(f'<div class="kpi-card-2"><span style="color: #14532d; font-size: 13px; font-weight: bold;">✅ Hàng OK</span><h2 style="color: #15803d; margin: 5px 0 0 0;">{ok_count:,} SP</h2></div>', unsafe_allow_html=True)
                with c3:
                    st.markdown(f'<div class="kpi-card-3"><span style="color: #7f1d1d; font-size: 13px; font-weight: bold;">❌ Hàng NG</span><h2 style="color: #b91c1c; margin: 5px 0 0 0;">{ng_count:,} SP</h2></div>', unsafe_allow_html=True)
                with c4:
                    st.markdown(f'<div class="kpi-card-4"><span style="color: #713f12; font-size: 13px; font-weight: bold;">📉 Tỉ Lệ Lỗi</span><h2 style="color: #a16207; margin: 5px 0 0 0;">{ng_rate}%</h2></div>', unsafe_allow_html=True)
                
                st.markdown("---")
                st.dataframe(df.tail(100).iloc[::-1], use_container_width=True, height=400)

        # ---------------------------------------------------------
        # TAB 2: BÁO CÁO DOWNTIME (HTML)
        # ---------------------------------------------------------
        elif selected_tab == "📊 Báo Cáo Downtime (HTML)":
            st.subheader("📊 Giao Diện Phân Tích Downtime & Sức Khỏe Thiết Bị")
            html_path = Path("dashboard.html")
            if html_path.exists():
                components.html(html_path.read_text(encoding="utf-8"), height=950, scrolling=True)
            else:
                st.warning("⚠️ Chưa tìm thấy file `dashboard.html`. Đang hiển thị giao diện mẫu:")
                embedded_html = """
                <div style="background: #f8fafc; padding: 20px; font-family: sans-serif; border-radius: 8px;">
                    <div style="background: #b91c1c; color: white; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                        <h3 style="margin: 0 0 5px 0; font-size: 14px;">🚨 CẦN LÀM GÌ TRONG PHẠM VI ĐANG XEM</h3>
                        <p style="margin: 0; font-size: 13px;">Chưa xác định downtime lớn nhất (2.650 phút) -> Ưu tiên xử lý 5-Why ngay tại trạm.</p>
                    </div>
                </div>
                """
                components.html(embedded_html, height=250, scrolling=False)

        # ---------------------------------------------------------
        # TAB 3: TRA CỨU & DỮ LIỆU
        # ---------------------------------------------------------
        elif selected_tab == "🔍 Tra cứu & Dữ liệu":
            st.subheader("🔍 Tra Cứu Dữ Liệu Chi Tiết")
            if df is None: df = pd.DataFrame(columns=["Chưa có dữ liệu"])
            kw = st.text_input("🔎 Tìm kiếm từ khóa bất kỳ:")
            if kw:
                df_res = df[df.astype(str).apply(lambda r: r.str.contains(kw, case=False, na=False)).any(axis=1)]
                st.dataframe(df_res, use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)

        # ---------------------------------------------------------
        # TAB 4: QUẢN LÝ MÁY MÓC (ĐÃ BỎ UPH)
        # ---------------------------------------------------------
        elif selected_tab == "🏭 Quản Lý Máy Móc":
            st.subheader("🏭 Thiết Lập Thiết Bị & Máy Móc")
            with st.form("new_l", clear_on_submit=True):
                n_ln = st.text_input("Tên LINE mới*:")
                if st.form_submit_button("Tạo LINE mới"):
                    if n_ln: 
                        credentials['lines'][n_ln] = {'status': 'Đã phê duyệt', 'machines': {}}
                        save_users(credentials)
                        st.success("✅ Đã tạo LINE mới!")
                        time.sleep(1)
                        st.rerun()
            
            for ln, li in credentials.get('lines', {}).items():
                with st.expander(f"🏭 {ln}"):
                    df_m = pd.DataFrame([{"Mã Máy": m, "Tên": i.get('name'), "Đường dẫn Path": i.get('path')} for m, i in li.get('machines', {}).items()])
                    if not df_m.empty: st.dataframe(df_m, hide_index=True)
                    
                    with st.form(f"add_{ln}"):
                        c1, c2 = st.columns(2)
                        with c1: 
                            mn = st.text_input("Mã Máy*")
                            mt = st.text_input("Tên Máy*")
                        with c2: 
                            mf = st.selectbox("Định dạng:", ["CSV", "Excel", "XLSB"])
                            mp = st.text_input("Path:", value=f"{ALLOWED_DATA_DIR}/...")
                        
                        # Đã loại bỏ hoàn toàn trường UPH theo yêu cầu
                        if st.form_submit_button("Lưu Máy Móc"):
                            if mn and mt:
                                if 'machines' not in credentials['lines'][ln]: credentials['lines'][ln]['machines'] = {}
                                credentials['lines'][ln]['machines'][mn] = {'name': mt, 'format': mf, 'path': mp, 'active': True}
                                save_users(credentials)
                                st.success("✅ Đã lưu thiết bị thành công!")
                                time.sleep(1)
                                st.rerun()

        # ---------------------------------------------------------
        # TAB 5: QUẢN LÝ TÀI KHOẢN
        # ---------------------------------------------------------
        elif selected_tab == "👤 Quản Lý Tài Khoản":
            st.subheader("👥 Quản Lý Danh Sách Tài Khoản Hệ Thống")
            u_list = [{"Username": k, "Tên": v.get('name'), "Chức vụ": v.get('position'), "Phòng ban": v.get('department')} for k, v in credentials['usernames'].items()]
            st.table(pd.DataFrame(u_list))

            with st.expander("➕ Tạo Mới Tài Khoản"):
                with st.form("new_u"):
                    c1, c2 = st.columns(2)
                    with c1: nu = st.text_input("Username*"); nn = st.text_input("Tên nhân sự*")
                    with c2: np = st.text_input("Mật khẩu*", type="password"); nl = st.selectbox("Line phụ trách:", line_options)
                    p_admin = st.checkbox("Quyền Quản Trị Viên (Admin)", value=False)
                    if st.form_submit_button("Tạo Tài Khoản"):
                        if nu and np and nn:
                            if nu in credentials['usernames']: st.error("Tài khoản đã tồn tại!")
                            else:
                                h = {'u': {nu: {'password': np}}}; stauth.Hasher.hash_passwords(h)
                                credentials['usernames'][nu] = {'name': nn, 'password': h['u'][nu]['password'], 'line': nl, 'role': 'admin' if p_admin else 'user', 'permissions': {'view': True, 'edit_data': p_admin, 'edit_line': p_admin, 'edit_account': p_admin}}
                                save_users(credentials)
                                st.success("✅ Tạo tài khoản thành công!")
                                time.sleep(1)
                                st.rerun()

        # ---------------------------------------------------------
        # TAB 6: CẬP NHẬT FILE
        # ---------------------------------------------------------
        elif selected_tab == "📂 Cập nhật File":
            st.subheader("📂 Tải Lên Dữ Liệu Máy & Hệ Thống")
            upf = st.file_uploader("📂 Chọn file (Excel/CSV/XLSB)", type=["xlsx", "xls", "xlsb", "csv"])
            if upf:
                if upf.name.endswith('.csv'): df = pd.read_csv(upf)
                elif upf.name.endswith('.xlsb'): df = pd.read_excel(upf, engine='pyxlsb')
                else: df = pd.read_excel(upf)
                df.to_csv("data_server.csv", index=False)
                st.success("✅ Đã ghi đè dữ liệu thành công! Hãy chuyển tab để xem kết quả.")
