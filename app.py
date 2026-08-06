import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date
import calendar
import hashlib
import secrets
import time
import re

# ==========================================
# CẤU HÌNH TRANG
# ==========================================
st.set_page_config(page_title="Dashboard OEE Toàn Diện (Secured)", layout="wide", initial_sidebar_state="expanded")

ALL_FEATURES = [
    "🎛️ Dashboard OEE",
    "🏭 Quản Lý Máy Móc",
    "👤 Quản Lý Tài Khoản"
]

ALL_MACHINE_EDIT_FIELDS = [
    "Tên máy",
    "Dây chuyền (Line)",
    "Đường dẫn máy",
    "File mẫu dữ liệu"
]

# THÔNG SỐ BẢO MẬT
SESSION_TIMEOUT = 1800 # 30 phút
MAX_LOGIN_ATTEMPTS = 5 # Số lần thử tối đa
LOCKOUT_DURATION = 300 # Khóa 5 phút (300 giây)

# ==========================================
# CÁC HÀM BẢO MẬT & MÃ HÓA NÂNG CAO
# ==========================================
def hash_password(password, salt=None):
    """Mã hóa mật khẩu sử dụng PBKDF2 HMAC SHA256 kết hợp ngẫu nhiên Salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return salt + ":" + key.hex()

def verify_password(password, hashed_pass):
    """Kiểm tra mật khẩu nhập vào so với mã băm đã lưu."""
    try:
        salt, _ = hashed_pass.split(':')
        return hash_password(password, salt) == hashed_pass
    except Exception:
        return False

def validate_username(username):
    """Kiểm tra tên đăng nhập chỉ chứa chữ cái và số, không khoảng trắng."""
    return bool(re.match(r"^[a-zA-Z0-9_]{3,20}$", username))

def validate_password_strength(password):
    """Kiểm tra độ mạnh của mật khẩu."""
    if len(password) < 8:
        return False, "Mật khẩu phải có ít nhất 8 ký tự!"
    if not re.search(r"[A-Z]", password):
        return False, "Mật khẩu phải chứa ít nhất 1 chữ hoa!"
    if not re.search(r"[a-z]", password):
        return False, "Mật khẩu phải chứa ít nhất 1 chữ thường!"
    if not re.search(r"\d", password):
        return False, "Mật khẩu phải chứa ít nhất 1 chữ số!"
    if not re.search(r"[@$!%*?&#]", password):
        return False, "Mật khẩu phải chứa ít nhất 1 ký tự đặc biệt (@, $, !, %, *, ?, &, #)!"
    return True, "Hợp lệ"

def log_security_event(username, event_type, status):
    """Ghi log các sự kiện bảo mật."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["AUDIT_LOGS"].insert(0, f"[{timestamp}] User: {username} | Event: {event_type} | Status: {status}")
    if len(st.session_state["AUDIT_LOGS"]) > 100: # Lưu tối đa 100 log gần nhất
        st.session_state["AUDIT_LOGS"].pop()

# ==========================================
# CSS GIAO DIỆN
# ==========================================
st.markdown("""
    <style>
    @keyframes pulse-btn {
        0% { transform: scale(1); box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4); }
        50% { transform: scale(1.02); box-shadow: 0 8px 20px rgba(245, 158, 11, 0.8); }
        100% { transform: scale(1); box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4); }
    }
    div[key="btn_home_nav"] > button {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
        color: #ffffff !important; border: none !important; font-weight: 800 !important;
        font-size: 16px !important; border-radius: 10px !important; height: 48px !important;
        animation: pulse-btn 2s infinite !important; transition: all 0.3s ease !important;
        margin-bottom: 20px !important; border: 2px solid #fcd34d !important;
    }
    div[key="btn_home_nav"] > button:hover {
        background: linear-gradient(135deg, #d97706 0%, #b45309 100%) !important;
        animation: none !important; transform: translateY(-2px);
    }
    .login-header-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border: 1px solid #334155;
        border-radius: 16px; padding: 30px; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); margin-bottom: 25px;
    }
    .login-title { color: #38bdf8; font-size: 2.2rem; font-weight: 800; margin-bottom: 8px; letter-spacing: 0.5px; }
    .login-subtitle { color: #94a3b8; font-size: 1rem; margin-bottom: 0; }
    .kpi-card-1 { background-color: #eff6ff; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 6px; }
    .kpi-card-2 { background-color: #f0fdf4; border-left: 5px solid #22c55e; padding: 15px; border-radius: 6px; }
    .kpi-card-3 { background-color: #fef2f2; border-left: 5px solid #ef4444; padding: 15px; border-radius: 6px; }
    .kpi-card-4 { background-color: #fefce8; border-left: 5px solid #eab308; padding: 15px; border-radius: 6px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# HÀM HỖ TRỢ HIỂN THỊ DIALOG/MODAL
# ==========================================
@st.dialog("🔔 THÔNG BÁO HỆ THỐNG")
def show_popup_message(title, message, icon="ℹ️"):
    st.markdown(f"### {icon} {title}")
    st.write(message)
    if st.button("Đóng", use_container_width=True, type="primary"):
        st.rerun()

# ==========================================
# HÀM HỖ TRỢ XỬ LÝ DỮ LIỆU MÔ PHỎNG
# ==========================================
def generate_mock_machine_data(machine_obj, start_date, end_date):
    date_range = pd.date_range(start=start_date, end=end_date)
    data = []
    seed_val = sum(ord(c) for c in machine_obj["id"]) + int(start_date.strftime("%d%m%Y"))
    np.random.seed(seed_val)
    for d in date_range:
        availability = np.random.uniform(80, 98)
        performance = np.random.uniform(85, 99)
        quality = np.random.uniform(95, 99.9)
        oee = (availability * performance * quality) / 10000
        downtime = round(np.random.uniform(10, 120), 1)
        data.append({
            "Ngày": d.strftime("%Y-%m-%d"), "Mã máy": machine_obj["id"], "Tên máy": machine_obj["name"],
            "Dây chuyền": machine_obj["line"], "Sẵn sàng (%)": round(availability, 1),
            "Hiệu suất (%)": round(performance, 1), "Chất lượng (%)": round(quality, 1),
            "OEE (%)": round(oee, 1), "Downtime (Phút)": downtime
        })
    return pd.DataFrame(data)

def generate_mock_pareto_4m_data(machine_ids, start_date, end_date):
    seed_val = sum(ord(c) for m in machine_ids for c in m) + int(start_date.strftime("%d%m%Y"))
    np.random.seed(seed_val)
    stations = ["Block 1", "Block 2", "Block 3", "Block 4", "Block 5", "Block 6", "Chưa xác định"]
    downtimes = np.random.randint(200, 3000, size=len(stations))
    df_pareto = pd.DataFrame({"Trạm": stations, "So_Phut": downtimes})
    df_pareto = df_pareto.sort_values(by="So_Phut", ascending=False).reset_index(drop=True)
    tong_thoi_gian = df_pareto["So_Phut"].sum()
    df_pareto["Phan_Tram_Tich_Luy"] = (df_pareto["So_Phut"].cumsum() / tong_thoi_gian) * 100
    
    m_machine = int(np.random.uniform(500, 2000))
    m_material = int(np.random.uniform(300, 1500))
    m_method = int(np.random.uniform(100, 800))
    m_unclassified = int(np.random.uniform(100, 600))
    
    data_4m = {
        "labels": ['Máy móc (Machine)', 'Nguyên liệu (Material)', 'Phương pháp (Method)', 'Chưa phân loại'],
        "values": [m_machine, m_material, m_method, m_unclassified]
    }
    return df_pareto, data_4m

# ==========================================
# KHỞI TẠO CƠ SỞ DỮ LIỆU & BẢO MẬT
# ==========================================
if "LOGIN_ATTEMPTS" not in st.session_state:
    st.session_state["LOGIN_ATTEMPTS"] = {} # Theo dõi số lần đăng nhập sai
if "AUDIT_LOGS" not in st.session_state:
    st.session_state["AUDIT_LOGS"] = [] # Theo dõi lịch sử

if "USER_DB" not in st.session_state:
    # Mật khẩu mặc định: Admin@123 và Manager@123
    st.session_state["USER_DB"] = {
        "admin": {
            "password_hash": hash_password("Admin@123"), 
            "name": "Giám Đốc Nhà Máy", "department": "Ban Giám Đốc",
            "position": "Giám Đốc", "role": "Admin",
            "allowed_pages": ALL_FEATURES,
            "machine_perms": ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"],
            "editable_machine_fields": ALL_MACHINE_EDIT_FIELDS
        },
        "manager": {
            "password_hash": hash_password("Manager@123"),
            "name": "Kỹ Sư IE", "department": "Kỹ Thuật (IE)",
            "position": "Trưởng Nhóm IE", "role": "Manager",
            "allowed_pages": ["🎛️ Dashboard OEE", "🏭 Quản Lý Máy Móc"],
            "machine_perms": ["Xem", "Chỉnh sửa"],
            "editable_machine_fields": ["Đường dẫn máy"]
        }
    }

if "MACHINE_DB" not in st.session_state:
    st.session_state["MACHINE_DB"] = [
        {"id": "M01", "name": "Máy dập Block 1", "line": "G103", "url": "http://192.168.1.100/m01", "template_file": "template_oee_g103.xlsx", "has_file": True},
        {"id": "M02", "name": "Máy Test Hipot", "line": "G104", "url": "http://192.168.1.101/m02", "template_file": "template_oee_g104.csv", "has_file": True}
    ]

if "selected_menu" not in st.session_state:
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
if "input_user" not in st.session_state:
    st.session_state["input_user"] = ""
if "input_pass" not in st.session_state:
    st.session_state["input_pass"] = ""

# ==========================================
# CÁC HÀM ĐĂNG NHẬP / ĐĂNG XUẤT / CHUYỂN TRANG
# ==========================================
def login():
    _, col_center, _ = st.columns([1, 2.2, 1])
    
    with col_center:
        st.markdown("""
            <div class="login-header-card">
                <div style="font-size: 3rem; margin-bottom: 10px;">🏭</div>
                <div class="login-title">OEE MANAGEMENT SYSTEM</div>
                <div class="login-subtitle">Hệ Thống Giám Sát & Quản Lý Hiệu Suất Thiết Bị Smart Factory</div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("### 🔐 Đăng Nhập Hệ Thống")
            st.caption("Vui lòng nhập tài khoản và mật khẩu của bạn để truy cập.")
            
            with st.form("login_form"):
                username = st.text_input("👤 Tên đăng nhập", value=st.session_state["input_user"], placeholder="Nhập tên đăng nhập")
                password = st.text_input("🔑 Mật khẩu", value=st.session_state["input_pass"], type="password", placeholder="Nhập mật khẩu")
                
                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    submit_button = st.form_submit_button("🚀 Đăng nhập", use_container_width=True, type="primary")
                with col_btn2:
                    clear_button = st.form_submit_button("🔄 Xóa nhập", use_container_width=True)
                
                if submit_button:
                    username_cleaned = username.strip().lower()
                    
                    # 🛡️ KIỂM TRA TÌNH TRẠNG KHÓA TÀI KHOẢN (BRUTE-FORCE PREVENTION)
                    attempts_info = st.session_state["LOGIN_ATTEMPTS"].get(username_cleaned, {"count": 0, "lockout_until": 0})
                    if time.time() < attempts_info["lockout_until"]:
                        remaining_time = int(attempts_info["lockout_until"] - time.time())
                        st.error(f"❌ Tài khoản đang bị khóa do nhập sai nhiều lần. Thử lại sau {remaining_time} giây!")
                        log_security_event(username_cleaned, "LOGIN_BLOCKED", "Thất bại (Locked)")
                    else:
                        if username_cleaned in st.session_state["USER_DB"]:
                            stored_hash = st.session_state["USER_DB"][username_cleaned]["password_hash"]
                            if verify_password(password, stored_hash):
                                # Reset số lần thử nếu thành công
                                st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = {"count": 0, "lockout_until": 0}
                                
                                st.session_state["logged_in"] = True
                                st.session_state["username"] = username_cleaned
                                st.session_state["user_info"] = st.session_state["USER_DB"][username_cleaned]
                                st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
                                st.session_state["menu_radio"] = "🎛️ Dashboard OEE"
                                st.session_state["last_activity"] = time.time() 
                                log_security_event(username_cleaned, "LOGIN", "Thành công")
                                st.toast("🔔 Đăng nhập thành công!", icon="✅")
                                st.rerun()
                            else:
                                # Tăng số lần thử
                                attempts_info["count"] += 1
                                if attempts_info["count"] >= MAX_LOGIN_ATTEMPTS:
                                    attempts_info["lockout_until"] = time.time() + LOCKOUT_DURATION
                                    st.error(f"❌ Bạn đã nhập sai {MAX_LOGIN_ATTEMPTS} lần. Tài khoản bị khóa 5 phút để bảo vệ!")
                                    log_security_event(username_cleaned, "BRUTE_FORCE_DETECTED", "Thất bại (Khóa tài khoản)")
                                else:
                                    st.error(f"❌ Mật khẩu không chính xác! (Còn {MAX_LOGIN_ATTEMPTS - attempts_info['count']} lần thử)")
                                    log_security_event(username_cleaned, "LOGIN_FAILED", "Thất bại (Sai mật khẩu)")
                                st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = attempts_info
                        else:
                            st.error("❌ Tài khoản không tồn tại trong hệ thống!")
                            log_security_event(username_cleaned, "LOGIN_FAILED", "Thất bại (User không tồn tại)")
                
                if clear_button:
                    st.session_state["input_user"] = ""
                    st.session_state["input_pass"] = ""
                    st.rerun()

        st.markdown("<p style='text-align: center; color: #64748b; font-size: 0.85rem; margin-top: 30px;'>© 2026 Smart Factory Management System | Version 3.1.0 (Enterprise Secured)</p>", unsafe_allow_html=True)

def logout(reason=""):
    log_security_event(st.session_state.get("username", "Unknown"), "LOGOUT", "Thành công")
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("user_info", None)
    st.session_state.pop("last_activity", None)
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
    if reason:
        st.warning(reason)

def go_home():
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
    st.session_state["menu_radio"] = "🎛️ Dashboard OEE"

# ==========================================
# GIAO DIỆN CHÍNH KHI ĐÃ ĐĂNG NHẬP
# ==========================================
if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
else:
    # 🔒 KIỂM TRA SESSION TIMEOUT
    current_time = time.time()
    last_activity = st.session_state.get("last_activity", 0)
    
    if (current_time - last_activity) > SESSION_TIMEOUT:
        logout("⏳ Phiên đăng nhập đã hết hạn do không hoạt động để bảo mật dữ liệu. Vui lòng đăng nhập lại!")
        st.rerun()
    else:
        st.session_state["last_activity"] = current_time 

    current_user = st.session_state["user_info"]
    
    # --- SIDEBAR MENU ---
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3652/3652191.png", width=95)
        st.success(f"👋 **{current_user['name']}**")
        st.info(f"📍 Bộ phận: **{current_user.get('department', 'N/A')}**\n\n💼 Chức vụ: **{current_user.get('position', 'N/A')}**\n\n🔑 Quyền: **{current_user.get('role', 'N/A')}**")
        st.markdown("---")
        
        user_pages = current_user.get("allowed_pages", ["🎛️ Dashboard OEE"])
        if "🎛️ Dashboard OEE" in user_pages:
            user_pages.remove("🎛️ Dashboard OEE")
            user_pages.insert(0, "🎛️ Dashboard OEE")

        if st.session_state["selected_menu"] not in user_pages:
            st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
            st.session_state["menu_radio"] = "🎛️ Dashboard OEE"

        selected_menu = st.radio("📌 ĐIỀU HƯỚNG HỆ THỐNG", user_pages, key="menu_radio")
        
        if selected_menu != st.session_state["selected_menu"]:
            st.session_state["selected_menu"] = selected_menu
            st.rerun()

        st.markdown("---")
        st.button("🚪 Đăng xuất an toàn", on_click=lambda: logout(), use_container_width=True)

    # ---------------------------------------------------------
    # TRANG CHỦ: DASHBOARD OEE
    # ---------------------------------------------------------
    if selected_menu == "🎛️ Dashboard OEE":
        st.markdown("""
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 22px; border-radius: 12px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 25px; border: 1px solid #334155;">
                <h1 style="margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: 1px; color: #38bdf8; text-transform: uppercase;">
                    🎛️ MANAGEMENT DASHBOARD V2 ACTIONABLE
                </h1>
            </div>
        """, unsafe_allow_html=True)

        st.subheader("🔍 Bộ Lọc Tìm Kiếm & Phân Tích Dữ Liệu")
        machine_db = st.session_state["MACHINE_DB"]
        existing_lines = sorted(list(set([m["line"] for m in machine_db if m.get("line")])))
        line_options = ["Tất cả Lines"] + existing_lines
        machine_options = ["Tất cả Máy"] + [f"{m['id']} - {m['name']} (Line: {m['line']})" for m in machine_db]

        filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([2.5, 2.5, 2.5, 2.5, 2])
        with filter_col1:
            start_date = st.date_input("Từ ngày", date(2026, 8, 1))
        with filter_col2:
            end_date = st.date_input("Đến ngày", date.today())
        with filter_col3:
            selected_line = st.selectbox("Dây Chuyền (Line)", line_options)
        with filter_col4:
            selected_machine_str = st.selectbox("Mã / Tên Thiết Bị", machine_options)
        with filter_col5:
            st.write("")
            st.write("")
            btn_search = st.button("🔎 Phân tích", use_container_width=True, type="primary")

        filtered_machines = machine_db.copy()
        if selected_line != "Tất cả Lines":
            filtered_machines = [m for m in filtered_machines if m["line"] == selected_line]
        if selected_machine_str != "Tất cả Máy":
            selected_m_id = selected_machine_str.split(" - ")[0]
            filtered_machines = [m for m in filtered_machines if m["id"] == selected_m_id]

        target_display_name = selected_machine_str if selected_machine_str != "Tất cả Máy" else (selected_line if selected_line != "Tất cả Lines" else "Toàn Nhà Máy")

        if btn_search:
            show_popup_message("CẬP NHẬT DỮ LIỆU", f"Đã tải thành công dữ liệu phân tích cho: **{target_display_name}**!", icon="📊")
        st.markdown("---")

        all_df_list = []
        for m_item in filtered_machines:
            df_m = generate_mock_machine_data(m_item, start_date, end_date)
            all_df_list.append(df_m)

        if all_df_list:
            df_filtered = pd.concat(all_df_list, ignore_index=True)
            avg_avail = df_filtered["Sẵn sàng (%)"].mean()
            downtime_rate = round(100 - avg_avail, 1)
            total_downtime = df_filtered["Downtime (Phút)"].sum()
            avg_mtbf = int(df_filtered["Downtime (Phút)"].mean() * 2) if avg_avail > 0 else 0
            avg_mttr = round(total_downtime / max(len(df_filtered), 1), 1)

            st.markdown(f"### ⚙️ 01. Equipment Health Overview <span style='font-size: 1rem; font-weight: normal; color: #64748b;'>({target_display_name} | {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')})</span>", unsafe_allow_html=True)

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            with kpi1:
                st.markdown(f'''<div class="kpi-card-1"><span style="color: #1e3a8a; font-size: 13px; font-weight: bold;">Downtime Rate</span><h2 style="color: #1d4ed8; margin: 5px 0 0 0;">{downtime_rate}%</h2></div>''', unsafe_allow_html=True)
            with kpi2:
                st.markdown(f'''<div class="kpi-card-2"><span style="color: #14532d; font-size: 13px; font-weight: bold;">Availability (Sẵn sàng)</span><h2 style="color: #15803d; margin: 5px 0 0 0;">{round(avg_avail, 1)}%</h2></div>''', unsafe_allow_html=True)
            with kpi3:
                st.markdown(f'''<div class="kpi-card-3"><span style="color: #7f1d1d; font-size: 13px; font-weight: bold;">MTBF (Chạy TB trước khi hỏng)</span><h2 style="color: #b91c1c; margin: 5px 0 0 0;">{avg_mtbf} Phút</h2></div>''', unsafe_allow_html=True)
            with kpi4:
                st.markdown(f'''<div class="kpi-card-4"><span style="color: #713f12; font-size: 13px; font-weight: bold;">MTTR (Thời gian sửa TB)</span><h2 style="color: #a16207; margin: 5px 0 0 0;">{avg_mttr} Phút</h2></div>''', unsafe_allow_html=True)
            st.markdown("---")

            if str(current_user.get("role", "")).lower() in ["manager", "admin"]:
                st.markdown(f"### 📊 02. Pareto Downtime (80/20) & Phân loại Nguyên nhân 4M <span style='font-size: 1rem; font-weight: normal; color: #64748b;'>({target_display_name})</span>", unsafe_allow_html=True)
                selected_ids = [m["id"] for m in filtered_machines]
                df_pareto, data_4m = generate_mock_pareto_4m_data(selected_ids, start_date, end_date)
                pareto_col, pie_col = st.columns([6, 4])
                
                with pareto_col:
                    fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_pareto.add_trace(go.Bar(x=df_pareto["Trạm"], y=df_pareto["So_Phut"], name="Downtime (Phút)", marker_color="#e11d48"), secondary_y=False)
                    fig_pareto.add_trace(go.Scatter(x=df_pareto["Trạm"], y=df_pareto["Phan_Tram_Tich_Luy"], name="% Luỹ kế", mode="lines+markers+text", text=df_pareto["Phan_Tram_Tich_Luy"].round(0).astype(str) + "%", textposition="top left", marker=dict(color="#0f766e", size=8), line=dict(width=3)), secondary_y=True)
                    fig_pareto.update_layout(hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_pareto, use_container_width=True)
                    with st.expander("🖱️ Click để xem Bảng Dữ Liệu Pareto chi tiết"):
                        df_pareto_display = df_pareto.rename(columns={"Trạm": "Tên Trạm/Block", "So_Phut": "Tổng lỗi (Phút)", "Phan_Tram_Tich_Luy": "% Tích lũy"})
                        st.dataframe(df_pareto_display.style.format({"% Tích lũy": "{:.1f}%"}), use_container_width=True)

                with pie_col:
                    colors = ['#dc2626', '#ea580c', '#2563eb', '#94a3b8']
                    fig_pie = go.Figure(data=[go.Pie(labels=data_4m["labels"], values=data_4m["values"], hole=.4, marker=dict(colors=colors))])
                    fig_pie.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5))
                    st.plotly_chart(fig_pie, use_container_width=True)
                    with st.expander("🖱️ Click để xem Bảng Phân Tích 4M chi tiết"):
                        df_4m = pd.DataFrame(data_4m).rename(columns={"labels": "Nguyên nhân 4M", "values": "Số phút dừng máy"})
                        df_4m["Tỷ lệ (%)"] = (df_4m["Số phút dừng máy"] / df_4m["Số phút dừng máy"].sum() * 100)
                        st.dataframe(df_4m.style.format({"Tỷ lệ (%)": "{:.1f}%"}), use_container_width=True)
            else:
                st.info("🔒 **Hạn chế truy cập:** Bạn đang đăng nhập với quyền Operator. Chỉ xem được thông số tổng quan.")

            st.markdown("---")
            st.markdown(f"### 📈 03. Phân Tích Xu Hướng Dữ Liệu Tự Động Từng Máy ({target_display_name})")
            col_chart, col_table = st.columns([6, 4])
            with col_chart:
                fig_line = go.Figure()
                for m_item in filtered_machines:
                    df_sub = df_filtered[df_filtered["Mã máy"] == m_item["id"]]
                    fig_line.add_trace(go.Scatter(x=df_sub["Ngày"], y=df_sub["OEE (%)"], mode='lines+markers', name=f"{m_item['id']} - {m_item['name']}"))
                fig_line.update_layout(title="Xu hướng Chỉ số OEE (%) Theo Ngày Được Lọc", xaxis_title="Ngày", yaxis_title="OEE (%)", hovermode="x unified")
                st.plotly_chart(fig_line, use_container_width=True)
            with col_table:
                st.markdown("**📋 Bảng tổng hợp chi tiết dữ liệu máy được chọn:**")
                with st.expander("🖱️ Click mở rộng Bảng Dữ Liệu Chi Tiết", expanded=True):
                    st.dataframe(df_filtered[["Ngày", "Mã máy", "Tên máy", "Dây chuyền", "OEE (%)", "Downtime (Phút)"]], use_container_width=True, height=320)
            
            st.markdown("---")
            current_month = start_date.month
            current_year = start_date.year
            _, last_day = calendar.monthrange(current_year, current_month)
            month_start = date(current_year, current_month, 1)
            month_end = date(current_year, current_month, last_day)

            st.markdown(f"### 🗓️ 04. Biểu Đồ & Bảng Tổng Hợp Xu Hướng Cả Tháng {current_month}/{current_year}")
            month_df_list = []
            for m_item in filtered_machines:
                month_df_list.append(generate_mock_machine_data(m_item, month_start, month_end))

            if month_df_list:
                df_month = pd.concat(month_df_list, ignore_index=True)
                m_col1, m_col2 = st.columns([6, 4])
                with m_col1:
                    fig_month = make_subplots(specs=[[{"secondary_y": True}]])
                    df_month_avg = df_month.groupby("Ngày")[["OEE (%)", "Downtime (Phút)"]].mean().reset_index()
                    fig_month.add_trace(go.Bar(x=df_month_avg["Ngày"], y=df_month_avg["Downtime (Phút)"], name="Tổng Downtime (Phút)", marker_color="#f43f5e"), secondary_y=False)
                    fig_month.add_trace(go.Scatter(x=df_month_avg["Ngày"], y=df_month_avg["OEE (%)"], name="OEE Trung Bình (%)", mode="lines+markers", line=dict(color="#0284c7", width=3)), secondary_y=True)
                    fig_month.update_layout(title=f"Tổng Quan Downtime & OEE Cả Tháng {current_month}/{current_year}", hovermode="x unified")
                    st.plotly_chart(fig_month, use_container_width=True)
                with m_col2:
                    st.markdown(f"**📊 Bảng chỉ số trung bình theo máy trong tháng {current_month}:**")
                    with st.expander("🖱️ Click để xem Chỉ Số Trung Bình Từng Máy", expanded=True):
                        summary_month = df_month.groupby(["Mã máy", "Tên máy", "Dây chuyền"]).agg({"OEE (%)": "mean", "Sẵn sàng (%)": "mean", "Downtime (Phút)": "sum"}).reset_index().round(1)
                        st.dataframe(summary_month, use_container_width=True, height=320)
        else:
            st.warning("⚠️ Không tìm thấy thiết bị nào phù hợp với bộ lọc đã chọn!")

    # ---------------------------------------------------------
    # TRANG 2: QUẢN LÝ MÁY MÓC
    # ---------------------------------------------------------
    elif selected_menu == "🏭 Quản Lý Máy Móc":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ THIẾT BỊ & MÁY MÓC")
        st.markdown("---")
        user_m_perms = current_user.get("machine_perms", ["Xem"])
        user_editable_fields = current_user.get("editable_machine_fields", [])
        tab_m_list, tab_m_add, tab_m_edit, tab_m_delete = st.tabs(["📋 Danh Sách Thiết Bị", "➕ Thêm Thiết Bị Mới", "✏️ Chỉnh Sửa Máy", "🗑️ Xóa Máy"])

        with tab_m_list:
            if "Xem" in user_m_perms:
                if st.session_state["MACHINE_DB"]:
                    m_display = [{"Mã máy": m.get("id"), "Tên thiết bị": m.get("name"), "Dây chuyền (Line)": m.get("line"), "Đường dẫn tới máy": m.get("url", "Chưa cấu hình"), "File mẫu dữ liệu chuẩn": m.get("template_file", "Chưa nạp file mẫu")} for m in st.session_state["MACHINE_DB"]]
                    st.dataframe(pd.DataFrame(m_display), use_container_width=True)
                else:
                    st.info("Chưa có thiết bị nào trong cơ sở dữ liệu.")
            else:
                st.error("🔒 Bạn không có quyền **Xem** danh sách máy móc.")

        with tab_m_add:
            if "Thêm mới" in user_m_perms:
                st.subheader("➕ Thêm máy móc & Nạp file dữ liệu mẫu")
                col1, col2 = st.columns(2)
                with col1:
                    m_id = st.text_input("Mã máy (VD: M04)*")
                    m_name = st.text_input("Tên máy (VD: Máy mài CNC)*")
                    m_line = st.text_input("Dây chuyền (Line)*", placeholder="Tự nhập tên Line (VD: G103, Line-A, SMT-1...)")
                with col2:
                    m_url = st.text_input("Đường dẫn tới máy (URL / IP / Path)")
                    template_file = st.file_uploader("📁 Nạp File Mẫu Chuẩn", type=["csv", "xlsx", "xlsm", "xlsb"])

                if st.button("💾 Lưu Thiết Bị Mới", use_container_width=True, type="primary"):
                    if not m_id or not m_name or not m_line:
                        show_popup_message("LỖI NHẬP DỮ LIỆU", "Vui lòng điền đầy đủ Mã, Tên và Dây chuyền!", icon="❌")
                    elif any(m["id"] == m_id for m in st.session_state["MACHINE_DB"]):
                        show_popup_message("TRÙNG MÃ MÁY", f"Mã máy `{m_id}` đã tồn tại!", icon="⚠️")
                    else:
                        st.session_state["MACHINE_DB"].append({
                            "id": m_id, "name": m_name, "line": m_line.strip(),
                            "url": m_url if m_url else "Chưa cấu hình",
                            "template_file": template_file.name if template_file else "Chưa nạp file mẫu",
                            "has_file": bool(template_file)
                        })
                        show_popup_message("THÀNH CÔNG", f"Đã thêm thiết bị **{m_name}**!", icon="🎉")
            else:
                st.error("🔒 Không có quyền Thêm mới thiết bị!")

        with tab_m_edit:
            if "Chỉnh sửa" in user_m_perms and st.session_state["MACHINE_DB"]:
                machine_options = [f"{m['id']} - {m['name']}" for m in st.session_state["MACHINE_DB"]]
                selected_m_option = st.selectbox("Chọn máy cần chỉnh sửa", machine_options, key="select_edit_m")
                selected_m_id = selected_m_option.split(" - ")[0]
                m_idx = next(i for i, m in enumerate(st.session_state["MACHINE_DB"]) if m["id"] == selected_m_id)
                cur_m = st.session_state["MACHINE_DB"][m_idx]

                st.info("💡 **Mã máy (ID)** là Khóa chính dùng để liên kết dữ liệu. Không thể thay đổi Mã máy. Nếu bạn nhập sai mã, vui lòng sang Tab 'Xóa Máy' và 'Thêm Thiết Bị Mới'.")

                with st.form("form_edit_machine"):
                    e_m_name = st.text_input("Tên máy", value=cur_m.get("name", ""), disabled="Tên máy" not in user_editable_fields)
                    e_m_line = st.text_input("Dây chuyền (Line)", value=cur_m.get("line", ""), disabled="Dây chuyền (Line)" not in user_editable_fields)
                    e_m_url = st.text_input("Đường dẫn", value=cur_m.get("url", ""), disabled="Đường dẫn máy" not in user_editable_fields)
                    e_template_file = st.file_uploader("Thay File mẫu", type=["csv", "xlsx", "xlsm", "xlsb"], disabled="File mẫu dữ liệu" not in user_editable_fields)

                    if st.form_submit_button("💾 Cập Nhật", use_container_width=True):
                        st.session_state["MACHINE_DB"][m_idx] = {
                            "id": selected_m_id,
                            "name": e_m_name if "Tên máy" in user_editable_fields else cur_m.get("name"),
                            "line": e_m_line.strip() if "Dây chuyền (Line)" in user_editable_fields else cur_m.get("line"),
                            "url": e_m_url if "Đường dẫn máy" in user_editable_fields else cur_m.get("url"),
                            "template_file": e_template_file.name if e_template_file else cur_m.get("template_file"),
                            "has_file": bool(e_template_file) or cur_m.get("has_file")
                        }
                        show_popup_message("THÀNH CÔNG", f"Đã cập nhật máy **{selected_m_id}**!", icon="💾")

        with tab_m_delete:
            if "Xóa" in user_m_perms and st.session_state["MACHINE_DB"]:
                del_m_option = st.selectbox("Chọn máy cần xóa", [f"{m['id']} - {m['name']}" for m in st.session_state["MACHINE_DB"]])
                del_m_id = del_m_option.split(" - ")[0]
                if st.button("🗑️ Xác Nhận Xóa", type="primary", use_container_width=True):
                    st.session_state["MACHINE_DB"] = [m for m in st.session_state["MACHINE_DB"] if m["id"] != del_m_id]
                    show_popup_message("ĐÃ XÓA", f"Đã xóa máy **{del_m_id}**!", icon="🗑️")

    # ---------------------------------------------------------
    # TRANG 3: QUẢN LÝ TÀI KHOẢN (ĐÃ NÂNG CẤP BẢO MẬT VÀ FULL SỬA)
    # ---------------------------------------------------------
    elif selected_menu == "👤 Quản Lý Tài Khoản":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ TÀI KHOẢN")
        st.markdown("---")

        tab_list, tab_add, tab_edit, tab_delete, tab_logs = st.tabs([
            "📋 Danh Sách Tài Khoản", "➕ Tạo Mới", "✏️ Chỉnh Sửa", "🗑️ Xóa", "🛡️ Nhật Ký Bảo Mật"
        ])

        with tab_list:
            display_data = []
            for uname, uinfo in st.session_state["USER_DB"].items():
                display_data.append({
                    "Tài khoản": uname, "Họ và Tên": uinfo.get("name", ""),
                    "Bộ phận": uinfo.get("department", ""), "Chức vụ": uinfo.get("position", ""),
                    "Quyền": uinfo.get("role", "")
                })
            st.dataframe(pd.DataFrame(display_data), use_container_width=True)

        with tab_add:
            with st.form("form_add_user"):
                st.info("🔐 Mật khẩu phải có ≥ 8 ký tự, gồm: Chữ HOA, chữ thường, số, ký tự đặc biệt (@$!%*?&#)")
                c1, c2 = st.columns(2)
                with c1:
                    a_username = st.text_input("Tên tài khoản*")
                    a_password = st.text_input("Mật khẩu*", type="password")
                    a_fullname = st.text_input("Họ và Tên")
                with c2:
                    a_dept = st.text_input("Bộ phận", value="Sản Xuất")
                    a_pos = st.text_input("Chức vụ", value="Nhân Viên")
                    a_role = st.text_input("Quyền*", value="Operator")

                a_pages = st.multiselect("Trang truy cập", ALL_FEATURES, default=["🎛️ Dashboard OEE"])
                a_m_perms = st.multiselect("Quyền thiết bị", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=["Xem"])
                a_edit_fields = st.multiselect("Cột được sửa", ALL_MACHINE_EDIT_FIELDS, default=["Đường dẫn máy"])

                if st.form_submit_button("➕ Tạo Mới", use_container_width=True):
                    if not validate_username(a_username):
                        show_popup_message("LỖI ĐỊNH DẠNG", "Tên đăng nhập 3-20 ký tự (Không chứa dấu, khoảng trắng)!", icon="❌")
                    else:
                        is_valid, msg = validate_password_strength(a_password)
                        if not is_valid:
                            show_popup_message("MẬT KHẨU YẾU", msg, icon="❌")
                        elif a_username.lower() in st.session_state["USER_DB"]:
                            show_popup_message("TỒN TẠI", "Tài khoản đã tồn tại!", icon="⚠️")
                        else:
                            st.session_state["USER_DB"][a_username.lower()] = {
                                "password_hash": hash_password(a_password),
                                "name": a_fullname, "department": a_dept, "position": a_pos, "role": a_role.strip(),
                                "allowed_pages": a_pages, "machine_perms": a_m_perms, "editable_machine_fields": a_edit_fields
                            }
                            log_security_event(st.session_state["username"], f"TẠO USER ({a_username})", "Thành công")
                            show_popup_message("THÀNH CÔNG", f"Đã tạo tài khoản **{a_username}**!", icon="👤")

        with tab_edit:
            target_user = st.selectbox("Chọn tài khoản cần sửa", list(st.session_state["USER_DB"].keys()))
            u_data = st.session_state["USER_DB"][target_user]
            
            with st.form("form_edit_user"):
                st.markdown("**1. Thông tin cơ bản:**")
                e_password = st.text_input("Mật khẩu mới (Để trống nếu không đổi)", type="password")
                e_fullname = st.text_input("Họ và Tên", value=u_data.get("name", ""))
                
                c1, c2, c3 = st.columns(3)
                with c1: e_dept = st.text_input("Bộ phận", value=u_data.get("department", ""))
                with c2: e_pos = st.text_input("Chức vụ", value=u_data.get("position", ""))
                with c3: e_role = st.text_input("Quyền (Role)", value=u_data.get("role", "Operator"))

                st.markdown("**2. Phân quyền truy cập & Thao tác:**")
                e_pages = st.multiselect("Trang truy cập", ALL_FEATURES, default=u_data.get("allowed_pages", []))
                e_m_perms = st.multiselect("Quyền thiết bị", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=u_data.get("machine_perms", ["Xem"]))
                e_edits = st.multiselect("Cột được sửa", ALL_MACHINE_EDIT_FIELDS, default=u_data.get("editable_machine_fields", []))
                
                if st.form_submit_button("💾 Lưu Thay Đổi Toàn Diện", use_container_width=True):
                    if e_password:
                        is_valid, msg = validate_password_strength(e_password)
                        if not is_valid: 
                            show_popup_message("LỖI", msg, "❌")
                            st.stop()
                    
                    st.session_state["USER_DB"][target_user].update({
                        "password_hash": hash_password(e_password) if e_password else u_data["password_hash"],
                        "name": e_fullname, 
                        "department": e_dept, 
                        "position": e_pos, 
                        "role": e_role.strip(),
                        "allowed_pages": e_pages, 
                        "machine_perms": e_m_perms, 
                        "editable_machine_fields": e_edits
                    })
                    
                    # Cập nhật thông tin cho người dùng hiện tại nếu họ đang tự sửa chính mình
                    if target_user == st.session_state["username"]:
                        st.session_state["user_info"] = st.session_state["USER_DB"][target_user]
                    
                    log_security_event(st.session_state["username"], f"SỬA USER TOÀN DIỆN ({target_user})", "Thành công")
                    show_popup_message("THÀNH CÔNG", f"Đã cập nhật toàn bộ thông tin cho **{target_user}**!", icon="💾")

        with tab_delete:
            del_user = st.selectbox("Xóa tài khoản", list(st.session_state["USER_DB"].keys()), key="del_u")
            if st.button("🗑️ Xác Nhận Xóa", type="primary", use_container_width=True):
                if del_user == st.session_state["username"]:
                    show_popup_message("LỖI", "Không thể tự xóa bản thân!", icon="🚫")
                else:
                    del st.session_state["USER_DB"][del_user]
                    log_security_event(st.session_state["username"], f"XÓA USER ({del_user})", "Thành công")
                    show_popup_message("THÀNH CÔNG", f"Đã xóa **{del_user}**!", icon="🗑️")

        with tab_logs:
            st.subheader("🛡️ Nhật ký hoạt động & bảo mật (Audit Logs)")
            if st.session_state["AUDIT_LOGS"]:
                for log in st.session_state["AUDIT_LOGS"]:
                    st.text(log)
            else:
                st.info("Chưa có bản ghi nhật ký nào.")
