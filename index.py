import os
import time
import urllib.parse
import base64
import io
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
# مفتاح سري لتشفير الجلسات
app.secret_key = os.urandom(32).hex()

# ==========================================
# إعدادات MongoDB Atlas 
# ==========================================
username = urllib.parse.quote_plus('ahmedosman')
password = urllib.parse.quote_plus('i-fn@bBHV7rXMYj')

MONGO_URI = f"mongodb+srv://{username}:{password}@cluster0.8wawfsu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

try:
    client = MongoClient(MONGO_URI)
    db = client['photographer_portfolio']
    categories_col = db['categories']
    settings_col = db['settings']
    client.admin.command('ping')
    print("تم الاتصال بـ MongoDB بنجاح!")
except Exception as e:
    print(f"فشل الاتصال بـ MongoDB: {e}")

# بيانات دخول لوحة الإدارة
ADMIN_USERNAME = "Admin"
ADMIN_PASSWORD_HASH = generate_password_hash("Ahmed123")

def is_image(file_storage):
    """التحقق من أن الملف صورة فعلاً بغض النظر عن الامتداد"""
    try:
        file_storage.seek(0)
        img = Image.open(file_storage)
        img.verify()
        file_storage.seek(0)
        return True
    except:
        file_storage.seek(0)
        return False

def get_main_banner():
    doc = settings_col.find_one({"_id": "main_banner"})
    return doc.get("base64_data", "") if doc else ""

# ==========================================
# دالة دمج العلامة المائية - Ahmed Osman
# ==========================================
def add_watermark_and_encode(file_storage):
    file_storage.seek(0)
    img = Image.open(file_storage).convert("RGBA")
    
    # تصغير حجم الصورة ليناسب العرض على الشاشات وتسريع الرفع
    img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
    width, height = img.size
    
    watermark_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark_layer)
    
    font_size = max(int(width / 45), 14)
    
    # محاولة تحميل خط مائل
    try:
        font = ImageFont.truetype("ariali.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", font_size)
        except:
            font = ImageFont.load_default()
                
    text = "Ahmed Osman"
    
    # حساب أبعاد النص
    try:
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    except:
        text_width, text_height = draw.textsize(text, font=font)
        
    # --- إعدادات الهوامش (Margins) ---
    margin_x = width * 0.03 # هامش 3% من العرض
    margin_y = height * 0.03 # هامش 3% من الارتفاع
    
    # الختم الوحيد: في الزاوية السفلية اليمنى (Bottom-Right)
    x = width - text_width - margin_x
    y = height - text_height - margin_y
    draw.text((x, y), text, fill=(255, 255, 255, 140), font=font)
    
    watermarked_img = Image.alpha_composite(img, watermark_layer)
    watermarked_img = watermarked_img.convert("RGB") 
    
    buffered = io.BytesIO()
    # حفظ بجودة معقولة مع ضغط لسرعة التحميل
    watermarked_img.save(buffered, format="JPEG", quality=75, optimize=True)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# ==========================================
# 1. واجهة الزوار
# ==========================================
@app.route('/')
def index():
    categories = list(categories_col.find({}, {"images": 0}))
    return render_template('index.html', categories=categories, banner=get_main_banner())

@app.route('/category/<cat_id>')
def category_view(cat_id):
    cat_info = categories_col.find_one({"_id": cat_id}, {"images": 0})
    if not cat_info:
        return redirect(url_for('index'))
    return render_template('category.html', cat_id=cat_id, cat_info=cat_info, banner=get_main_banner())

@app.route('/api/category_images/<cat_id>')
def get_category_images_api(cat_id):
    """جلب فوري فائق السرعة عبر تقنية Direct Array Slicing اللحظية"""
    try:
        page = int(request.args.get('page', 1))
        index_pos = page - 1
        
        # استخدام إسقاط المخطط الفرعي لجلب مصفوفة فرعية بحجم عنصر واحد فوريّاً بدون لود
        cat_info = categories_col.find_one(
            {"_id": cat_id}, 
            {"images": {"$slice": [index_pos, 1]}}
        )
        
        if not cat_info or 'images' not in cat_info or len(cat_info['images']) == 0:
            return jsonify({"status": "success", "images": [], "has_more": False})
            
        return jsonify({
            "status": "success",
            "images": [cat_info['images'][0]],
            "has_more": True
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 2. نظام تسجيل الدخول
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        if user == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, pw):
            session['admin_logged_in'] = True
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "بيانات الدخول غير صحيحة"}), 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

# ==========================================
# 3. لوحة الإدارة
# ==========================================
@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    categories = list(categories_col.find())
    return render_template('admin.html', categories=categories, banner=get_main_banner())

@app.route('/admin/update_banner', methods=['POST'])
def update_banner():
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    file = request.files.get('banner_image')
    if file and is_image(file):
        encoded_string = add_watermark_and_encode(file)
        settings_col.update_one({"_id": "main_banner"}, {"$set": {"base64_data": encoded_string}}, upsert=True)
        flash('تم تحديث صورة الهيدر بنجاح!', 'success')
    else:
        flash('فشل التحديث، يرجى التأكد من رفع ملف صورة صحيح.', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/add_category', methods=['POST'])
def add_category():
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    cat_name = request.form.get('cat_name')
    file = request.files.get('cover_image')
    
    if cat_name and file and is_image(file):
        cat_id = f"cat_{int(time.time())}"
        encoded_cover = add_watermark_and_encode(file)
        categories_col.insert_one({"_id": cat_id, "name": cat_name, "cover_base64": encoded_cover, "images": []})
        flash('تم إنشاء الألبوم بنجاح!', 'success')
    else:
        flash('فشل الإنشاء، يرجى التأكد من رفع صورة للغلاف.', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/edit_category_name/<cat_id>', methods=['POST'])
def edit_category_name(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    new_name = request.form.get('new_name')
    if new_name:
        categories_col.update_one({"_id": cat_id}, {"$set": {"name": new_name}})
        flash('تم تغيير الاسم بنجاح!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/edit_cover/<cat_id>', methods=['POST'])
def edit_cover(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    file = request.files.get('new_cover')
    if file and is_image(file):
        encoded_cover = add_watermark_and_encode(file)
        categories_col.update_one({"_id": cat_id}, {"$set": {"cover_base64": encoded_cover}})
        flash('تم تحديث الغلاف بنجاح!', 'success')
    else:
        flash('فشل التحديث، يرجى رفع ملف صورة.', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/delete_category/<cat_id>', methods=['POST'])
def delete_category(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    categories_col.delete_one({"_id": cat_id})
    flash('تم حذف الألبوم بالكامل!', 'success')
    return redirect(url_for('admin'))

# ==========================================
# 4. إدارة صور الألبوم الداخلي (AJAX Upload)
# ==========================================
@app.route('/admin/category/<cat_id>')
def admin_category(cat_id):
    if not session.get('admin_logged_in'): return redirect(url_for('login'))
    cat_info = categories_col.find_one({"_id": cat_id})
    if not cat_info: return redirect(url_for('admin'))
    return render_template('admin_category.html', cat_id=cat_id, cat_info=cat_info)

@app.route('/admin/upload_images/<cat_id>', methods=['POST'])
def upload_images(cat_id):
    if not session.get('admin_logged_in'): 
        return jsonify({"status": "error", "message": "غير مصرح لك"}), 401
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({"status": "error", "message": "لم يتم اختيار صور!"}), 400

    encoded_images = []
    success_count = 0
    fail_count = 0

    for file in files:
        if file and is_image(file):
            try:
                encoded_img = add_watermark_and_encode(file)
                encoded_images.append(encoded_img)
                success_count += 1
            except Exception as e:
                fail_count += 1
        else:
            fail_count += 1
            
    if encoded_images:
        categories_col.update_one({"_id": cat_id}, {"$push": {"images": {"$each": encoded_images}}})
        msg = f"تم رفع {success_count} صورة بنجاح!"
        if fail_count > 0: msg += f" وفشل رفع {fail_count} ملفات غير صالحة."
        return jsonify({"status": "success", "message": msg})
    else:
        return jsonify({"status": "error", "message": "فشل الرفع بالكامل، تأكد من أن الملفات المرفوعة هي صور صالحة."}), 400

@app.route('/admin/delete_image/<cat_id>', methods=['POST'])
def delete_image(cat_id):
    if not session.get('admin_logged_in'): return jsonify({"status": "error"}), 401
    img_data = request.json.get('filename')
    categories_col.update_one({"_id": cat_id}, {"$pull": {"images": img_data}})
    return jsonify({"status": "success"})

@app.route('/admin/reorder_images/<cat_id>', methods=['POST'])
def reorder_images(cat_id):
    if not session.get('admin_logged_in'): return jsonify({"status": "error"}), 401
    new_order = request.json.get('order', [])
    categories_col.update_one({"_id": cat_id}, {"$set": {"images": new_order}})
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True, port=8080)
