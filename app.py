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
import base64

# ==========================================
# CẤU HÌNH TRANG
# ==========================================
st.set_page_config(
    page_title="Dashboard OEE & Quản Lý Nhà Máy",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

def image_to_base64(uploaded_file):
    if uploaded_file is not None:
        bytes_data = uploaded_file.getvalue()
        encoded = base64.b64encode(bytes_data).decode()
        file_extension = uploaded_file.name.split('.')[-1].lower()
        if file_extension == 'jpg': file_extension = 'jpeg'
        return f"data:image/{file_extension};base64,{encoded}"
    return None

# ==========================================
# KHỞI TẠO BẢNG & DỮ LIỆU MẶC ĐỊNH
# ==========================================
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT,
                    name TEXT,
                    department TEXT,
                    position TEXT,
                    role TEXT,
                    allowed_pages TEXT,
                    machine_perms TEXT,
                    editable_machine_fields TEXT,
                    spare_perms TEXT
                )''')

    try:
        c.execute("ALTER TABLE users ADD COLUMN spare_perms TEXT")
    except sqlite3.OperationalError:
        pass
    
    c.execute('''CREATE TABLE IF NOT EXISTS machines (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    line TEXT,
                    url TEXT,
                    template_file TEXT,
                    has_file INTEGER
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS spare_parts (
                    part_id TEXT PRIMARY KEY,
                    part_name TEXT,
                    category TEXT,
                    model_applicable TEXT,
                    location TEXT,
                    quantity INTEGER,
                    min_quantity INTEGER,
                    unit TEXT,
                    image_url TEXT
                )''')

    try:
        c.execute("ALTER TABLE spare_parts ADD COLUMN image_url TEXT")
    except sqlite3.OperationalError:
        pass

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

    # Bảng yêu cầu xuất kho chờ phê duyệt
    c.execute('''CREATE TABLE IF NOT EXISTS spare_request_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    part_id TEXT,
                    part_name TEXT,
                    quantity_requested INTEGER,
                    requester TEXT,
                    notes TEXT,
                    status TEXT
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    username TEXT,
                    event_type TEXT,
                    status TEXT
                )''')

    default_spare_perms = json.dumps(["Xem", "Giao dịch", "Thêm mới", "Chỉnh sửa", "Phê duyệt"])
    c.execute("SELECT username FROM users WHERE username='admin'")
    if not c.fetchone():
        admin_pass = hash_password("Admin@123")
        c.execute('''INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  ('admin', admin_pass, 'Giám Đốc Nhà Máy', 'Ban Giám Đốc', 'Giám Đốc', 'Admin',
                   json.dumps(ALL_FEATURES), json.dumps(["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"]), json.dumps(ALL_MACHINE_EDIT_FIELDS), default_spare_perms))
        
        manager_pass = hash_password("Manager@123")
        c.execute('''INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  ('manager', manager_pass, 'Kỹ Sư IE', 'Kỹ Thuật (IE)', 'Trưởng Nhóm IE', 'Manager',
                   json.dumps(ALL_FEATURES), json.dumps(["Xem", "Chỉnh sửa"]), json.dumps(["Đường dẫn máy"]), default_spare_perms))
    else:
        c.execute("UPDATE users SET spare_perms = ? WHERE spare_perms IS NULL", (default_spare_perms,))

    c.execute("SELECT count(*) FROM machines")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", ("M01", "Máy dập Block 1", "G103", "http://192.168.1.100/m01", "template_oee_g103.xlsx", 1))
        c.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", ("M02", "Máy Test Hipot", "G104", "http://192.168.1.101/m02", "template_oee_g104.csv", 1))

    c.execute("SELECT count(*) FROM spare_parts")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", ("SP01", "Van điện từ SMC 24V", "Khí nén", "Máy dập Block 1", "Kệ A-01", 12, 5, "Cái", "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=300&q=80"))
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", ("SP02", "Cảm biến quang Omron E3Z", "Cảm biến", "Tất cả", "Kệ A-02", 3, 6, "Cái", "https://images.unsplash.com/photo-1518770660439-4636190af475?w=300&q=80"))
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", ("SP03", "Dây curoa răng 5M-350", "Cơ khí", "Máy Test Hipot", "Kệ B-01", 8, 4, "Sợi", "https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=300&q=80"))
        c.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", ("SP04", "Kim phun keo Dispenser 0.3mm", "Vật tư tiêu hao", "Máy dập Block 1", "Kệ C-05", 2, 10, "Hộp", "https://images.unsplash.com/photo-1581092580497-e0d23cbdf1dc?w=300&q=80"))
        
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
    .highlight-box {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 2px solid #38bdf8;
        border-radius: 12px;
        padding: 20px;
        color: #ffffff;
        box-shadow: 0 8px 20px rgba(56, 189, 248, 0.2);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

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

if "LOGIN_ATTEMPTS" not in st.session_state: st.session_state["LOGIN_ATTEMPTS"] = {}
if "selected_menu" not in st.session_state: st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

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
                                    "machine_perms": json.loads(user['machine_perms']), "editable_machine_fields": json.loads(user['editable_machine_fields']),
                                    "spare_perms": json.loads(user['spare_perms']) if user['spare_perms'] else ["Xem", "Giao dịch"]
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
        with filter_col1: start_date = st.date_input("Từ ngày", date(2026, 8, 1))
        with filter_col2: end_date = st.date_input("Đến ngày", date.today())
        with filter_col3: selected_line = st.selectbox("Dây Chuyền (Line)", line_options)
        with filter_col4: selected_machine_str = st.selectbox("Mã / Tên Thiết Bị", machine_options)
        with filter_col5:
            st.write("")
            st.write("")
            btn_search = st.button("🔎 Phân tích", use_container_width=True, type="primary")

        filtered_machines = machine_db.copy()
        if selected_line != "Tất cả Lines": filtered_machines = [m for m in filtered_machines if m["line"] == selected_line]
        if selected_machine_str != "Tất cả Máy": filtered_machines = [m for m in filtered_machines if m["id"] == selected_machine_str.split(" - ")[0]]

        target_display_name = selected_machine_str if selected_machine_str != "Tất cả Máy" else (selected_line if selected_line != "Tất cả Lines" else "Toàn Nhà Máy")

        if btn_search: show_popup_message("CẬP NHẬT DỮ LIỆU", f"Đã tải thành công dữ liệu phân tích cho: **{target_display_name}**!", icon="📊")
        st.markdown("---")

        all_df_list = [generate_mock_machine_data(m, start_date, end_date) for m in filtered_machines]
        if all_df_list:
            df_filtered = pd.concat(all_df_list, ignore_index=True)
            avg_avail = df_filtered["Sẵn sàng (%)"].mean()
            
            st.markdown(f"### ⚙️ 01. Equipment Health Overview <span style='font-size: 1rem; font-weight: normal; color: #64748b;'>({target_display_name})</span>", unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            with k1: st.markdown(f'''<div class="kpi-card-1"><span style="color: #1e3a8a; font-size: 13px; font-weight: bold;">Downtime Rate</span><h2 style="color: #1d4ed8; margin: 5px 0 0 0;">{round(100 - avg_avail, 1)}%</h2></div>''', unsafe_allow_html=True)
            with k2: st.markdown(f'''<div class="kpi-card-2"><span style="color: #14532d; font-size: 13px; font-weight: bold;">Availability</span><h2 style="color: #15803d; margin: 5px 0 0 0;">{round(avg_avail, 1)}%</h2></div>''', unsafe_allow_html=True)
            with k3: st.markdown(f'''<div class="kpi-card-3"><span style="color: #7f1d1d; font-size: 13px; font-weight: bold;">MTBF</span><h2 style="color: #b91c1c; margin: 5px 0 0 0;">{int(df_filtered["Downtime (Phút)"].mean() * 2)} Phút</h2></div>''', unsafe_allow_html=True)
            with kpi4: st.markdown(f'''<div class="kpi-card-4"><span style="color: #713f12; font-size: 13px; font-weight: bold;">MTTR</span><h2 style="color: #a16207; margin: 5px 0 0 0;">{round(df_filtered["Downtime (Phút)"].sum() / max(len(df_filtered), 1), 1)} Phút</h2></div>''', unsafe_allow_html=True)

    # ---------------------------------------------------------
    # TRANG 2: KHO SPARE PART (TRA CỨU, YÊU CẦU XUẤT KHO & PHÊ DUYỆT)
    # ---------------------------------------------------------
    elif selected_menu == "📦 Kho Spare Part":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## 📦 QUẢN LÝ KHO PHỤ TÙNG & LINH KIỆN (SPARE PARTS)")
        st.markdown("---")

        user_spare_perms = current_user.get("spare_perms", ["Xem", "Giao dịch"])
        conn = get_db_connection()
        sp_data_raw = conn.execute("SELECT * FROM spare_parts").fetchall()
        sp_data = [dict(r) for r in sp_data_raw]
        
        # Đếm số yêu cầu xuất kho đang chờ phê duyệt
        pending_requests = conn.execute("SELECT * FROM spare_request_queue WHERE status = 'CHO_DUYET'").fetchall()
        conn.close()

        low_stock_items = [item for item in sp_data if item["quantity"] <= item["min_quantity"]]
        
        sp_kpi1, sp_kpi2, sp_kpi3, sp_kpi4 = st.columns(4)
        with sp_kpi1: st.markdown(f'''<div class="kpi-card-1"><span style="color: #1e3a8a; font-size: 13px; font-weight: bold;">Tổng Danh Mục</span><h2 style="color: #1d4ed8; margin: 5px 0 0 0;">{len(sp_data)} Loại</h2></div>''', unsafe_allow_html=True)
        with sp_kpi2: st.markdown(f'''<div class="kpi-card-2"><span style="color: #14532d; font-size: 13px; font-weight: bold;">Tổng Tồn Kho</span><h2 style="color: #15803d; margin: 5px 0 0 0;">{sum(i["quantity"] for i in sp_data)} Cái</h2></div>''', unsafe_allow_html=True)
        with sp_kpi3: st.markdown(f'''<div class="kpi-card-3"><span style="color: #7f1d1d; font-size: 13px; font-weight: bold;">Cảnh Báo Thiếu Hàng</span><h2 style="color: #b91c1c; margin: 5px 0 0 0;">{len(low_stock_items)} Loại</h2></div>''', unsafe_allow_html=True)
        with sp_kpi4: st.markdown(f'''<div class="kpi-card-4"><span style="color: #713f12; font-size: 13px; font-weight: bold;">Yêu Cầu Chờ Duyệt</span><h2 style="color: #a16207; margin: 5px 0 0 0;">{len(pending_requests)} Đơn</h2></div>''', unsafe_allow_html=True)
        
        st.markdown("---")
        if low_stock_items:
            st.error(f"⚠️ **CẢNH BÁO TỒN KHO TỐI THIỂU:** Có {len(low_stock_items)} linh kiện đang dưới mức an toàn: " + ", ".join([f"**{i['part_name']}** ({i['quantity']} {i['unit']})" for i in low_stock_items]))

        tab_titles = []
        tab_actions = {}
        if "Xem" in user_spare_perms: tab_titles.append("📋 Tra Cứu & Yêu Cầu Xuất"); tab_actions["list"] = len(tab_titles) - 1
        if "Giao dịch" in user_spare_perms: tab_titles.append("🔄 Xuất / Nhập Trực Tiếp"); tab_actions["tx"] = len(tab_titles) - 1
        if "Phê duyệt" in user_spare_perms or current_user.get("role") == "Admin": 
            tab_titles.append(f"✅ Phê Duyệt ({len(pending_requests)})")
            tab_actions["approve"] = len(tab_titles) - 1
        if "Thêm mới" in user_spare_perms: tab_titles.append("➕ Thêm Mã Phụ Tùng"); tab_actions["add"] = len(tab_titles) - 1
        if "Xem" in user_spare_perms: tab_titles.append("📜 Lịch Sử Giao Dịch"); tab_actions["history"] = len(tab_titles) - 1

        if not tab_titles:
            st.error("🔒 Bạn không có quyền truy cập Kho Spare Part.")
        else:
            tabs = st.tabs(tab_titles)
            
            # TAB 1: TRA CỨU & GỬI YÊU CẦU XUẤT KHO
            if "list" in tab_actions:
                with tabs[tab_actions["list"]]:
                    if sp_data:
                        c_s1, c_s2 = st.columns([3, 1.5])
                        with c_s1: search_kw = st.text_input("🔍 Tra cứu thông tin vật tư", placeholder="Nhập mã, tên, vị trí kệ, thiết bị sử dụng...")
                        with c_s2: categories = ["Tất cả nhóm"] + sorted(list(set([i.get("category", "Khác") for i in sp_data])))
                        selected_cat = st.selectbox("Lọc theo nhóm", categories)

                        filtered_sp = sp_data.copy()
                        if selected_cat != "Tất cả nhóm": filtered_sp = [i for i in filtered_sp if i.get("category") == selected_cat]
                        if search_kw:
                            kw = search_kw.strip().lower()
                            filtered_sp = [i for i in filtered_sp if kw in str(i.get("part_id","")).lower() or kw in str(i.get("part_name","")).lower() or kw in str(i.get("location","")).lower() or kw in str(i.get("model_applicable","")).lower() or kw in str(i.get("category","")).lower()]

                        if filtered_sp:
                            st.caption(f"Tìm thấy **{len(filtered_sp)}/{len(sp_data)}** vật tư phù hợp.")
                            for idx in range(0, len(filtered_sp), 3):
                                cols = st.columns(3)
                                for c_idx, item in enumerate(filtered_sp[idx:idx+3]):
                                    with cols[c_idx]:
                                        with st.container(border=True):
                                            st.image(item.get("image_url") or "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=300&q=80", use_container_width=True)
                                            st.markdown(f"#### {item['part_name']}")
                                            st.markdown(f"🏷️ **Mã:** `{item['part_id']}` | 📂 {item['category']}")
                                            st.markdown(f"📍 **Vị trí kệ:** `{item['location']}` | ⚙️ **Máy:** {item['model_applicable']}")
                                            st.markdown(f"📦 **Tồn kho:** :green[{item['quantity']} {item['unit']}] (Min: {item['min_quantity']})")
                                            
                                            # Nút Gửi yêu cầu xuất kho
                                            with st.popover(f"📤 Gửi yêu cầu xuất: {item['part_id']}", use_container_width=True):
                                                with st.form(f"req_out_{item['part_id']}"):
                                                    st.markdown(f"**Yêu cầu xuất vật tư: {item['part_name']}**")
                                                    req_q = st.number_input("Số lượng cần xuất", min_value=1, max_value=max(1, item['quantity']), value=1)
                                                    req_note = st.text_input("Lý do / Mục đích sử dụng (VD: Thay thế bảo dưỡng định kỳ)")
                                                    if st.form_submit_button("🚀 Gửi Yêu Cầu Phê Duyệt", use_container_width=True, type="primary"):
                                                        if req_q > item['quantity']:
                                                            st.error("Số lượng yêu cầu vượt quá tồn kho hiện tại!")
                                                        else:
                                                            conn = get_db_connection()
                                                            conn.execute("INSERT INTO spare_request_queue (timestamp, part_id, part_name, quantity_requested, requester, notes, status) VALUES (?,?,?,?,?,?,?)",
                                                                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item['part_id'], item['part_name'], req_q, current_user["name"], req_note, "CHO_DUYET"))
                                                            conn.commit()
                                                            conn.close()
                                                            show_popup_message("ĐÃ GỬI YÊU CẦU", f"Yêu cầu xuất **{req_q} {item['unit']}** `{item['part_name']}` đã được gửi đến cấp có thẩm quyền phê duyệt!", "📤")

                                            # Nút Sửa nhanh nếu có quyền
                                            if "Chỉnh sửa" in user_spare_perms:
                                                with st.popover(f"✏️ Sửa thông tin: {item['part_id']}", use_container_width=True):
                                                    with st.form(f"qe_{item['part_id']}"):
                                                        q_name = st.text_input("Tên", value=item['part_name'])
                                                        q_cat = st.text_input("Nhóm", value=item['category'])
                                                        q_model = st.text_input("Máy", value=item['model_applicable'])
                                                        q_loc = st.text_input("Kệ", value=item['location'])
                                                        q_min = st.number_input("Min", min_value=1, value=int(item['min_quantity']))
                                                        q_unit = st.text_input("ĐVT", value=item['unit'])
                                                        q_img = st.file_uploader("Đổi ảnh", type=["png","jpg","jpeg"], key=f"i_{item['part_id']}")
                                                        if st.form_submit_button("💾 Lưu Ngay", use_container_width=True, type="primary"):
                                                            img_db = image_to_base64(q_img) if q_img else item.get("image_url")
                                                            conn = get_db_connection()
                                                            conn.execute("UPDATE spare_parts SET part_name=?, category=?, model_applicable=?, location=?, min_quantity=?, unit=?, image_url=? WHERE part_id=?", (q_name, q_cat, q_model, q_loc, q_min, q_unit, img_db, item['part_id']))
                                                            conn.commit()
                                                            conn.close()
                                                            show_popup_message("THÀNH CÔNG", f"Đã cập nhật {item['part_id']}!", "💾")
                        else:
                            st.warning("⚠️ Không tìm thấy vật tư nào phù hợp!")
                    else:
                        st.info("Chưa có dữ liệu linh kiện trong kho.")

            # TAB 2: XUẤT / NHẬP TRỰC TIẾP
            if "tx" in tab_actions:
                with tabs[tab_actions["tx"]]:
                    if sp_data:
                        st.subheader("Giao Dịch Xuất / Nhập Kho Trực Tiếp")
                        with st.form("tx_form"):
                            t_opt = st.selectbox("Phụ tùng", [f"{i['part_id']} - {i['part_name']} (Tồn: {i['quantity']})" for i in sp_data])
                            t_id = t_opt.split(" - ")[0]
                            t_act = st.radio("Thao tác", ["📥 Nhập Kho (+)", "📤 Xuất Kho (-)"], horizontal=True)
                            t_q = st.number_input("Số lượng", min_value=1, value=1)
                            t_n = st.text_input("Ghi chú")
                            if st.form_submit_button("Xác nhận", type="primary", use_container_width=True):
                                cur = next(i for i in sp_data if i["part_id"] == t_id)
                                cur_q = cur["quantity"]
                                if "📤" in t_act and t_q > cur_q:
                                    show_popup_message("LỖI", "Số lượng xuất vượt quá tồn kho!", "❌")
                                else:
                                    new_q = cur_q + t_q if "📥" in t_act else cur_q - t_q
                                    conn = get_db_connection()
                                    conn.execute("UPDATE spare_parts SET quantity=? WHERE part_id=?", (new_q, t_id))
                                    conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), t_id, "NHAP" if "📥" in t_act else "XUAT", t_q, new_q, current_user["name"], t_n))
                                    conn.commit()
                                    conn.close()
                                    show_popup_message("THÀNH CÔNG", f"Tồn kho mới: {new_q} {cur['unit']}", "📦")

            # TAB 3: PHÊ DUYỆT YÊU CẦU XUẤT KHO
            if "approve" in tab_actions:
                with tabs[tab_actions["approve"]]:
                    st.subheader("✅ Danh Sách Yêu Cầu Xuất Kho Chờ Phê Duyệt")
                    conn = get_db_connection()
                    queue_list = conn.execute("SELECT * FROM spare_request_queue WHERE status = 'CHO_DUYET' ORDER BY id DESC").fetchall()
                    conn.close()

                    if queue_list:
                        for req in queue_list:
                            with st.container(border=True):
                                r_cols = st.columns([3, 2, 2])
                                with r_cols[0]:
                                    st.markdown(f"**Vật tư:** `{req['part_id']}` - **{req['part_name']}**")
                                    st.markdown(f"📦 **Số lượng xin xuất:** `{req['quantity_requested']}`")
                                with r_cols[1]:
                                    st.markdown(f"👤 **Người yêu cầu:** {req['requester']}")
                                    st.markdown(f"🕒 **Thời gian:** {req['timestamp']}")
                                with r_cols[2]:
                                    st.markdown(f"📝 **Lý do:** {req['notes']}")
                                    
                                btn_c1, btn_c2 = st.columns(2)
                                with btn_c1:
                                    if st.button("✅ Phê Duyệt", key=f"app_{req['id']}", use_container_width=True, type="primary"):
                                        # Kiểm tra tồn kho thực tế trước khi duyệt
                                        conn = get_db_connection()
                                        p_item = conn.execute("SELECT * FROM spare_parts WHERE part_id = ?", (req['part_id'],)).fetchone()
                                        if p_item and p_item['quantity'] >= req['quantity_requested']:
                                            new_qty = p_item['quantity'] - req['quantity_requested']
                                            conn.execute("UPDATE spare_parts SET quantity = ? WHERE part_id = ?", (new_qty, req['part_id']))
                                            conn.execute("UPDATE spare_request_queue SET status = 'DA_DUYET' WHERE id = ?", (req['id'],))
                                            conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), req['part_id'], "XUAT", req['quantity_requested'], f"{current_user['name']} (Duyệt cho {req['requester']})", req['notes']))
                                            conn.commit()
                                            conn.close()
                                            show_popup_message("PHÊ DUYỆT THÀNH CÔNG", f"Đã duyệt xuất kho cho đơn hàng **#{req['id']}**!", "✅")
                                        else:
                                            conn.close()
                                            show_popup_message("LỖI PHÊ DUYỆT", "Tồn kho không đủ để đáp ứng yêu cầu xuất này!", "❌")
                                with btn_c2:
                                    if st.button("❌ Từ Chối", key=f"rej_{req['id']}", use_container_width=True):
                                        conn = get_db_connection()
                                        conn.execute("UPDATE spare_request_queue SET status = 'TU_CHOI' WHERE id = ?", (req['id'],))
                                        conn.commit()
                                        conn.close()
                                        show_popup_message("ĐÃ TỪ CHỐI", f"Đã từ chối đơn hàng **#{req['id']}**.", "🚫")
                    else:
                        st.info("Hiện không có yêu cầu xuất kho nào đang chờ phê duyệt.")

            # TAB 4: THÊM MÃ PHỤ TÙNG MỚI
            if "add" in tab_actions:
                with tabs[tab_actions["add"]]:
                    with st.form("add_sp_form"):
                        n_id = st.text_input("Mã phụ tùng*")
                        n_name = st.text_input("Tên phụ tùng*")
                        n_cat = st.text_input("Nhóm", value="Cơ khí")
                        n_mod = st.text_input("Máy áp dụng", value="Tất cả")
                        n_loc = st.text_input("Vị trí kệ", value="Kệ A")
                        n_qty = st.number_input("Tồn ban đầu", min_value=0, value=10)
                        n_min = st.number_input("Tồn tối thiểu", min_value=1, value=5)
                        n_unit = st.text_input("ĐVT", value="Cái")
                        n_file = st.file_uploader("Hình ảnh", type=["png","jpg","jpeg"])
                        if st.form_submit_button("Lưu mới", type="primary", use_container_width=True):
                            if not n_id or not n_name: show_popup_message("LỖI", "Nhập đủ Mã và Tên!", "❌")
                            else:
                                img_save = image_to_base64(n_file) if n_file else "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=300&q=80"
                                conn = get_db_connection()
                                conn.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", (n_id, n_name, n_cat, n_mod, n_loc, n_qty, n_min, n_unit, img_save))
                                conn.commit()
                                conn.close()
                                show_popup_message("THÀNH CÔNG", f"Đã thêm {n_name}!", "🎉")

            # TAB 5: LỊCH SỬ GIAO DỊCH
            if "history" in tab_actions:
                with tabs[tab_actions["history"]]:
                    conn = get_db_connection()
                    logs = conn.execute("SELECT * FROM spare_part_logs ORDER BY id DESC LIMIT 100").fetchall()
                    conn.close()
                    if logs: st.dataframe(pd.DataFrame([dict(l) for l in logs]), use_container_width=True)
                    else: st.info("Chưa có lịch sử.")

    # ---------------------------------------------------------
    # TRANG 3: QUẢN LÝ MÁY MÓC
    # ---------------------------------------------------------
    elif selected_menu == "🏭 Quản Lý Máy Móc":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ THIẾT BỊ")
        st.markdown("---")
        user_m_perms = current_user.get("machine_perms", ["Xem"])
        if "Xem" in user_m_perms and machine_db: st.dataframe(pd.DataFrame(machine_db), use_container_width=True)

    # ---------------------------------------------------------
    # TRANG 4: QUẢN LÝ TÀI KHOẢN
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
            st.subheader("📋 Danh Sách Người Dùng & Quyền Hạn Chi Tiết")
            display_data = []
            for u in users_db:
                pages_list = json.loads(u["allowed_pages"]) if u["allowed_pages"] else []
                display_data.append({
                    "Tài khoản": u["username"], "Họ và Tên": u["name"],
                    "Bộ phận": u["department"], "Chức vụ": u["position"],
                    "Quyền (Role)": u["role"], "Các mục được truy cập": ", ".join(pages_list)
                })
            st.dataframe(pd.DataFrame(display_data), use_container_width=True)

            st.markdown("---")
            st.markdown("### 🔍 Xem Nổi Bật Thông Tin & Quyền Hạn Tài Khoản")
            selected_highlight_user = st.selectbox("Chọn tài khoản để xem chi tiết nổi bật", [u["username"] for u in users_db])
            if selected_highlight_user:
                sel_u_obj = next(u for u in users_db if u["username"] == selected_highlight_user)
                p_list = json.loads(sel_u_obj["allowed_pages"]) if sel_u_obj["allowed_pages"] else []
                m_perms = json.loads(sel_u_obj["machine_perms"]) if sel_u_obj["machine_perms"] else []
                s_perms = json.loads(sel_u_obj["spare_perms"]) if sel_u_obj["spare_perms"] else []

                st.markdown(f"""
                    <div class="highlight-box">
                        <h3 style="color: #38bdf8; margin-top: 0;">👤 Tài khoản: {sel_u_obj['username'].upper()} ({sel_u_obj['name']})</h3>
                        <p><b>🏢 Bộ phận:</b> {sel_u_obj['department']} &nbsp;|&nbsp; <b>💼 Chức vụ:</b> {sel_u_obj['position']} &nbsp;|&nbsp; <b>🔑 Phân quyền:</b> {sel_u_obj['role']}</p>
                        <hr style="border-color: #334155;">
                        <p><b>📌 Các mục phần mềm được truy cập:</b> <span style="color: #34d399;">{", ".join(p_list)}</span></p>
                        <p><b>⚙️ Quyền quản lý máy móc:</b> {", ".join(m_perms)}</p>
                        <p><b>📦 Quyền chi tiết kho Spare Part:</b> {", ".join(s_perms)}</p>
                    </div>
                """, unsafe_allow_html=True)

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
                a_m_perms = st.multiselect("Quyền thiết bị (Máy móc)", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=["Xem"])
                a_edit_fields = st.multiselect("Cột máy được sửa", ALL_MACHINE_EDIT_FIELDS, default=["Đường dẫn máy"])
                a_spare_perms = st.multiselect("Quyền chi tiết Kho Spare Part", ["Xem", "Giao dịch", "Thêm mới", "Chỉnh sửa", "Phê duyệt"], default=["Xem", "Giao dịch"])

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
                            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)", 
                                        (a_username.lower(), hash_password(a_password), a_fullname, a_dept, a_pos, a_role.strip(), json.dumps(a_pages), json.dumps(a_m_perms), json.dumps(a_edit_fields), json.dumps(a_spare_perms)))
                            conn.commit()
                            conn.close()
                            log_security_event(st.session_state["username"], f"TẠO USER ({a_username})", "Thành công")
                            show_popup_message("THÀNH CÔNG", f"Đã tạo tài khoản **{a_username}**!", icon="👤")

        with tab_edit:
            target_user = st.selectbox("Chọn tài khoản cần sửa", [u["username"] for u in users_db], key="sel_edit_u")
            cur_u = next(u for u in users_db if u["username"] == target_user)
            with st.form("form_edit_user"):
                st.markdown("**1. Thông tin cơ bản:**")
                e_password = st.text_input("Mật khẩu mới (Để trống nếu không đổi)", type="password")
                e_fullname = st.text_input("Họ và Tên", value=cur_u["name"])
                c1, c2, c3 = st.columns(3)
                with c1: e_dept = st.text_input("Bộ phận", value=cur_u["department"])
                with c2: e_pos = st.text_input("Chức vụ", value=cur_u["position"])
                with c3: e_role = st.text_input("Quyền (Role)", value=cur_u["role"])

                st.markdown("**2. Phân quyền chi tiết:**")
                e_pages = st.multiselect("Trang truy cập", ALL_FEATURES, default=json.loads(cur_u["allowed_pages"]))
                e_m_perms = st.multiselect("Quyền thiết bị (Máy móc)", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=json.loads(cur_u["machine_perms"]))
                e_edits = st.multiselect("Cột máy được sửa", ALL_MACHINE_EDIT_FIELDS, default=json.loads(cur_u["editable_machine_fields"]))
                
                cur_spare_p = json.loads(cur_u["spare_perms"]) if cur_u["spare_perms"] else ["Xem", "Giao dịch"]
                e_spare_perms = st.multiselect("Quyền chi tiết Kho Spare Part", ["Xem", "Giao dịch", "Thêm mới", "Chỉnh sửa", "Phê duyệt"], default=cur_spare_p)

                if st.form_submit_button("💾 Lưu Thay Đổi Toàn Diện", use_container_width=True):
                    if e_password:
                        is_valid, msg = validate_password_strength(e_password)
                        if not is_valid:
                            show_popup_message("LỖI", msg, icon="❌")
                            st.stop()
                    
                    conn = get_db_connection()
                    conn.execute("""UPDATE users SET password_hash=?, name=?, department=?, position=?, role=?, allowed_pages=?, machine_perms=?, editable_machine_fields=?, spare_perms=? WHERE username=?""", 
                                 (hash_password(e_password) if e_password else cur_u["password_hash"], e_fullname, e_dept, e_pos, e_role.strip(), json.dumps(e_pages), json.dumps(e_m_perms), json.dumps(e_edits), json.dumps(e_spare_perms), target_user))
                    conn.commit()
                    conn.close()

                    if target_user == st.session_state["username"]:
                        st.session_state["user_info"].update({"name": e_fullname, "department": e_dept, "position": e_pos, "role": e_role, "allowed_pages": e_pages, "machine_perms": e_m_perms, "editable_machine_fields": e_edits, "spare_perms": e_spare_perms})

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
