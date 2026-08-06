import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date
import calendar

# ==========================================
# CẤU HÌNH TRANG
# ==========================================
st.set_page_config(page_title="Dashboard OEE Toàn Diện", layout="wide", initial_sidebar_state="expanded")

ALL_FEATURES = [
    "🎛️ Dashboard OEE",
    "🏭 Quản Lý Máy Móc",
    "👤 Quản Lý Tài Khoản"
]

ALL_MACHINE_EDIT_FIELDS = [
    "Tên máy",
    "Dây chuyền (Line)",
    "UPH chuẩn",
    "Đường dẫn máy",
    "File mẫu dữ liệu"
]

# CSS NỔI BẬT NÚT TRỞ VỀ TRANG CHỦ & TỐI ƯU GIAO DIỆN
st.markdown("""
    <style>
    div[key="btn_home_nav"] > button {
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        border-radius: 10px !important;
        height: 48px !important;
        box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3) !important;
        transition: all 0.3s ease !important;
        margin-bottom: 20px !important;
    }
    div[key="btn_home_nav"] > button:hover {
        background: linear-gradient(135deg, #0369a1 0%, #075985 100%) !important;
        box-shadow: 0 6px 16px rgba(2, 132, 199, 0.5) !important;
        transform: translateY(-2px);
    }
    
    /* CSS RIÊNG CHO MÀN HÌNH ĐĂNG NHẬP */
    .login-header-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 30px;
        text-align: center;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        margin-bottom: 25px;
    }
    .login-title {
        color: #38bdf8;
        font-size: 2.2rem;
        font-weight: 800;
        margin-bottom: 8px;
        letter-spacing: 0.5px;
    }
    .login-subtitle {
        color: #94a3b8;
        font-size: 1rem;
        margin-bottom: 0;
    }
    .quick-login-card {
        background-color: #0f172a;
        border: 1px dashed #334155;
        border-radius: 12px;
        padding: 15px;
        margin-top: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# HÀM HỖ TRỢ HIỂN THỊ DIALOG/MODAL GIỮA MÀN HÌNH
# ==========================================
@st.dialog("🔔 THÔNG BÁO HỆ THỐNG")
def show_popup_message(title, message, icon="ℹ️"):
    st.markdown(f"### {icon} {title}")
    st.write(message)
    if st.button("Đóng", use_container_width=True, type="primary"):
        st.rerun()

# ==========================================
# HÀM HỖ TRỢ XỬ LÝ FILE DỮ LIỆU MẪU & MÔ PHỎNG
# ==========================================
def load_sample_file_data(uploaded_file):
    try:
        filename = uploaded_file.name.lower()
        if filename.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            engine = 'pyxlsb' if filename.endswith('.xlsb') else 'openpyxl'
            df = pd.read_excel(uploaded_file, engine=engine)
        return df
    except Exception as e:
        st.error(f"Lỗi khi đọc file mẫu: {e}")
        return None

def generate_mock_machine_data(machine_obj, start_date, end_date):
    date_range = pd.date_range(start=start_date, end=end_date)
    data = []
    
    seed_val = sum(ord(c) for c in machine_obj["id"]) + int(start_date.strftime("%d%m%Y"))
    np.random.seed(seed_val)
    
    base_uph = machine_obj.get("uph", 1000)
    
    for d in date_range:
        availability = np.random.uniform(80, 98)
        performance = np.random.uniform(85, 99)
        quality = np.random.uniform(95, 99.9)
        oee = (availability * performance * quality) / 10000
        downtime = round(np.random.uniform(10, 120), 1)
        uph = int(base_uph * np.random.uniform(0.85, 1.05))
        
        data.append({
            "Ngày": d.strftime("%Y-%m-%d"),
            "Mã máy": machine_obj["id"],
            "Tên máy": machine_obj["name"],
            "Dây chuyền": machine_obj["line"],
            "Sẵn sàng (%)": round(availability, 1),
            "Hiệu suất (%)": round(performance, 1),
            "Chất lượng (%)": round(quality, 1),
            "OEE (%)": round(oee, 1),
            "Downtime (Phút)": downtime,
            "Sản lượng UPH": uph
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
# KHỞI TẠO CƠ SỞ DỮ LIỆU
# ==========================================
if "USER_DB" not in st.session_state:
    st.session_state["USER_DB"] = {
        "admin": {
            "password": "123",
            "name": "Giám Đốc Nhà Máy",
            "department": "Ban Giám Đốc",
            "position": "Giám Đốc",
            "role": "Admin",
            "allowed_pages": ALL_FEATURES,
            "machine_perms": ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"],
            "editable_machine_fields": ALL_MACHINE_EDIT_FIELDS
        },
        "manager": {
            "password": "123",
            "name": "Kỹ Sư IE",
            "department": "Kỹ Thuật (IE)",
            "position": "Trưởng Nhóm IE",
            "role": "Manager",
            "allowed_pages": ["🎛️ Dashboard OEE", "🏭 Quản Lý Máy Móc"],
            "machine_perms": ["Xem", "Chỉnh sửa"],
            "editable_machine_fields": ["UPH chuẩn", "Đường dẫn máy"]
        }
    }

if "MACHINE_DB" not in st.session_state:
    st.session_state["MACHINE_DB"] = [
        {
            "id": "M01", 
            "name": "Máy dập Block 1", 
            "line": "G103", 
            "uph": 1200, 
            "url": "http://192.168.1.100/m01", 
            "template_file": "template_oee_g103.xlsx",
            "has_file": True
        },
        {
            "id": "M02", 
            "name": "Máy Test Hipot", 
            "line": "G104", 
            "uph": 800, 
            "url": "http://192.168.1.101/m02", 
            "template_file": "template_oee_g104.csv",
            "has_file": True
        }
    ]

if "selected_menu" not in st.session_state:
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

# Khởi tạo giá trị đăng nhập tạm thời
if "input_user" not in st.session_state:
    st.session_state["input_user"] = ""
if "input_pass" not in st.session_state:
    st.session_state["input_pass"] = ""

# ==========================================
# CÁC HÀM ĐĂNG NHẬP / ĐĂNG XUẤT / CHUYỂN TRANG
# ==========================================
def set_quick_login(user, pwd):
    st.session_state["input_user"] = user
    st.session_state["input_pass"] = pwd

def login():
    # CĂN GIỮA VÀ TẠO KHUNG ĐĂNG NHẬP SANG TRỌNG
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
                username = st.text_input("👤 Tên đăng nhập", value=st.session_state["input_user"], placeholder="Nhập tên đăng nhập (VD: admin)")
                password = st.text_input("🔑 Mật khẩu", value=st.session_state["input_pass"], type="password", placeholder="Nhập mật khẩu")
                
                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    submit_button = st.form_submit_button("🚀 Đăng nhập", use_container_width=True, type="primary")
                with col_btn2:
                    clear_button = st.form_submit_button("🔄 Xóa nhập", use_container_width=True)
                
                if submit_button:
                    if username in st.session_state["USER_DB"] and st.session_state["USER_DB"][username]["password"] == password:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = username
                        st.session_state["user_info"] = st.session_state["USER_DB"][username]
                        st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
                        st.session_state["menu_radio"] = "🎛️ Dashboard OEE"
                        st.toast("🔔 Đăng nhập thành công!", icon="✅")
                        st.rerun()
                    else:
                        st.error("❌ Mật khẩu hoặc tên đăng nhập không chính xác!")
                
                if clear_button:
                    st.session_state["input_user"] = ""
                    st.session_state["input_pass"] = ""
                    st.rerun()

        # KHU VỰC THỬ NGHIỆM ĐĂNG NHẬP NHANH (DEMO ACCOUNTS)
        st.markdown("""
            <div class="quick-login-card">
                <div style="font-weight: 700; color: #38bdf8; margin-bottom: 8px;">⚡ Đăng nhập nhanh (Tài khoản mẫu):</div>
            </div>
        """, unsafe_allow_html=True)
        
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            if st.button("👑 Giám Đốc (Admin)", use_container_width=True):
                set_quick_login("admin", "123")
                st.rerun()
        with col_q2:
            if st.button("👷 Kỹ Sư IE (Manager)", use_container_width=True):
                set_quick_login("manager", "123")
                st.rerun()

        st.markdown("<p style='text-align: center; color: #64748b; font-size: 0.85rem; margin-top: 30px;'>© 2026 Smart Factory Management System | Version 2.4.0</p>", unsafe_allow_html=True)

def logout():
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("user_info", None)
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

def go_home():
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
    st.session_state["menu_radio"] = "🎛️ Dashboard OEE"

# ==========================================
# GIAO DIỆN CHÍNH KHI ĐÃ ĐĂNG NHẬP
# ==========================================
if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
else:
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

        selected_menu = st.radio(
            "📌 ĐIỀU HƯỚNG HỆ THỐNG", 
            user_pages, 
            key="menu_radio"
        )
        
        if selected_menu != st.session_state["selected_menu"]:
            st.session_state["selected_menu"] = selected_menu
            st.rerun()

        st.markdown("---")
        st.button("🚪 Đăng xuất", on_click=logout, use_container_width=True)

    # ---------------------------------------------------------
    # TRANG CHỦ: DASHBOARD OEE
    # ---------------------------------------------------------
    if selected_menu == "🎛️ Dashboard OEE":
        st.markdown("""
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); 
                        padding: 22px; 
                        border-radius: 12px; 
                        text-align: center; 
                        box-shadow: 0 4px 15px rgba(0,0,0,0.2); 
                        margin-bottom: 25px; 
                        border: 1px solid #334155;">
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
            avg_mtbf = int(df_filtered["Sản lượng UPH"].mean() * (avg_avail / 100) / 2.5) if avg_avail > 0 else 0
            avg_mttr = round(total_downtime / max(len(df_filtered), 1), 1)

            st.markdown(f"### ⚙️ 01. Equipment Health Overview <span style='font-size: 1rem; font-weight: normal; color: #64748b;'>({target_display_name} | {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')})</span>", unsafe_allow_html=True)

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)

            with kpi1:
                with st.container(border=True):
                    st.metric(label="Downtime Rate", value=f"{downtime_rate}%", delta="Cập nhật theo lọc", delta_color="inverse")

            with kpi2:
                with st.container(border=True):
                    st.metric(label="Availability (Sẵn sàng)", value=f"{round(avg_avail, 1)}%", delta="Mức trung bình", delta_color="normal")

            with kpi3:
                with st.container(border=True):
                    st.metric(label="MTBF (Chạy TB trước khi hỏng)", value=f"{avg_mtbf} Phút", delta="Ước tính", delta_color="normal")

            with kpi4:
                with st.container(border=True):
                    st.metric(label="MTTR (Thời gian sửa TB)", value=f"{avg_mttr} Phút", delta="TB trạm", delta_color="inverse")

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

                with pie_col:
                    colors = ['#dc2626', '#ea580c', '#2563eb', '#94a3b8']
                    fig_pie = go.Figure(data=[go.Pie(labels=data_4m["labels"], values=data_4m["values"], hole=.4, marker=dict(colors=colors))])
                    fig_pie.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5))
                    st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("🔒 **Hạn chế truy cập:** Bạn đang đăng nhập với quyền Operator. Chỉ xem được thông số tổng quan.")

            st.markdown("---")

            st.markdown(f"### 📈 03. Phân Tích Xu Hướng Dữ Liệu Tự Động Từng Máy ({target_display_name})")
            
            col_chart, col_table = st.columns([6, 4])
            with col_chart:
                fig_line = go.Figure()
                for m_item in filtered_machines:
                    df_sub = df_filtered[df_filtered["Mã máy"] == m_item["id"]]
                    fig_line.add_trace(go.Scatter(
                        x=df_sub["Ngày"], y=df_sub["OEE (%)"],
                        mode='lines+markers', name=f"{m_item['id']} - {m_item['name']}"
                    ))
                fig_line.update_layout(title="Xu hướng Chỉ số OEE (%) Theo Ngày Được Lọc", xaxis_title="Ngày", yaxis_title="OEE (%)", hovermode="x unified")
                st.plotly_chart(fig_line, use_container_width=True)

            with col_table:
                st.markdown("**📋 Bảng tổng hợp chi tiết dữ liệu máy được chọn:**")
                st.dataframe(df_filtered[["Ngày", "Mã máy", "Tên máy", "Dây chuyền", "OEE (%)", "Downtime (Phút)", "Sản lượng UPH"]], use_container_width=True, height=320)

            st.markdown("---")

            current_month = start_date.month
            current_year = start_date.year
            _, last_day = calendar.monthrange(current_year, current_month)
            month_start = date(current_year, current_month, 1)
            month_end = date(current_year, current_month, last_day)

            st.markdown(f"### 🗓️ 04. Biểu Đồ & Bảng Tổng Hợp Xu Hướng Cả Tháng {current_month}/{current_year}")

            month_df_list = []
            for m_item in filtered_machines:
                df_m_month = generate_mock_machine_data(m_item, month_start, month_end)
                month_df_list.append(df_m_month)

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
                    summary_month = df_month.groupby(["Mã máy", "Tên máy", "Dây chuyền"]).agg({
                        "OEE (%)": "mean",
                        "Sẵn sàng (%)": "mean",
                        "Downtime (Phút)": "sum",
                        "Sản lượng UPH": "mean"
                    }).reset_index().round(1)
                    st.dataframe(summary_month, use_container_width=True, height=320)
        else:
            st.warning("⚠️ Không tìm thấy thiết bị nào phù hợp với bộ lọc đã chọn!")

    # ---------------------------------------------------------
    # TRANG 2: QUẢN LÝ MÁY MÓC
    # ---------------------------------------------------------
    elif selected_menu == "🏭 Quản Lý Máy Móc":
        # NÚT VỀ TRANG CHỦ DASHBOARD NỔI BẬT
        st.container(key="btn_home_nav").button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True)

        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ THIẾT BỊ & MÁY MÓC")
        st.markdown("---")

        user_m_perms = current_user.get("machine_perms", ["Xem"])
        user_editable_fields = current_user.get("editable_machine_fields", [])

        tab_m_list, tab_m_add, tab_m_edit, tab_m_delete = st.tabs([
            "📋 Danh Sách Thiết Bị", 
            "➕ Thêm Thiết Bị Mới", 
            "✏️ Chỉnh Sửa Máy", 
            "🗑️ Xóa Máy"
        ])

        # TAB 1: DANH SÁCH MÁY MÓC
        with tab_m_list:
            if "Xem" in user_m_perms:
                if st.session_state["MACHINE_DB"]:
                    m_display = []
                    for m in st.session_state["MACHINE_DB"]:
                        m_display.append({
                            "Mã máy": m.get("id"),
                            "Tên thiết bị": m.get("name"),
                            "Dây chuyền (Line)": m.get("line"),
                            "UPH (Cơ bản)": m.get("uph"),
                            "Đường dẫn tới máy": m.get("url", "Chưa cấu hình"),
                            "File mẫu dữ liệu chuẩn": m.get("template_file", "Chưa nạp file mẫu")
                        })
                    st.dataframe(pd.DataFrame(m_display), use_container_width=True)
                else:
                    st.info("Chưa có thiết bị nào trong cơ sở dữ liệu.")
            else:
                st.error("🔒 Bạn không có quyền **Xem** danh sách máy móc.")

        # TAB 2: THÊM MÁY MÓC MỚI
        with tab_m_add:
            if "Thêm mới" in user_m_perms:
                st.subheader("➕ Thêm máy móc & Nạp file dữ liệu mẫu")
                col1, col2 = st.columns(2)
                with col1:
                    m_id = st.text_input("Mã máy (VD: M04)*")
                    m_name = st.text_input("Tên máy (VD: Máy mài CNC)*")
                    m_line = st.text_input("Dây chuyền (Line)*", placeholder="Tự nhập tên Line (VD: G103, Line-A, SMT-1...)")
                with col2:
                    m_uph = st.number_input("Tốc độ chuẩn - UPH (Sản phẩm/Giờ)", min_value=1, value=100)
                    m_url = st.text_input("Đường dẫn tới máy (URL / IP / Path)", placeholder="http://192.168.1.x/m04")
                    template_file = st.file_uploader("📁 Nạp File Mẫu Chuẩn (.csv, .xlsx, .xlsm, .xlsb)", type=["csv", "xlsx", "xlsm", "xlsb"])

                if st.button("💾 Lưu Thiết Bị Mới", use_container_width=True, type="primary"):
                    if not m_id or not m_name or not m_line:
                        show_popup_message("LỖI NHẬP DỮ LIỆU", "Vui lòng điền đầy đủ **Mã máy**, **Tên máy** và **Dây chuyền (Line)**!", icon="❌")
                    elif any(m["id"] == m_id for m in st.session_state["MACHINE_DB"]):
                        show_popup_message("TRÙNG MÃ MÁY", f"Mã máy `{m_id}` đã tồn tại trên hệ thống!", icon="⚠️")
                    else:
                        t_filename = template_file.name if template_file else "Chưa nạp file mẫu"
                        has_f = True if template_file else False
                        
                        st.session_state["MACHINE_DB"].append({
                            "id": m_id,
                            "name": m_name,
                            "line": m_line.strip(),
                            "uph": m_uph,
                            "url": m_url if m_url else "Chưa cấu hình",
                            "template_file": t_filename,
                            "has_file": has_f
                        })
                        show_popup_message("TẠO MỚI THÀNH CÔNG", f"Đã lưu thành công thiết bị **{m_name} ({m_id})** vào Line **{m_line}**!", icon="🎉")
            else:
                st.error("🔒 Tài khoản của bạn **không có quyền Thêm mới** thiết bị!")

        # TAB 3: CHỈNH SỬA MÁY MÓC
        with tab_m_edit:
            if "Chỉnh sửa" in user_m_perms:
                if st.session_state["MACHINE_DB"]:
                    machine_options = [f"{m['id']} - {m['name']}" for m in st.session_state["MACHINE_DB"]]
                    selected_m_option = st.selectbox("Chọn máy cần chỉnh sửa", machine_options, key="select_edit_m")
                    selected_m_id = selected_m_option.split(" - ")[0]
                    
                    m_idx = next((i for i, m in enumerate(st.session_state["MACHINE_DB"]) if m["id"] == selected_m_id), None)
                    cur_m = st.session_state["MACHINE_DB"][m_idx]

                    st.subheader(f"✏️ Cập nhật thông tin máy: {cur_m['id']}")
                    
                    allowed_fields_str = ", ".join(user_editable_fields) if user_editable_fields else "Không có mục nào"
                    st.info(f"🔑 **Các mục bạn được phép chỉnh sửa:** {allowed_fields_str}")

                    with st.form("form_edit_machine"):
                        can_edit_name = "Tên máy" in user_editable_fields
                        can_edit_line = "Dây chuyền (Line)" in user_editable_fields
                        can_edit_uph = "UPH chuẩn" in user_editable_fields
                        can_edit_url = "Đường dẫn máy" in user_editable_fields
                        can_edit_file = "File mẫu dữ liệu" in user_editable_fields

                        e_m_name = st.text_input("Tên máy", value=cur_m.get("name", ""), disabled=not can_edit_name)
                        e_m_line = st.text_input("Dây chuyền (Line)", value=cur_m.get("line", ""), disabled=not can_edit_line)
                        e_m_uph = st.number_input("UPH chuẩn", min_value=1, value=int(cur_m.get("uph", 100)), disabled=not can_edit_uph)
                        e_m_url = st.text_input("Đường dẫn tới máy", value=cur_m.get("url", ""), disabled=not can_edit_url)
                        
                        st.write(f"File mẫu chuẩn hiện tại: **{cur_m.get('template_file', 'Chưa có file mẫu')}**")
                        e_template_file = st.file_uploader("Thay đổi File mẫu chuẩn mới (Nếu có)", type=["csv", "xlsx", "xlsm", "xlsb"], key="e_template", disabled=not can_edit_file)

                        btn_update_m = st.form_submit_button("💾 Cập Nhật & Lưu Thay Đổi", use_container_width=True)
                        if btn_update_m:
                            new_t_filename = e_template_file.name if (e_template_file and can_edit_file) else cur_m.get("template_file", "Chưa có file mẫu")
                            has_f = True if (e_template_file and can_edit_file) or cur_m.get("has_file") else False

                            st.session_state["MACHINE_DB"][m_idx] = {
                                "id": selected_m_id,
                                "name": e_m_name if can_edit_name else cur_m.get("name"),
                                "line": e_m_line.strip() if can_edit_line else cur_m.get("line"),
                                "uph": e_m_uph if can_edit_uph else cur_m.get("uph"),
                                "url": e_m_url if can_edit_url else cur_m.get("url"),
                                "template_file": new_t_filename,
                                "has_file": has_f
                            }
                            show_popup_message("CẬP NHẬT THÀNH CÔNG", f"Đã lưu các thay đổi cho thiết bị **{selected_m_id}**!", icon="💾")
                else:
                    st.info("Chưa có máy nào để chỉnh sửa.")
            else:
                st.error("🔒 Tài khoản của bạn **không có quyền Chỉnh sửa** máy móc!")

        # TAB 4: XÓA MÁY MÓC
        with tab_m_delete:
            if "Xóa" in user_m_perms:
                if st.session_state["MACHINE_DB"]:
                    st.subheader("🗑️ Xóa thiết bị khỏi hệ thống")
                    machine_del_options = [f"{m['id']} - {m['name']}" for m in st.session_state["MACHINE_DB"]]
                    del_m_option = st.selectbox("Chọn máy cần xóa", machine_del_options, key="select_del_m")
                    del_m_id = del_m_option.split(" - ")[0]
                    
                    m_del_idx = next((i for i, m in enumerate(st.session_state["MACHINE_DB"]) if m["id"] == del_m_id), None)
                    
                    st.warning(f"⚠️ Thao tác này sẽ xóa vĩnh viễn máy **{del_m_id}** khỏi hệ thống.")
                    if st.button("🗑️ Xác Nhận Xóa Thiết Bị", type="primary", use_container_width=True):
                        st.session_state["MACHINE_DB"].pop(m_del_idx)
                        show_popup_message("ĐÃ XÓA THIẾT BỊ", f"Đã xóa vĩnh viễn máy **{del_m_id}** khỏi hệ thống!", icon="🗑️")
                else:
                    st.info("Chưa có máy nào để xóa.")
            else:
                st.error("🔒 Tài khoản của bạn **không có quyền Xóa** thiết bị!")

    # ---------------------------------------------------------
    # TRANG 3: QUẢN LÝ TÀI KHOẢN
    # ---------------------------------------------------------
    elif selected_menu == "👤 Quản Lý Tài Khoản":
        # NÚT VỀ TRANG CHỦ DASHBOARD NỔI BẬT
        st.container(key="btn_home_nav").button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True)

        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ TÀI KHOẢN")
        st.markdown("---")

        tab_list, tab_add, tab_edit, tab_delete = st.tabs([
            "📋 Danh Sách Tài Khoản", 
            "➕ Tạo Mới Tài Khoản", 
            "✏️ Chỉnh Sửa Tài Khoản", 
            "🗑️ Xóa Tài Khoản"
        ])

        # TAB 1: DANH SÁCH
        with tab_list:
            display_data = []
            for uname, uinfo in st.session_state["USER_DB"].items():
                m_perms_str = ", ".join(uinfo.get("machine_perms", []))
                edit_fields_str = ", ".join(uinfo.get("editable_machine_fields", [])) if "Chỉnh sửa" in uinfo.get("machine_perms", []) else "N/A"
                
                display_data.append({
                    "Tài khoản": uname,
                    "Họ và Tên": uinfo.get("name", ""),
                    "Bộ phận": uinfo.get("department", ""),
                    "Chức vụ": uinfo.get("position", ""),
                    "Phân quyền (Role)": uinfo.get("role", ""),
                    "Quyền máy móc": m_perms_str,
                    "Các mục được sửa": edit_fields_str,
                    "Mục được truy cập": ", ".join(uinfo.get("allowed_pages", []))
                })
            st.dataframe(pd.DataFrame(display_data), use_container_width=True)

        # TAB 2: TẠO MỚI TÀI KHOẢN
        with tab_add:
            with st.form("form_add_user"):
                st.subheader("Thêm tài khoản mới vào hệ thống")
                col_a, col_b = st.columns(2)
                with col_a:
                    a_username = st.text_input("Tên tài khoản (viết liền không dấu)*")
                    a_password = st.text_input("Mật khẩu*", type="password")
                    a_fullname = st.text_input("Họ và Tên")
                with col_b:
                    a_dept = st.text_input("Bộ phận", value="Sản Xuất")
                    a_pos = st.text_input("Chức vụ", value="Nhân Viên")
                    a_role = st.text_input("Phân quyền (Role)*", value="Operator", placeholder="Tự nhập quyền (VD: Admin, Manager, Operator, Viewer...)")

                st.markdown("---")
                st.markdown("**1. Quyền được truy cập trang trong phần mềm:**")
                a_pages = st.multiselect("Chọn các trang được phép dùng", ALL_FEATURES, default=["🎛️ Dashboard OEE"])

                st.markdown("**2. Thao tác chi tiết tại Tab Quản Lý Máy Móc:**")
                a_m_perms = st.multiselect("Chọn thao tác máy móc được phép", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=["Xem"])

                st.markdown("**3. Nếu có quyền Chỉnh Sửa máy móc, chọn cụ thể các mục được phép sửa:**")
                a_edit_fields = st.multiselect("Chọn các trường thông tin máy được phép sửa", ALL_MACHINE_EDIT_FIELDS, default=["UPH chuẩn"])

                btn_add = st.form_submit_button("➕ Tạo Tài Khoản Mới", use_container_width=True)
                if btn_add:
                    if not a_username or not a_password:
                        show_popup_message("LỖI ĐĂNG KÝ", "Vui lòng điền **Tên tài khoản** và **Mật khẩu**!", icon="❌")
                    elif a_username in st.session_state["USER_DB"]:
                        show_popup_message("TÀI KHOẢN ĐÃ TỒN TẠI", f"Tài khoản `{a_username}` đã tồn tại trên hệ thống!", icon="⚠️")
                    else:
                        st.session_state["USER_DB"][a_username] = {
                            "password": a_password,
                            "name": a_fullname,
                            "department": a_dept,
                            "position": a_pos,
                            "role": a_role.strip(),
                            "allowed_pages": a_pages,
                            "machine_perms": a_m_perms,
                            "editable_machine_fields": a_edit_fields
                        }
                        show_popup_message("TẠO TÀI KHOẢN THÀNH CÔNG", f"Đã khởi tạo thành công tài khoản **{a_username}**!", icon="👤")

        # TAB 3: CHỈNH SỬA TÀI KHOẢN
        with tab_edit:
            target_user = st.selectbox("Chọn tài khoản cần chỉnh sửa", list(st.session_state["USER_DB"].keys()), key="select_edit_user")
            u_data = st.session_state["USER_DB"][target_user]

            st.subheader(f"✏️ Cập nhật thông tin: {target_user}")
            with st.form("form_edit_user"):
                e_password = st.text_input("Mật khẩu mới", value=u_data.get("password", ""))
                e_fullname = st.text_input("Họ và Tên", value=u_data.get("name", ""))
                e_dept = st.text_input("Bộ phận", value=u_data.get("department", ""))
                e_pos = st.text_input("Chức vụ", value=u_data.get("position", ""))
                e_role = st.text_input("Phân quyền (Role)", value=u_data.get("role", "Operator"))

                st.markdown("---")
                st.markdown("**1. Quyền được truy cập trang trong phần mềm:**")
                e_pages = st.multiselect("Chọn các trang được phép dùng", ALL_FEATURES, default=u_data.get("allowed_pages", []))

                st.markdown("**2. Thao tác chi tiết tại Tab Quản Lý Máy Móc:**")
                e_m_perms = st.multiselect("Chọn thao tác máy móc được phép", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=u_data.get("machine_perms", ["Xem"]))

                st.markdown("**3. Nếu có quyền Chỉnh Sửa máy móc, chọn cụ thể các mục được phép sửa:**")
                e_edit_fields = st.multiselect("Chọn các trường thông tin máy được phép sửa", ALL_MACHINE_EDIT_FIELDS, default=u_data.get("editable_machine_fields", []))

                btn_update = st.form_submit_button("💾 Lưu Thay Đổi", use_container_width=True)
                if btn_update:
                    st.session_state["USER_DB"][target_user] = {
                        "password": e_password,
                        "name": e_fullname,
                        "department": e_dept,
                        "position": e_pos,
                        "role": e_role.strip(),
                        "allowed_pages": e_pages,
                        "machine_perms": e_m_perms,
                        "editable_machine_fields": e_edit_fields
                    }
                    if target_user == st.session_state["username"]:
                        st.session_state["user_info"] = st.session_state["USER_DB"][target_user]
                    show_popup_message("CẬP NHẬT THÀNH CÔNG", f"Đã lưu các thay đổi cho tài khoản **{target_user}**!", icon="💾")

        # TAB 4: XÓA TÀI KHOẢN
        with tab_delete:
            del_user = st.selectbox("Chọn tài khoản cần xóa", list(st.session_state["USER_DB"].keys()), key="select_del_user")
            st.subheader(f"🗑️ Xóa tài khoản: {del_user}")
            st.warning(f"⚠️ Thao tác này không thể hoàn tác với tài khoản **{del_user}**.")
            
            if st.button("🗑️ Xác Nhận Xóa Tài Khoản", type="primary", use_container_width=True):
                if del_user == st.session_state["username"]:
                    show_popup_message("KHÔNG THỂ XÓA", "Bạn không thể xóa tài khoản hiện tại đang đăng nhập!", icon="🚫")
                else:
                    del st.session_state["USER_DB"][del_user]
                    show_popup_message("ĐÃ XÓA TÀI KHOẢN", f"Đã xóa tài khoản **{del_user}** khỏi hệ thống!", icon="🗑️")
