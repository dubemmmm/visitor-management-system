import streamlit as st
import psycopg2
import random
import string
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# Load environment variables
if os.getenv("RENDER") is None: # RENDER is an automatic env var in Render
    load_dotenv()
# App name
APP_NAME = "SecureVisit"

# Database Connection
DATABASE_URL = os.getenv("DATABASE_URL")
# Authenticated Credentials
ADMIN_USERS = {
    os.environ.get("ADMIN1_USERNAME", "admin1"): {
        "password": os.environ.get("ADMIN1_PASSWORD", "change_me_immediately"),
        "display_name": "Receptionist"
    }
}
SECURITY_USERS = {
    os.environ.get("SECURITY_USERNAME", "security"): os.environ.get("SECURITY_PASSWORD", "change_me_immediately")
}
# Add more admin users from environment variables if they exist
for i in range(2, 4):  # Support up to 3 admin users from env variables
    username_key = f"ADMIN{i}_USERNAME"
    password_key = f"ADMIN{i}_PASSWORD"
    display_name_key = f"ADMIN{i}_DISPLAY_NAME"
    
    if os.environ.get(username_key) and os.environ.get(password_key):
        ADMIN_USERS[os.environ.get(username_key)] = {
            "password": os.environ.get(password_key),
            "display_name": os.environ.get(display_name_key, f"Admin User {i}")
        }

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

# Initialize Database
def init_db():
    """Initialize the PostgreSQL database with the required tables."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_codes (
            code TEXT PRIMARY KEY,
            visitor_name TEXT NOT NULL,
            visit_host TEXT NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            location TEXT NOT NULL,
            generated_by TEXT NOT NULL,
            generation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used BOOLEAN DEFAULT FALSE
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def generate_code():
    """Generate a unique 7-digit code that doesn't already exist in the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    while True:
        code = ''.join(random.choices(string.digits, k=7))
        cur.execute("SELECT 1 FROM access_codes WHERE code = %s", (code,))
        if not cur.fetchone():  # If code does not exist, break the loop
            break
    
    cur.close()
    conn.close()
    return code

def save_code_to_db(code, visitor_name, visit_host, start_time, end_time, location, generated_by):
    """Save a new access code to the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO access_codes (code, visitor_name, visit_host, start_time, end_time, location, generated_by) 
        VALUES (%s, %s, %s, %s, %s, %s, %s);
    """, (code, visitor_name, visit_host, start_time, end_time, location, generated_by))
    
    conn.commit()
    cur.close()
    conn.close()

def get_all_codes(include_expired=True, days_to_keep=7, filter_date=None):
    """Retrieve all access codes from the database, with optional filtering."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM access_codes"
    params = []
    where_clauses = []
    
    if not include_expired:
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
        where_clauses.append("generation_timestamp >= %s")
        params.append(cutoff_date)
    
    if filter_date:
        where_clauses.append("DATE(generation_timestamp) = %s")
        params.append(filter_date)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    codes = []
    current_time = datetime.now().time()
    current_date = datetime.now().date()
    
    for row in rows:
        code, visitor_name, visit_host, start_time_str, end_time_str, location, generated_by, timestamp, used = row
        #start_time = datetime.strptime(start_time_str, "%H:%M").time()
        #end_time = datetime.strptime(end_time_str, "%H:%M").time()
        end_time = end_time_str
        timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S") 
        generation_date = datetime.strptime(timestamp.split()[0], "%Y-%m-%d").date()

        # If the code was generated today, check if it's still active
        is_active = False
        if generation_date == current_date and end_time > current_time:
            is_active = True
            
        codes.append({
            "code": code,
            "visitor_name": visitor_name,
            "visit_host": visit_host,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "location": location,
            "generated_by": generated_by,
            "timestamp": timestamp,
            "is_active": is_active,
            "used": bool(used)
        })

    return codes

def remove_expired_codes():
    """Remove expired access codes from the database older than 30 days."""
    cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM access_codes WHERE generation_timestamp < %s", (cutoff_date,))
    conn.commit()
    cur.close()
    conn.close()

def is_code_valid(code):
    """Check if the code exists and is still valid."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM access_codes WHERE code = %s", (code,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        code, visitor_name, visit_host, start_time, end_time, location, generated_by, timestamp, used = row
        current_time = datetime.now().time()
        current_date = datetime.now().date()

        if timestamp.date() == current_date and start_time <= current_time <= end_time:
            return True, {
                "visitor_name": visitor_name, 
                "visit_host": visit_host, 
                "start_time": start_time, 
                "end_time": end_time,
                "location": location,
                "generated_by": generated_by,
                "used": used
            }
    
    return False, None

def mark_code_as_used(code):
    """Mark a code as used in the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE access_codes SET used = TRUE WHERE code = %s", (code,))
    conn.commit()
    cur.close()
    conn.close()

# Initialize the database
init_db()

# Remove expired codes
remove_expired_codes()

# Streamlit App
st.set_page_config(page_title=f"{APP_NAME} - Visitor Access System", layout="centered")

# App header with logo styling
st.markdown(f"""
    <div style='text-align: center; background-color: #f0f2f6; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;'>
        <h1 style='color: #1E88E5;'>{APP_NAME}</h1>
        <p style='font-style: italic;'>Secure Visitor Management System</p>
    </div>
""", unsafe_allow_html=True)

# Custom CSS for status indicators
st.markdown("""
<style>
.status-active {
    color: white;
    background-color: #28a745;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: bold;
}
.status-inactive {
    color: white;
    background-color: #dc3545;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: bold;
}
.status-used {
    color: white;
    background-color: #6c757d;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: bold;
}
.status-unused {
    color: white;
    background-color: #17a2b8;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)


# Tabs
tab1, tab2 = st.tabs(["🔑 Generate Code", "✅ Verify Code"])

# ---------------------- TAB 1: Code Generation ----------------------
with tab1:
    st.header("🔑 Generate Access Code")

    # Authentication for code generation
    if st.session_state.get("auth_section") != "generate":
        st.subheader("Login to Generate Codes")
        username = st.text_input("Username", key="gen_username")
        password = st.text_input("Password", type="password", key="gen_password")
        if st.button("Login", key="gen_login"):
            if username in ADMIN_USERS and ADMIN_USERS[username]["password"] == password:
                st.session_state["auth_section"] = "generate"
                st.session_state["current_admin"] = username
                st.session_state["admin_display_name"] = ADMIN_USERS[username]["display_name"]
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid credentials")

    if st.session_state.get("auth_section") == "generate":
        st.info(f"Logged in as: {st.session_state.get('admin_display_name')}")
        st.subheader("Generate a Visitor Code")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Visitor information
            visitor_name = st.text_input("Visitor's Full Name")
            visit_host = st.text_input("Person to Visit")
            location = st.text_input("Location", value="10B1 Sarumoh Oladosu Close, Lekki Phase 1, Lagos State")
        
        with col2:
            # Date selection
            visit_date = st.date_input("Visit Date", value=datetime.now())
            
            # Start and end time inputs
            start_time = st.time_input("Start Time")
            end_time = st.time_input("End Time")

        # Generate code button
        if st.button("Generate Code", key="generate_btn") and visitor_name and visit_host:
            if end_time <= start_time:
                st.error("End time must be later than start time!")
            else:
                new_code = generate_code()
                generated_by = st.session_state.get("admin_display_name")
                save_code_to_db(new_code, visitor_name, visit_host, start_time, end_time, location, generated_by)

                formatted_date = visit_date.strftime("%d/%m/%Y")
                formatted_start = start_time.strftime("%I:%M %p")
                formatted_end = end_time.strftime("%I:%M %p")
                
                # Format according to the specifications
                st.markdown("### Generated Access Code")
                code_display = f"""
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 10px; border-left: 5px solid #1E88E5;">
                <p>Hi {visitor_name},</p>
                <p>Your one-time code is: <b style="font-size: 1.2em; color: #1E88E5;">{new_code}</b></p>
                <p><b>Location:</b> {location}</p>
                <p><b>From:</b> {formatted_date}, {formatted_start}</p>
                <p><b>To:</b> {formatted_date}, {formatted_end}</p>
                <p><b>Generated by:</b> {generated_by}</p>
                <hr>
                <p style="font-size: 0.8em; text-align: center;">Powered by {APP_NAME}</p>
                </div>
                """
                st.markdown(code_display, unsafe_allow_html=True)
                
                # Provide plain text version for copying
                with st.expander("Copy Plain Text Version"):
                    plain_text = f"""
Hi {visitor_name},
Your one-time code is: {new_code}
Location: {location}
From: {formatted_date}, {formatted_start}
To: {formatted_date}, {formatted_end}
Generated by: {generated_by}
Powered by {APP_NAME}
                    """
                    st.code(plain_text, language="")

        # Logout button
        if st.button("Logout", key="gen_logout"):
            st.session_state["auth_section"] = None
            st.session_state.pop("current_admin", None)
            st.session_state.pop("admin_display_name", None)
            st.rerun()
            
        # Display all codes (both active and inactive) with status
        with st.expander("Admin: View All Access Codes"):
            # Add date filter
            st.subheader("Filter Options")
            col1, col2 = st.columns(2)
            
            with col1:
                filter_by_date = st.checkbox("Filter by date")
            
            with col2:
                if filter_by_date:
                    selected_date = st.date_input("Select date", value=datetime.now(), key="filter_date")
                    filter_date_str = selected_date.strftime("%Y-%m-%d")
                else:
                    filter_date_str = None
            
            # Get codes with date filter
            all_codes = get_all_codes(include_expired=True, filter_date=filter_date_str)
            
            if all_codes:
                # Convert to a format suitable for display with status indicators
                st.markdown("### All Access Codes")
                
                # Create dataframe-ready list with status column
                display_codes = []
                for code in all_codes:
                    # Format the status with HTML for color
                    status_html = f"<span class='status-active'>ACTIVE</span>" if code["is_active"] else f"<span class='status-inactive'>INACTIVE</span>"
                    used_html = f"<span class='status-used'>USED</span>" if code["used"] else f"<span class='status-unused'>UNUSED</span>"
                    
                    display_codes.append({
                        "Code": code["code"],
                        "Visitor": code["visitor_name"],
                        "Host": code["visit_host"],
                        "End Time": code["end_time"],
                        "Status": status_html,
                        "Used": used_html,
                        "Generated By": code["generated_by"],
                        "Date": code["timestamp"].split()[0]
                    })
                
                # Sort by status (active first) then by timestamp
                display_codes.sort(key=lambda x: (not "ACTIVE" in x["Status"], x["Date"]), reverse=True)
                
                # Use DataFrame for better display and sorting
                df = pd.DataFrame(display_codes)
                
                # Display the table with HTML for colored status
                st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.write("No codes found.")
            
            # Add a refresh button for the admin panel
            if st.button("Refresh List"):
                st.rerun()

# ---------------------- TAB 2: Code Verification ----------------------
with tab2:
    st.header("✅ Verify Access Code")
    
    # Authentication for verification
    if st.session_state.get("auth_section") != "verify":
        st.subheader("Login to Verify Codes")
        username = st.text_input("Username", key="verify_username")
        password = st.text_input("Password", type="password", key="verify_password")
        if st.button("Login", key="verify_login"):
            if username in SECURITY_USERS and SECURITY_USERS[username] == password:
                st.session_state["auth_section"] = "verify"
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid credentials")
    
    if st.session_state.get("auth_section") == "verify":
        st.subheader("Enter Visitor Code")
        code_input = st.text_input("7-digit Code", max_chars=7)
        
        if st.button("Verify Code", key="verify_btn"):
            if not code_input:
                st.warning("Please enter a code")
            else:
                is_valid, entry = is_code_valid(code_input)
                if is_valid:
                    # Check if already used
                    already_used = entry.get('used', False)
                    status_message = "✅ APPROVED: The code is valid!"
                    
                    if already_used:
                        status_message += " (Note: This code has been used before)"
                    
                    st.success(status_message)
                    
                    # Mark code as used
                    mark_code_as_used(code_input)
                    
                    # Format the verification result
                    st.markdown(f"""
                    <div style="background-color: #e7f7e7; padding: 20px; border-radius: 10px; border-left: 5px solid #28a745;">
                    <h3>Visitor Information</h3>
                    <p><b>Visitor:</b> {entry['visitor_name']}</p>
                    <p><b>Visiting:</b> {entry['visit_host']}</p>
                    <p><b>Location:</b> {entry['location']}</p>
                    <p><b>Valid from:</b> {entry['start_time'].strftime('%I:%M %p')}</p>
                    <p><b>Valid until:</b> {entry['end_time'].strftime('%I:%M %p')}</p>
                    <p><b>Generated by:</b> {entry['generated_by']}</p>
                    <p><b>Usage status:</b> {"Previously used" if already_used else "First use"}</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Try to find if code exists but is expired
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM access_codes WHERE code = ?", (code_input,))
                    row = cur.fetchone()
                    conn.close()
                    
                    if row:
                        st.error("❌ CODE EXPIRED: This code is no longer valid")
                    else:
                        st.error("❌ INVALID CODE: This code does not exist")
        
        # Logout button
        if st.button("Logout", key="verify_logout"):
            st.session_state["auth_section"] = None
            st.rerun()



