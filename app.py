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
import sqlite3
import json

# ==========================================
# CẤU HÌNH TRANG
# ==========================================
st.set_page_config(page_title="Dashboard OEE & Quản Lý Nhà Máy", layout="wide", initial_sidebar_state="expanded")

ALL_FEATURES = [
    "🎛️ Dashboard OEE",
    "📦 Kho Spare Part",
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
# 🗄️ KẾT NỐI CƠ SỞ DỮ LIỆU SQLITE
# ==========================================
def get_db_connection():
    conn = sqlite3.connect('mes_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# CÁC HÀM BẢO MẬT & MÃ HÓA
# ==========================================
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return salt + ":" + key.hex()

def verify_password(password, hashed_pass):
    try:
        salt, _ = hashed_pass.split(':')
        return hash_password(password, salt) == hashed_pass
    except Exception:
        return False

def validate_username(username):
    return bool(re.match(r"^[a-zA-Z0-9_]{3,20}$", username))

def validate_password_strength(password):
    if len(password) < 8: return False, "Mật khẩu phải có ít nhất 8 ký tự!"
    if not re.search(r"[A-Z]", password): return False, "Phải chứa ít nhất 1 chữ hoa!"
    if not re.search(r"[a-z]", password): return False, "Phải chứa ít nhất 1 chữ thường!"
    if not re.search(r"\d", password): return False, "Phải chứa ít nhất 1 chữ số!"
    if not re.search(r"[@$!%*?&#]", password): return False, "Phải chứa ít nhất 1 ký tự đặc biệt (@, $, !, %, *, ?, &, #)!"
    return True, "Hợp lệ"

def log_security_event(username, event_type, status):
    conn = get_db_connection()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO audit_logs (timestamp, username, event_type, status) VALUES (?,?,?,?)", (timestamp, username, event_type, status))
    conn.commit()
    conn.close()

# ==========================================
# KHỞI TẠO BẢNG & DỮ LIỆU MẶC ĐỊNH
# ==========================================
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Bảng Tài Khoản
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT,
                    name TEXT,
                    department TEXT,
                    position TEXT,
                    role TEXT,
                    allowed_pages TEXT,
                    machine_perms TEXT,
                    editable_machine_fields TEXT
                )''')
    
    # 2. Bảng Máy Móc
    c.execute('''CREATE TABLE IF NOT EXISTS machines (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    line TEXT,
                    url TEXT,
                    template_file TEXT,
                    has_file INTEGER
                )''')

    # 3. Bảng Kho Spare Part
    c.execute('''CREATE TABLE IF NOT EXISTS spare_parts (
                    part_id TEXT PRIMARY KEY,
                    part_name TEXT,
                    category TEXT,
                    model_applicable TEXT,
                    location TEXT,
                    quantity INTEGER,
                    min_quantity INTEGER,
                    unit TEXT
                )''')

    # 4. Bảng Lịch Sử Xuất Nhập Spare Part
    c.execute('''CREATE TABLE IF NOT EXISTS spare_part_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    part_id TEXT,
                    action_type TEXT,
                    quantity_changed INTEGER,
                    remaining_qty INTEGER,
                    user_action TEXT,
                    notes TEXT
                )''')
    
    # 5. Bảng Nhật Ký Bảo Mật
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    username TEXT,
                    event_type TEXT,
                    status TEXT
                )''')

    # 6. Tạo tài khoản mặc định nếu DB trống
    c.execute("SELECT username FROM users WHERE username='admin'")
    if not c.fetchone():
        admin_pass = hash_password("Admin@123")
        c.execute('''INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)''',
                  ('admin', admin_pass, 'Giám Đốc Nhà Máy', 'Ban Giám Đốc', 'Giám Đốc', 'Admin',
                   json.dumps(ALL_FEATURES), json.dumps(["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"]), json.dumps(ALL_MACHINE_EDIT_FIELDS)))
        
        manager_pass = hash_password("Manager@123")
        c.execute('''INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)''',
                  ('manager', manager_pass, 'Kỹ Sư IE', 'Kỹ Thuật (IE)', 'Trưởng Nhóm IE', 'Manager',
                   json.dumps(ALL_FEATURES), json.dumps(["Xem", "Chỉnh sửa"]), json.dumps(["Đường dẫn máy"])))
    
    # 7. Dữ liệu máy móc mẫu
    c.execute("SELECT count(*) FROM machines")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", ("M01", "Máy dập Block 1", "G103", "http://192.168.1.100/m01", "template_oee_g103.xlsx", 1))
        c.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", ("M02", "Máy Test Hipot", "G104", "http://192.168.1.101/m02", "template_oee_g104.csv", 1))

    # 8. Dữ liệu Spare Part mẫu
    c.execute("SELECT count(*) FROM spare_parts")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?)", ("SP01", "Van điện từ SMC 24V", "Khí nén", "Máy dập Block 1", "Kệ A-01", 12, 5, "Cái"))
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?)", ("SP02", "Cảm biến quang Omron E3Z", "Cảm biến", "Tất cả", "Kệ A-02", 3, 6, "Cái"))
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?)", ("SP03", "Dây curoa răng 5M-350", "Cơ khí", "Máy Test Hipot", "Kệ B-01", 8, 4, "Sợi"))
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?)", ("SP04", "Kim phun keo Dispenser 0.3mm", "Vật tư tiêu hao", "Máy dập Block 1", "Kệ C-05", 2, 10, "Hộp"))
        
    conn.commit()
    conn.close()

init_db()

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
# HÀM HỖ TRỢ HIỂN THỊ & DỮ LIỆU
# ==========================================
@st.dialog("🔔 THÔNG BÁO HỆ THỐNG")
def show_popup_message(title, message, icon="ℹ️"):
    st.markdown(f"### {icon} {title}")
    st.write(message)
    if st.button("Đóng", use_container_width=True, type="primary"):
        st.rerun()

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
# KHỞI TẠO STATE
# ==========================================
if "LOGIN_ATTEMPTS" not in st.session_state: st.session_state["LOGIN_ATTEMPTS"] = {}
if "selected_menu" not in st.session_state: st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

# ==========================================
# LOGIC ĐĂNG NHẬP / ĐĂNG XUẤT
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
            with st.form("login_form"):
                username = st.text_input("👤 Tên đăng nhập", placeholder="Nhập tên đăng nhập")
                password = st.text_input("🔑 Mật khẩu", type="password", placeholder="Nhập mật khẩu")
                submit_button = st.form_submit_button("🚀 Đăng nhập", use_container_width=True, type="primary")
                
                if submit_button:
                    username_cleaned = username.strip().lower()
                    attempts_info = st.session_state["LOGIN_ATTEMPTS"].get(username_cleaned, {"count": 0, "lockout_until": 0})
                    if time.time() < attempts_info["lockout_until"]:
                        st.error(f"❌ Tài khoản đang bị khóa. Thử lại sau {int(attempts_info['lockout_until'] - time.time())} giây!")
                        log_security_event(username_cleaned, "LOGIN_BLOCKED", "Thất bại (Locked)")
                    else:
                        conn = get_db_connection()
                        user = conn.execute("SELECT * FROM users WHERE username = ?", (username_cleaned,)).fetchone()
                        conn.close()

                        if user:
                            if verify_password(password, user['password_hash']):
                                st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = {"count": 0, "lockout_until": 0}
                                st.session_state["logged_in"] = True
                                st.session_state["username"] = username_cleaned
                                st.session_state["user_info"] = {
                                    "name": user['name'], "department": user['department'], "position": user['position'],
                                    "role": user['role'], "allowed_pages": json.loads(user['allowed_pages']),
                                    "machine_perms": json.loads(user['machine_perms']), "editable_machine_fields": json.loads(user['editable_machine_fields'])
                                }
                                st.session_state["last_activity"] = time.time() 
                                log_security_event(username_cleaned, "LOGIN", "Thành công")
                                st.rerun()
                            else:
                                attempts_info["count"] += 1
                                if attempts_info["count"] >= MAX_LOGIN_ATTEMPTS:
                                    attempts_info["lockout_until"] = time.time() + LOCKOUT_DURATION
                                    st.error(f"❌ Nhập sai {MAX_LOGIN_ATTEMPTS} lần. Bị khóa 5 phút!")
                                    log_security_event(username_cleaned, "BRUTE_FORCE_DETECTED", "Khóa tài khoản")
                                else:
                                    st.error(f"❌ Sai mật khẩu! (Còn {MAX_LOGIN_ATTEMPTS - attempts_info['count']} lần thử)")
                                    log_security_event(username_cleaned, "LOGIN_FAILED", "Sai mật khẩu")
                                st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = attempts_info
                        else:
                            st.error("❌ Tài khoản không tồn tại!")
                            log_security_event(username_cleaned, "LOGIN_FAILED", "User không tồn tại")

        st.markdown("<p style='text-align: center; color: #64748b; font-size: 0.85rem; margin-top: 30px;'>© 2026 Smart Factory Management | Enterprise Secured (SQLite)</p>", unsafe_allow_html=True)

def logout(reason=""):
    log_security_event(st.session_state.get("username", "Unknown"), "LOGOUT", "Thành công")
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("user_info", None)
    st.session_state.pop("last_activity", None)
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
    if reason: st.warning(reason)

def go_home():
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
    st.session_state["menu_radio"] = "🎛️ Dashboard OEE"

# ==========================================
# GIAO DIỆN CHÍNH KHI ĐÃ ĐĂNG NHẬP
# ==========================================
if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
else:
    if (time.time() - st.session_state.get("last_activity", 0)) > SESSION_TIMEOUT:
        logout("⏳ Phiên đăng nhập đã hết hạn do không hoạt động để bảo mật dữ liệu. Vui lòng đăng nhập lại!")
        st.rerun()
    else:
        st.session_state["last_activity"] = time.time() 

    current_user = st.session_state["user_info"]
    
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

        selected_menu = st.radio("📌 ĐIỀU HƯỚNG HỆ THỐNG", user_pages, key="menu_radio")
        if selected_menu != st.session_state["selected_menu"]:
            st.session_state["selected_menu"] = selected_menu
            st.rerun()

        st.markdown("---")
        st.button("🚪 Đăng xuất an toàn", on_click=lambda: logout(), use_container_width=True)

    # ĐỌC DB MÁY MÓC TỪ SQLITE
    conn = get_db_connection()
    machine_db_raw = conn.execute("SELECT * FROM machines").fetchall()
    machine_db = [{"id": m["id"], "name": m["name"], "line": m["line"], "url": m["url"], "template_file": m["template_file"], "has_file": bool(m["has_file"])} for m in machine_db_raw]
    conn.close()

    # ---------------------------------------------------------
    # TRANG 1: DASHBOARD OEE
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
                    with st.expander("🖱️ Click để xem Phân Tích Tổng Quan Tháng"):
                        tb_oee_thang = df_month_avg['OEE (%)'].mean()
                        tong_dt_thang = df_month_avg['Downtime (Phút)'].sum()
                        st.success(f"**Kết quả tháng {current_month}/{current_year}:**")
                        st.write(f"- 📈 **OEE Trung bình toàn tháng:** {tb_oee_thang:.1f}%")
                        st.write(f"- 🕒 **Tổng thời gian Downtime:** {tong_dt_thang:.0f} Phút")

                with m_col2:
                    st.markdown(f"**📊 Bảng chỉ số trung bình theo máy trong tháng {current_month}:**")
                    with st.expander("🖱️ Click để xem Chỉ Số Trung Bình Từng Máy", expanded=True):
                        summary_month = df_month.groupby(["Mã máy", "Tên máy", "Dây chuyền"]).agg({"OEE (%)": "mean", "Sẵn sàng (%)": "mean", "Downtime (Phút)": "sum"}).reset_index().round(1)
                        st.dataframe(summary_month, use_container_width=True, height=320)
        else:
            st.warning("⚠️ Không tìm thấy thiết bị nào phù hợp với bộ lọc đã chọn!")

    # ---------------------------------------------------------
    # TRANG 2: KHO SPARE PART
    # ---------------------------------------------------------
    elif selected_menu == "📦 Kho Spare Part":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## 📦 QUẢN LÝ KHO PHỤ TÙNG & LINH KIỆN (SPARE PARTS)")
        st.markdown("---")

        conn = get_db_connection()
        sp_data_raw = conn.execute("SELECT * FROM spare_parts").fetchall()
        sp_data = [dict(r) for r in sp_data_raw]
        conn.close()

        # Hiển thị số lượng linh kiện cần cảnh báo
        low_stock_items = [item for item in sp_data if item["quantity"] <= item["min_quantity"]]
        
        sp_kpi1, sp_kpi2, sp_kpi3 = st.columns(3)
        with sp_kpi1:
            st.markdown(f'''<div class="kpi-card-1"><span style="color: #1e3a8a; font-size: 13px; font-weight: bold;">Tổng Danh Mục Linh Kiện</span><h2 style="color: #1d4ed8; margin: 5px 0 0 0;">{len(sp_data)} Loại</h2></div>''', unsafe_allow_html=True)
        with sp_kpi2:
            st.markdown(f'''<div class="kpi-card-2"><span style="color: #14532d; font-size: 13px; font-weight: bold;">Tổng Tồn Kho (Pieces)</span><h2 style="color: #15803d; margin: 5px 0 0 0;">{sum(i["quantity"] for i in sp_data)} Cái</h2></div>''', unsafe_allow_html=True)
        with sp_kpi3:
            st.markdown(f'''<div class="kpi-card-3"><span style="color: #7f1d1d; font-size: 13px; font-weight: bold;">Cảnh Báo Thiếu Hàng (Low Stock)</span><h2 style="color: #b91c1c; margin: 5px 0 0 0;">{len(low_stock_items)} Loại</h2></div>''', unsafe_allow_html=True)
        
        st.markdown("---")
        
        if low_stock_items:
            st.error(f"⚠️ **CẢNH BÁO TỒN KHO TỐI THIỂU:** Có {len(low_stock_items)} linh kiện đang dưới hoặc bằng mức an toàn: " + ", ".join([f"**{i['part_name']}** (Tồn: {i['quantity']} {i['unit']})" for i in low_stock_items]))

        tab_sp_list, tab_sp_tx, tab_sp_add, tab_sp_edit, tab_sp_history = st.tabs([
            "📋 Danh Sách Tồn Kho", "🔄 Xuất / Nhập Kho", "➕ Thêm Mã Phụ Tùng", "✏️ Chỉnh Sửa Thông Tin", "📜 Lịch Sử Giao Dịch"
        ])

        # TAB 1: DANH SÁCH TỒN KHO
        with tab_sp_list:
            if sp_data:
                df_sp = pd.DataFrame(sp_data).rename(columns={
                    "part_id": "Mã Phụ Tùng", "part_name": "Tên Phụ Tùng", "category": "Nhóm",
                    "model_applicable": "Thiết Bị Sử Dụng", "location": "Vị Trí Kệ",
                    "quantity": "Tồn Kho Hiện Tại", "min_quantity": "Tồn Tối Thiểu", "unit": "ĐVT"
                })
                st.dataframe(df_sp, use_container_width=True)
            else:
                st.info("Chưa có dữ liệu linh kiện trong kho.")

        # TAB 2: XUẤT / NHẬP KHO
        with tab_sp_tx:
            if sp_data:
                st.subheader("Thực Hiện Giao Dịch Xuất / Nhập Kho")
                with st.form("form_sp_tx"):
                    c_tx1, c_tx2 = st.columns(2)
                    with c_tx1:
                        tx_part_opt = st.selectbox("Chọn Phụ Tùng", [f"{i['part_id']} - {i['part_name']} (Tồn: {i['quantity']})" for i in sp_data])
                        tx_part_id = tx_part_opt.split(" - ")[0]
                        tx_action = st.radio("Loại giao dịch", ["📥 Nhập Kho (+)", "📤 Xuất Kho Dùng (-)"], horizontal=True)
                    with c_tx2:
                        tx_qty = st.number_input("Số lượng", min_value=1, value=1)
                        tx_note = st.text_input("Ghi chú / Mục đích sử dụng (VD: Thay thế bảo dưỡng máy M01)")

                    if st.form_submit_button("💾 Xác Nhận Giao Dịch", use_container_width=True, type="primary"):
                        cur_item = next(i for i in sp_data if i["part_id"] == tx_part_id)
                        current_qty = cur_item["quantity"]
                        
                        if tx_action == "📤 Xuất Kho Dùng (-)" and tx_qty > current_qty:
                            show_popup_message("LỖI XUẤT KHO", f"Số lượng xuất ({tx_qty}) vượt quá số lượng tồn kho ({current_qty})!", "❌")
                        else:
                            new_qty = current_qty + tx_qty if tx_action == "📥 Nhập Kho (+)" else current_qty - tx_qty
                            timestamp_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            conn = get_db_connection()
                            conn.execute("UPDATE spare_parts SET quantity = ? WHERE part_id = ?", (new_qty, tx_part_id))
                            conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                         (timestamp_now, tx_part_id, "NHAP" if tx_action == "📥 Nhập Kho (+)" else "XUAT", tx_qty, new_qty, current_user["name"], tx_note))
                            conn.commit()
                            conn.close()
                            
                            show_popup_message("GIAO DỊCH THÀNH CÔNG", f"Đã cập nhật tồn kho cho **{cur_item['part_name']}**! Tồn mới: **{new_qty} {cur_item['unit']}**.", "📦")
            else:
                st.info("Chưa có phụ tùng nào trong kho.")

        # TAB 3: THÊM MÃ PHỤ TÙNG MỚI
        with tab_sp_add:
            with st.form("form_add_sp"):
                st.subheader("Khai Báo Phụ Tùng / Vật Tư Mới")
                c_a1, c_a2 = st.columns(2)
                with c_a1:
                    new_sp_id = st.text_input("Mã Phụ Tùng (VD: SP05)*")
                    new_sp_name = st.text_input("Tên Phụ Tùng / Linh Kiện*")
                    new_sp_cat = st.selectbox("Phân Loại Nhóm", ["Khí nén", "Cơ khí", "Cảm biến", "Điện - Tự động hóa", "Vật tư tiêu hao", "Khác"])
                    new_sp_model = st.text_input("Dùng cho thiết bị / Máy nào", value="Tất cả")
                with c_a2:
                    new_sp_loc = st.text_input("Vị trí lưu kho (Kệ / Ô / Ngăn)", value="Kệ A-01")
                    new_sp_qty = st.number_input("Số lượng tồn ban đầu", min_value=0, value=10)
                    new_sp_min = st.number_input("Mức tồn kho an toàn (Min Alert)", min_value=1, value=5)
                    new_sp_unit = st.selectbox("Đơn vị tính (ĐVT)", ["Cái", "Bộ", "Sợi", "Hộp", "Thanh", "Mét"])

                if st.form_submit_button("➕ Lưu Phụ Tùng Mới", use_container_width=True, type="primary"):
                    if not new_sp_id or not new_sp_name:
                        show_popup_message("LỖI", "Vui lòng nhập Mã và Tên phụ tùng!", "❌")
                    elif any(i["part_id"] == new_sp_id for i in sp_data):
                        show_popup_message("LỖI", f"Mã phụ tùng `{new_sp_id}` đã tồn tại!", "⚠️")
                    else:
                        conn = get_db_connection()
                        conn.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?)",
                                     (new_sp_id, new_sp_name, new_sp_cat, new_sp_model, new_sp_loc, new_sp_qty, new_sp_min, new_sp_unit))
                        conn.commit()
                        conn.close()
                        show_popup_message("THÀNH CÔNG", f"Đã thêm phụ tùng **{new_sp_name} ({new_sp_id})** vào kho!", "🎉")

        # TAB 4: CHỈNH SỬA PHỤ TÙNG
        with tab_sp_edit:
            if sp_data:
                edit_sp_sel = st.selectbox("Chọn Phụ Tùng Cần Chỉnh Sửa", [f"{i['part_id']} - {i['part_name']}" for i in sp_data], key="sel_sp_edit")
                edit_sp_id = edit_sp_sel.split(" - ")[0]
                cur_sp = next(i for i in sp_data if i["part_id"] == edit_sp_id)

                with st.form("form_edit_sp"):
                    c_e1, c_e2 = st.columns(2)
                    with c_e1:
                        e_sp_name = st.text_input("Tên Phụ Tùng", value=cur_sp["part_name"])
                        e_sp_cat = st.text_input("Phân Loại", value=cur_sp["category"])
                        e_sp_model = st.text_input("Thiết Bị Áp Dụng", value=cur_sp["model_applicable"])
                    with c_e2:
                        e_sp_loc = st.text_input("Vị Trí Kệ", value=cur_sp["location"])
                        e_sp_min = st.number_input("Mức Tồn Kho An Toàn (Min)", min_value=1, value=int(cur_sp["min_quantity"]))
                        e_sp_unit = st.text_input("Đơn Vị Tính", value=cur_sp["unit"])

                    if st.form_submit_button("💾 Cập Nhật Thông Tin", use_container_width=True):
                        conn = get_db_connection()
                        conn.execute("UPDATE spare_parts SET part_name=?, category=?, model_applicable=?, location=?, min_quantity=?, unit=? WHERE part_id=?",
                                     (e_sp_name, e_sp_cat, e_sp_model, e_sp_loc, e_sp_min, e_sp_unit, edit_sp_id))
                        conn.commit()
                        conn.close()
                        show_popup_message("THÀNH CÔNG", f"Đã cập nhật linh kiện **{edit_sp_id}**!", "💾")
            else:
                st.info("Chưa có phụ tùng để chỉnh sửa.")

        # TAB 5: LỊCH SỬ XUẤT NHẬP
        with tab_sp_history:
            st.subheader("📜 Nhật Ký Xuất / Nhập Kho Gần Đây")
            conn = get_db_connection()
            tx_logs = conn.execute("SELECT * FROM spare_part_logs ORDER BY id DESC LIMIT 100").fetchall()
            conn.close()
            if tx_logs:
                df_tx_logs = pd.DataFrame([dict(r) for r in tx_logs]).rename(columns={
                    "id": "Mã GD", "timestamp": "Thời Gian", "part_id": "Mã Phụ Tùng",
                    "action_type": "Loại GD", "quantity_changed": "Số Lượng",
                    "remaining_qty": "Tồn Còn Lại", "user_action": "Người Thực Hiện", "notes": "Ghi Chú"
                })
                st.dataframe(df_tx_logs, use_container_width=True)
            else:
                st.info("Chưa có lịch sử xuất nhập kho nào được ghi nhận.")

    # ---------------------------------------------------------
    # TRANG 3: QUẢN LÝ MÁY MÓC (SQLITE)
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
                if machine_db:
                    m_display = [{"Mã máy": m.get("id"), "Tên thiết bị": m.get("name"), "Dây chuyền (Line)": m.get("line"), "Đường dẫn tới máy": m.get("url", "Chưa cấu hình"), "File mẫu dữ liệu chuẩn": m.get("template_file", "Chưa nạp file mẫu")} for m in machine_db]
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
                    elif any(m["id"] == m_id for m in machine_db):
                        show_popup_message("TRÙNG MÃ MÁY", f"Mã máy `{m_id}` đã tồn tại!", icon="⚠️")
                    else:
                        conn = get_db_connection()
                        conn.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", (m_id, m_name, m_line.strip(), m_url if m_url else "Chưa cấu hình", template_file.name if template_file else "Chưa nạp file mẫu", 1 if template_file else 0))
                        conn.commit()
                        conn.close()
                        show_popup_message("THÀNH CÔNG", f"Đã thêm thiết bị **{m_name}**!", icon="🎉")
            else:
                st.error("🔒 Không có quyền Thêm mới thiết bị!")

        with tab_m_edit:
            if "Chỉnh sửa" in user_m_perms and machine_db:
                machine_options = [f"{m['id']} - {m['name']}" for m in machine_db]
                selected_m_option = st.selectbox("Chọn máy cần chỉnh sửa", machine_options, key="select_edit_m")
                selected_m_id = selected_m_option.split(" - ")[0]
                cur_m = next(m for m in machine_db if m["id"] == selected_m_id)

                st.info("💡 **Mã máy (ID)** là Khóa chính dùng để liên kết dữ liệu. Không thể thay đổi Mã máy. Nếu bạn nhập sai mã, vui lòng sang Tab 'Xóa Máy' và 'Thêm Thiết Bị Mới'.")

                with st.form("form_edit_machine"):
                    e_m_name = st.text_input("Tên máy", value=cur_m.get("name", ""), disabled="Tên máy" not in user_editable_fields)
                    e_m_line = st.text_input("Dây chuyền (Line)", value=cur_m.get("line", ""), disabled="Dây chuyền (Line)" not in user_editable_fields)
                    e_m_url = st.text_input("Đường dẫn", value=cur_m.get("url", ""), disabled="Đường dẫn máy" not in user_editable_fields)
                    e_template_file = st.file_uploader("Thay File mẫu", type=["csv", "xlsx", "xlsm", "xlsb"], disabled="File mẫu dữ liệu" not in user_editable_fields)

                    if st.form_submit_button("💾 Cập Nhật", use_container_width=True):
                        conn = get_db_connection()
                        conn.execute("UPDATE machines SET name=?, line=?, url=?, template_file=?, has_file=? WHERE id=?", 
                                     (e_m_name if "Tên máy" in user_editable_fields else cur_m.get("name"),
                                      e_m_line.strip() if "Dây chuyền (Line)" in user_editable_fields else cur_m.get("line"),
                                      e_m_url if "Đường dẫn máy" in user_editable_fields else cur_m.get("url"),
                                      e_template_file.name if e_template_file else cur_m.get("template_file"),
                                      1 if e_template_file or cur_m.get("has_file") else 0, selected_m_id))
                        conn.commit()
                        conn.close()
                        show_popup_message("THÀNH CÔNG", f"Đã cập nhật máy **{selected_m_id}**!", icon="💾")

        with tab_m_delete:
            if "Xóa" in user_m_perms and machine_db:
                del_m_option = st.selectbox("Chọn máy cần xóa", [f"{m['id']} - {m['name']}" for m in machine_db])
                del_m_id = del_m_option.split(" - ")[0]
                if st.button("🗑️ Xác Nhận Xóa", type="primary", use_container_width=True):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM machines WHERE id=?", (del_m_id,))
                    conn.commit()
                    conn.close()
                    show_popup_message("ĐÃ XÓA", f"Đã xóa máy **{del_m_id}**!", icon="🗑️")

    # ---------------------------------------------------------
    # TRANG 4: QUẢN LÝ TÀI KHOẢN (SQLITE)
    # ---------------------------------------------------------
    elif selected_menu == "👤 Quản Lý Tài Khoản":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ TÀI KHOẢN")
        st.markdown("---")

        conn = get_db_connection()
        users_db = conn.execute("SELECT * FROM users").fetchall()
        conn.close()

        tab_list, tab_add, tab_edit, tab_delete, tab_logs = st.tabs([
            "📋 Danh Sách Tài Khoản", "➕ Tạo Mới", "✏️ Chỉnh Sửa", "🗑️ Xóa", "🛡️ Nhật Ký Bảo Mật"
        ])

        with tab_list:
            display_data = []
            for u in users_db:
                display_data.append({
                    "Tài khoản": u["username"], "Họ và Tên": u["name"],
                    "Bộ phận": u["department"], "Chức vụ": u["position"],
                    "Quyền": u["role"]
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
                        elif any(u["username"] == a_username.lower() for u in users_db):
                            show_popup_message("TỒN TẠI", "Tài khoản đã tồn tại!", icon="⚠️")
                        else:
                            conn = get_db_connection()
                            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", 
                                        (a_username.lower(), hash_password(a_password), a_fullname, a_dept, a_pos, a_role.strip(), json.dumps(a_pages), json.dumps(a_m_perms), json.dumps(a_edit_fields)))
                            conn.commit()
                            conn.close()
                            log_security_event(st.session_state["username"], f"TẠO USER ({a_username})", "Thành công")
                            show_popup_message("THÀNH CÔNG", f"Đã tạo tài khoản **{a_username}**!", icon="👤")

        with tab_edit:
            target_user = st.selectbox("Chọn tài khoản cần sửa", [u["username"] for u in users_db])
            cur_u = next(u for u in users_db if u["username"] == target_user)
            with st.form("form_edit_user"):
                st.markdown("**1. Thông tin cơ bản:**")
                e_password = st.text_input("Mật khẩu mới (Để trống nếu không đổi)", type="password")
                e_fullname = st.text_input("Họ và Tên", value=cur_u["name"])
                c1, c2, c3 = st.columns(3)
                with c1: e_dept = st.text_input("Bộ phận", value=cur_u["department"])
                with c2: e_pos = st.text_input("Chức vụ", value=cur_u["position"])
                with c3: e_role = st.text_input("Quyền (Role)", value=cur_u["role"])

                st.markdown("**2. Phân quyền truy cập & Thao tác:**")
                e_pages = st.multiselect("Trang truy cập", ALL_FEATURES, default=json.loads(cur_u["allowed_pages"]))
                e_m_perms = st.multiselect("Quyền thiết bị", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=json.loads(cur_u["machine_perms"]))
                e_edits = st.multiselect("Cột được sửa", ALL_MACHINE_EDIT_FIELDS, default=json.loads(cur_u["editable_machine_fields"]))

                if st.form_submit_button("💾 Lưu Thay Đổi Toàn Diện", use_container_width=True):
                    if e_password:
                        is_valid, msg = validate_password_strength(e_password)
                        if not is_valid:
                            show_popup_message("LỖI", msg, "❌")
                            st.stop()
                    
                    conn = get_db_connection()
                    conn.execute("""UPDATE users SET password_hash=?, name=?, department=?, position=?, role=?, allowed_pages=?, machine_perms=?, editable_machine_fields=? WHERE username=?""", 
                                 (hash_password(e_password) if e_password else cur_u["password_hash"], e_fullname, e_dept, e_pos, e_role.strip(), json.dumps(e_pages), json.dumps(e_m_perms), json.dumps(e_edits), target_user))
                    conn.commit()
                    conn.close()

                    if target_user == st.session_state["username"]:
                        st.session_state["user_info"].update({"name": e_fullname, "department": e_dept, "position": e_pos, "role": e_role, "allowed_pages": e_pages, "machine_perms": e_m_perms, "editable_machine_fields": e_edits})

                    log_security_event(st.session_state["username"], f"SỬA USER TOÀN DIỆN ({target_user})", "Thành công")
                    show_popup_message("THÀNH CÔNG", f"Đã cập nhật toàn bộ thông tin cho **{target_user}**!", icon="💾")

        with tab_delete:
            del_user = st.selectbox("Xóa tài khoản", [u["username"] for u in users_db], key="del_u")
            if st.button("🗑️ Xác Nhận Xóa", type="primary", use_container_width=True):
                if del_user == st.session_state["username"]:
                    show_popup_message("LỖI", "Không thể tự xóa bản thân!", icon="🚫")
                else:
                    conn = get_db_connection()
                    conn.execute("DELETE FROM users WHERE username=?", (del_user,))
                    conn.commit()
                    conn.close()
                    log_security_event(st.session_state["username"], f"XÓA USER ({del_user})", "Thành công")
                    show_popup_message("THÀNH CÔNG", f"Đã xóa **{del_user}**!", icon="🗑️")

        with tab_logs:
            st.subheader("🛡️ Nhật ký hoạt động & bảo mật (Audit Logs)")
            conn = get_db_connection()
            logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100").fetchall()
            conn.close()
            if logs:
                st.dataframe(pd.DataFrame([{"ID": l["id"], "Thời gian": l["timestamp"], "Người dùng": l["username"], "Hành động": l["event_type"], "Trạng thái": l["status"]} for l in logs]), use_container_width=True)
            else:
                st.info("Chưa có bản ghi nhật ký nào.")
