import os
import time
import urllib.parse
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pymongo import MongoClient

app = Flask(__name__)
# مفتاح سري لتشفير الجلسات
app.secret_key = os.urandom(32).hex()

# إعدادات المجلدات لرفع الصور
UPLOAD_BASE = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
os.makedirs(UPLOAD_BASE, exist_ok=True)

# ==========================================
# إعدادات MongoDB Atlas (تم حل مشكلة الرموز المعقدة)
# ==========================================
# استخدام urllib لتشفير الباسورد الذي يحتوي على رمز @ لتجنب الأخطاء
username = urllib.parse.quote_plus('ahmedosman')
password = urllib.parse.quote_plus('i-fn@bBHV7rXMYj')

# الرابط السليم بعد التشفير
MONGO_URI = f"mongodb+srv://{username}:{password}@cluster0.8wawfsu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

try:
    client = MongoClient(MONGO_URI)
    db = client['photographer_portfolio']
    categories_col = db['categories']
    settings_col = db['settings']
    # اختبار الاتصال
    client.admin.command('ping')
    print("تم الاتصال بـ MongoDB بنجاح! الباسورد سليم 100%")
except Exception as e:
    print(f"فشل الاتصال بـ MongoDB: {e}")

# بيانات دخول لوحة الإدارة
ADMIN_USERNAME = "Admin"
ADMIN_PASSWORD_HASH = generate_password_hash("Ahmed123") # كلمة المرور للدخول هي: Ahmed123

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_main_banner():
    doc = settings_col.find_one({"_id": "main_banner"})
    return doc.get("filename", "") if doc else ""

# ==========================================
# 1. واجهة الزوار (الرئيسية والأقسام)
# ==========================================
@app.route('/')
def index():
    categories = list(categories_col.find())
    return render_template('index.html', categories=categories, banner=get_main_banner())

@app.route('/category/<cat_id>')
def category_view(cat_id):
    cat_info = categories_col.find_one({"_id": cat_id})
    if not cat_info:
        return redirect(url_for('index'))
    return render_template('category.html', cat_id=cat_id, cat_info=cat_info, images=cat_info.get("images", []), banner=get_main_banner())

# ==========================================
# 2. نظام تسجيل الدخول
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_logged_in'] = True
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "بيانات الدخول غير صحيحة"}), 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

# ==========================================
# 3. لوحة الإدارة (الأدمن)
# ==========================================
@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    categories = list(categories_col.find())
    return render_template('admin.html', categories=categories, banner=get_main_banner())

# تحديث البانر الرئيسي (الهيدر)
@app.route('/admin/update_banner', methods=['POST'])
def update_banner():
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    file = request.files.get('banner_image')
    if file and allowed_file(file.filename):
        filename = f"banner_{int(time.time())}_{secure_filename(file.filename)}"
        file.save(os.path.join(UPLOAD_BASE, filename))
        
        old_banner = get_main_banner()
        if old_banner and os.path.exists(os.path.join(UPLOAD_BASE, old_banner)):
            try: os.remove(os.path.join(UPLOAD_BASE, old_banner))
            except: pass
            
        settings_col.update_one({"_id": "main_banner"}, {"$set": {"filename": filename}}, upsert=True)
        flash('تم تحديث صورة الهيدر بنجاح!', 'success')
    return redirect(url_for('admin'))

# إضافة ألبوم جديد
@app.route('/admin/add_category', methods=['POST'])
def add_category():
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    cat_name = request.form.get('cat_name')
    file = request.files.get('cover_image')
    
    if cat_name and file and allowed_file(file.filename):
        cat_id = f"cat_{int(time.time())}"
        cat_path = os.path.join(UPLOAD_BASE, cat_id)
        os.makedirs(cat_path, exist_ok=True)
        
        cover_name = f"cover_{int(time.time())}_{secure_filename(file.filename)}"
        file.save(os.path.join(cat_path, cover_name))
        
        categories_col.insert_one({"_id": cat_id, "name": cat_name, "cover": cover_name, "images": []})
        flash('تم إنشاء الألبوم بنجاح!', 'success')
    return redirect(url_for('admin'))

# تعديل اسم الألبوم
@app.route('/admin/edit_category_name/<cat_id>', methods=['POST'])
def edit_category_name(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    new_name = request.form.get('new_name')
    if new_name:
        categories_col.update_one({"_id": cat_id}, {"$set": {"name": new_name}})
        flash('تم تغيير الاسم بنجاح!', 'success')
    return redirect(url_for('admin'))

# تعديل غلاف الألبوم
@app.route('/admin/edit_cover/<cat_id>', methods=['POST'])
def edit_cover(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    file = request.files.get('new_cover')
    cat_info = categories_col.find_one({"_id": cat_id})
    
    if cat_info and file and allowed_file(file.filename):
        cat_path = os.path.join(UPLOAD_BASE, cat_id)
        os.makedirs(cat_path, exist_ok=True)
        
        old_cover = cat_info.get("cover", "")
        if old_cover and os.path.exists(os.path.join(cat_path, old_cover)):
            try: os.remove(os.path.join(cat_path, old_cover))
            except: pass
            
        cover_name = f"cover_{int(time.time())}_{secure_filename(file.filename)}"
        file.save(os.path.join(cat_path, cover_name))
        
        categories_col.update_one({"_id": cat_id}, {"$set": {"cover": cover_name}})
        flash('تم تحديث الغلاف بنجاح!', 'success')
    return redirect(url_for('admin'))

# حذف ألبوم بالكامل
@app.route('/admin/delete_category/<cat_id>', methods=['POST'])
def delete_category(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    categories_col.delete_one({"_id": cat_id})
    flash('تم حذف الألبوم بالكامل من قاعدة البيانات!', 'success')
    return redirect(url_for('admin'))

# ==========================================
# 4. إدارة صور الألبوم الداخلي
# ==========================================
@app.route('/admin/category/<cat_id>')
def admin_category(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    cat_info = categories_col.find_one({"_id": cat_id})
    if not cat_info: return redirect(url_for('admin'))
    return render_template('admin_category.html', cat_id=cat_id, cat_info=cat_info)

@app.route('/admin/upload_images/<cat_id>', methods=['POST'])
def upload_images(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    files = request.files.getlist('files')
    cat_path = os.path.join(UPLOAD_BASE, cat_id)
    os.makedirs(cat_path, exist_ok=True)
    
    uploaded_names = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = f"img_{int(time.time()*1000)}_{secure_filename(file.filename)}"
            file.save(os.path.join(cat_path, filename))
            uploaded_names.append(filename)
            
    if uploaded_names:
        categories_col.update_one({"_id": cat_id}, {"$push": {"images": {"$each": uploaded_names}}})
        flash('تم رفع الصور بنجاح!', 'success')
    return redirect(url_for('admin_category', cat_id=cat_id))

@app.route('/admin/delete_image/<cat_id>', methods=['POST'])
def delete_image(cat_id):
    if not session.get('admin_logged_in'): return jsonify({"status": "error"}), 401
    filename = request.json.get('filename')
    categories_col.update_one({"_id": cat_id}, {"$pull": {"images": filename}})
    
    filepath = os.path.join(UPLOAD_BASE, cat_id, secure_filename(filename))
    if os.path.exists(filepath):
        try: os.remove(filepath)
        except: pass
    return jsonify({"status": "success"})

@app.route('/admin/reorder_images/<cat_id>', methods=['POST'])
def reorder_images(cat_id):
    if not session.get('admin_logged_in'): return jsonify({"status": "error"}), 401
    new_order = request.json.get('order', [])
    categories_col.update_one({"_id": cat_id}, {"$set": {"images": new_order}})
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True, port=8080)