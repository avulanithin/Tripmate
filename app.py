import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from functools import wraps
from flask_wtf.csrf import CSRFProtect
from forms import LoginForm
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
import qrcode
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# CSRF Protection
csrf = CSRFProtect(app)

# SocketIO initialization
socketio = SocketIO(app)

# ------------------ Database (SQLite via SQLAlchemy) ------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tripmate.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')
    name = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    profile_pic = db.Column(db.String(255))
    emergency_contact = db.Column(db.String(120))


class Package(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float)
    total_days = db.Column(db.Integer)
    image_path = db.Column(db.String(255))
    places = db.Column(db.Text)  # comma-separated for simplicity
    hotels = db.Column(db.Text)  # comma-separated for simplicity


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey('package.id'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now())


class Itinerary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    destination = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.String(50))
    end_date = db.Column(db.String(50))


class Friend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending/accepted


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=func.now())

# No Neo4j driver. Using local SQLite DB instead.

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static/uploads')
PROFILE_PICS_FOLDER = os.path.join('static', 'profile_pics')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER

# Create the upload folders if they don't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(PROFILE_PICS_FOLDER):
    os.makedirs(PROFILE_PICS_FOLDER)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Generate QR code for the website
os.makedirs("static/qr", exist_ok=True)
url = "http://192.168.223.35:5000"
img = qrcode.make(url)
img.save("static/qr/website_qr.png")

# ------------------ Utility Functions ------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None

    u = User.query.get(user_id)
    if not u:
        return None
    return {
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'phone': u.phone,
        'profile_pic': u.profile_pic,
        'emergency_contact': u.emergency_contact,
        'user_id': u.id,
    }


# ------------------ Auth Decorators ------------------

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            flash('Admin access required.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ------------------ Database Functions ------------------

def create_user(email, password, role='user'):
    existing = User.query.filter_by(email=email).first()
    if existing:
        return
    u = User(email=email, password=password, role=role)
    db.session.add(u)
    db.session.commit()

def check_user(email, password):
    u = User.query.filter_by(email=email, password=password).first()
    if u:
        return u.role, u.id
    return None, None

def fetch_concepts():
    # No concepts table; return empty list to keep UI happy
    return []

def fetch_packages():
    pkgs = Package.query.all()
    return [
        {
            'title': p.title,
            'description': p.description,
            'price': p.price,
            'total_days': p.total_days,
            'image_path': p.image_path,
        }
        for p in pkgs
    ]

def fetch_package_details(package_name):
    p = Package.query.filter_by(title=package_name).first()
    if not p:
        return None
    places = (p.places or '')
    hotels = (p.hotels or '')
    return {
        'title': p.title,
        'description': p.description,
        'price': p.price,
        'total_days': p.total_days,
        'image_url': p.image_path,
        'places': [s.strip() for s in places.split(',') if s.strip()],
        'hotels': [s.strip() for s in hotels.split(',') if s.strip()],
    }

def create_package(title, description, price, total_days, image_path, places, hotels):
    p = Package(
        title=title,
        description=description,
        price=float(price) if price is not None else None,
        total_days=int(total_days) if total_days else None,
        image_path=image_path,
        places=",".join([pl for pl in places if pl]),
        hotels=",".join([h for h in hotels if h]),
    )
    db.session.add(p)
    db.session.commit()

def update_package(package_id, title, description, price, total_days, image_url, places=[], hotels=[]):
    p = Package.query.get(package_id)
    if not p:
        return
    p.title = title
    p.description = description
    p.price = float(price) if price is not None else None
    p.total_days = int(total_days) if total_days else None
    p.image_path = image_url
    p.places = ",".join([pl for pl in places if pl])
    p.hotels = ",".join([h for h in hotels if h])
    db.session.commit()

def delete_package(package_id):
    p = Package.query.get(package_id)
    if p:
        db.session.delete(p)
        db.session.commit()

def fetch_budget(email):
    u = User.query.filter_by(email=email).first()
    if not u:
        return []
    items = Budget.query.filter_by(user_id=u.id).all()
    return [{"expense_name": b.name, "amount": b.amount} for b in items]

def fetch_user_details(email):
    u = User.query.filter_by(email=email).first()
    if not u:
        return None
    return {"email": u.email, "role": u.role}

def fetch_user_details_by_id(user_id):
    u = User.query.get(user_id)
    if not u:
        return None
    return {"email": u.email, "name": u.name, "phone": u.phone, "profile_pic": u.profile_pic}

def update_user_profile(user_id, name, phone, profile_pic=None, email=None, emergency_contact=None):
    u = User.query.get(int(user_id))
    if not u:
        return
    u.name = name
    u.phone = phone
    if profile_pic is not None:
        u.profile_pic = profile_pic
    if email is not None:
        u.email = email
    if emergency_contact is not None:
        u.emergency_contact = emergency_contact
    db.session.commit()

def fetch_previous_trips(email):
    # Not implemented in SQLite baseline; return empty list for now
    return []

def save_itinerary(email, destination, start_date, end_date):
    u = User.query.filter_by(email=email).first()
    if not u:
        return
    it = Itinerary(user_id=u.id, destination=destination, start_date=start_date, end_date=end_date)
    db.session.add(it)
    db.session.commit()

def create_budget(email, budget_name, amount):
    u = User.query.filter_by(email=email).first()
    if not u:
        return
    b = Budget(user_id=u.id, name=budget_name, amount=float(amount))
    db.session.add(b)
    db.session.commit()

def initialize_admin():
    # Create tables
    db.create_all()
    # Seed admin
    if not User.query.filter_by(email='admin@gmail.com').first():
        db.session.add(User(email='admin@gmail.com', password='admin123', role='admin'))
        db.session.commit()
        print("Admin user created with email: admin@gmail.com and password: admin123")
    # Seed a sample package if none exist
    if Package.query.count() == 0:
        sample = Package(
            title='Goa Getaway',
            description='3 nights and 4 days in Goa with beach visits and local cuisine.',
            price=14999.0,
            total_days=4,
            image_path='/static/images/goa.jpg',
            places='Baga Beach, Calangute Beach, Fort Aguada',
            hotels='Beach Resort, City Hotel'
        )
        db.session.add(sample)
        db.session.commit()
        print('Seeded a sample package: Goa Getaway')

def save_booking(email, package_title):
    u = User.query.filter_by(email=email).first()
    p = Package.query.filter_by(title=package_title).first()
    if not u or not p:
        return
    db.session.add(Booking(user_id=u.id, package_id=p.id))
    db.session.commit()

def fetch_user_bookings(email):
    u = User.query.filter_by(email=email).first()
    if not u:
        return []
    bookings = (
        db.session.query(Booking, Package)
        .join(Package, Booking.package_id == Package.id)
        .filter(Booking.user_id == u.id)
        .all()
    )
    result = []
    for b, p in bookings:
        result.append({
            'title': p.title,
            'description': p.description,
            'price': p.price,
            'total_days': p.total_days,
            'image_path': p.image_path,
        })
    return result

def get_friends(user_id):
    # accepted friends both directions
    rows = Friend.query.filter(
        ((Friend.user_id == user_id) | (Friend.friend_id == user_id)) & (Friend.status == 'accepted')
    ).all()
    result = []
    for r in rows:
        other_id = r.friend_id if r.user_id == user_id else r.user_id
        other = User.query.get(other_id)
        if other:
            result.append({'id': other.id, 'name': other.name or other.email})
    return result

def get_all_users():
    users = User.query.all()
    return [{'id': u.id, 'name': u.name or u.email} for u in users]

def add_friend(user_id, friend_id):
    # avoid duplicates
    existing = Friend.query.filter_by(user_id=user_id, friend_id=friend_id).first()
    if existing:
        return
    db.session.add(Friend(user_id=user_id, friend_id=friend_id, status='pending'))
    db.session.commit()

def accept_friend(user_id, friend_id):
    r = Friend.query.filter_by(user_id=friend_id, friend_id=user_id, status='pending').first()
    if r:
        r.status = 'accepted'
    # ensure reciprocal row
    reciprocal = Friend.query.filter_by(user_id=user_id, friend_id=friend_id).first()
    if not reciprocal:
        db.session.add(Friend(user_id=user_id, friend_id=friend_id, status='accepted'))
    else:
        reciprocal.status = 'accepted'
    db.session.commit()

def get_dm_messages(user_id, friend_id):
    msgs = (
        Message.query.filter(
            ((Message.sender_id == user_id) & (Message.receiver_id == friend_id))
            | ((Message.sender_id == friend_id) & (Message.receiver_id == user_id))
        )
        .order_by(Message.timestamp.asc())
        .all()
    )
    return [
        {
            'message': m.message,
            'timestamp': m.timestamp.isoformat() if m.timestamp else None,
            'sender_id': m.sender_id,
        }
        for m in msgs
    ]

def save_dm_message(sender_id, receiver_id, message):
    db.session.add(Message(sender_id=sender_id, receiver_id=receiver_id, message=message))
    db.session.commit()

def get_suggested_friends(user_id):
    # Users not me and not already friends or requested
    all_users = User.query.filter(User.id != user_id).all()
    existing = Friend.query.filter(
        (Friend.user_id == user_id) | (Friend.friend_id == user_id)
    ).all()
    blocked_ids = {user_id}
    for r in existing:
        blocked_ids.add(r.user_id)
        blocked_ids.add(r.friend_id)
    suggestions = [u for u in all_users if u.id not in blocked_ids]
    return [{'id': u.id, 'name': u.name or u.email} for u in suggestions]

def get_friend_requests(user_id):
    rows = Friend.query.filter_by(friend_id=user_id, status='pending').all()
    out = []
    for r in rows:
        u = User.query.get(r.user_id)
        if u:
            out.append({'id': u.id, 'name': u.name or u.email})
    return out

# ------------------ In-Memory Storage ------------------

# Simple in-memory storage for demo purposes
tips = []

def create_tip(tip):
    tips.append(tip)

def fetch_tips():
    return tips

# ------------------ Routes ------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        create_user(email, password)
        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        role, user_id = check_user(email, password)

        if role:
            session['email'] = email
            session['role'] = role
            session['user_id'] = user_id

            if role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html', form=form)

@app.route('/admin')
def admin_dashboard():
    if 'role' in session and session['role'] == 'admin':
        return render_template('admin_dashboard.html')
    else:
        flash("Unauthorized access", "error")
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('landing'))

@app.route('/landing')
def landing():
    if 'email' not in session:
        return redirect(url_for('login'))
    concepts = fetch_concepts()
    return render_template('index.html', email=session['email'], role=session['role'], concepts=concepts)

@app.route('/packages')
def packages():
    packages = fetch_packages()
    return render_template('packages.html', packages=packages)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/budget', methods=['GET', 'POST'])
def budget():
    if 'email' not in session:
        flash('Please log in to access the Budget Tracker.', 'error')
        return redirect(url_for('login'))

    email = session['email']

    # Fetch the user's budget items and total budget
    budget_items = fetch_budget(email)
    for item in budget_items:
        item['amount'] = float(item['amount'])

    # Fetch or set total budget (you can store it in the user node or a separate Budget node)
    total_budget = session.get('total_budget', None)

    if request.method == 'POST':
        if 'total_budget' in request.form:
            total_budget = float(request.form['total_budget'])
            session['total_budget'] = total_budget  # Store in session for demo; ideally, store in DB
        else:
            expense_name = request.form['expense_name']
            amount = request.form['amount']
            create_budget(email, expense_name, amount)
            flash('Budget item added successfully!', 'success')
        return redirect(url_for('budget'))

    return render_template('budget.html', email=email, budget_items=budget_items, total_budget=total_budget)

@app.route('/manage_expenses', methods=['GET', 'POST'])
def manage_expenses():
    if 'email' not in session:
        flash('Please log in to access the Manage Expenses feature.', 'error')
        return redirect(url_for('login'))

    email = session['email']

    if request.method == 'POST':
        expense_name = request.form['expense_name']
        amount = request.form['amount']

        # Add the expense to the database
        create_budget(email, expense_name, amount)
        flash('Expense added successfully!', 'success')
        return redirect(url_for('manage_expenses'))

    # Fetch the user's expenses
    expenses = fetch_budget(email)
    return render_template('manage_expenses.html', email=email, expenses=expenses)

@app.route('/group_chat')
def group_chat():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    suggested = get_suggested_friends(user_id)
    requests = get_friend_requests(user_id)
    friends = get_friends(user_id)
    user = get_current_user()
    return render_template(
        'chat.html',
        suggested=suggested,
        requests=requests,
        friends=friends,
        user=user
    )

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/plan_smart', methods=['GET', 'POST'])
def plan_smart():
    if 'email' not in session:
        flash('Please log in to access the Plan Smart feature.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        tip = request.form.get('tip')
        if tip:
            create_tip(tip)
            flash('Your tip has been added successfully!', 'success')
        return redirect(url_for('plan_smart'))

    # Fetch tips for the Plan Smart page
    return render_template('plan_smart.html', email=session['email'], tips=fetch_tips())

@app.route('/plan_itinerary', methods=['GET', 'POST'])
def plan_itinerary():
    if 'email' not in session:
        flash('Please log in to access the Plan Itinerary feature.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Handle itinerary planning logic here
        destination = request.form.get('destination')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        # Example: Save the itinerary to the database
        save_itinerary(session['email'], destination, start_date, end_date)
        flash('Itinerary planned successfully!', 'success')
        return redirect(url_for('plan_itinerary'))

    return render_template('plan_itinerary.html')


@app.route('/enjoy_more')
def enjoy_more():
    if 'email' not in session:
        flash('Please log in to access the Enjoy More feature.', 'error')
        return redirect(url_for('login'))
    return render_template('enjoy_more.html')

@app.route('/view_profile')
def view_profile():
    user = get_current_user()  # ✅ Use the correct function
    if not user:
        flash("Please log in to view your profile.", "error")
        return redirect(url_for('login'))
    return render_template('view_profile.html', user=user)



@app.route('/previous_trips')
def previous_trips():
    if 'email' not in session:
        flash('Please log in to view your previous trips.', 'error')
        return redirect(url_for('login'))

    email = session['email']
    # Fetch previous trips from the database
    trips = fetch_previous_trips(email)
    return render_template('previous_trips.html', trips=trips)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    user = get_current_user()
    if not user:
        flash("Please log in to edit your profile.", "error")
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        emergency_contact = request.form.get('emergency_contact')
        file = request.files.get('profile_pic')

        profile_pic = user.get('profile_pic')
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{user['id']}_{file.filename}")
            file.save(os.path.join(app.config['PROFILE_PICS_FOLDER'], filename))
            profile_pic = filename

        # Update user in DB
        update_user_profile(user['id'], name=name, phone=phone, profile_pic=profile_pic, email=email, emergency_contact=emergency_contact)

        flash("Profile updated successfully!", "success")
        return redirect(url_for('view_profile'))

    return render_template('edit_profile.html', user=user)

@app.route('/add_package', methods=['GET', 'POST'])
def add_package():
    if 'role' not in session or session['role'] != 'admin':
        flash('Admin access required.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        description = request.form.get('description')
        price = request.form.get('price')
        total_days = request.form.get('total_days')
        image_url = request.form.get('image_url')  # Or handle file uploads
        places = request.form.getlist('places')  # Multiple places
        hotels = request.form.getlist('hotels')  # Multiple hotels

        # Save the package to the database
        create_package(title, description, price, total_days, image_url, places, hotels)
        flash('Package added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('add_package.html')

@app.route('/book_package', methods=['POST'])
def book_package():
    user_id = session['user_id']
    destination = request.form['destination']
    #start_date = request.form['start_date']
    #end_date = request.form['end_date']
    # Save booking to DB (pseudo code)
    #save_trip(user_id, destination)
    return redirect(url_for('my_bookings'))

@app.route('/my_bookings')
def my_bookings():
    if 'email' not in session:
        flash('Please log in to view your bookings.', 'error')
        return redirect(url_for('login'))

    email = session['email']
    bookings = fetch_user_bookings(email)
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/my_trips', methods=['GET', 'POST'])
def my_trips():
    user_id = session['user_id']
    if request.method == 'POST':
        # Create or update trip
        data = request.form
        # ...save to DB...
        return redirect(url_for('my_trips'))
    # Not implemented fully; show chat suggestions instead
    trips = []
    suggested_friends = get_suggested_friends(user_id)
    return render_template('my_trips.html', trips=trips, suggested_friends=suggested_friends)

@app.route('/delete_trip/<int:trip_id>', methods=['POST'])
def delete_trip(trip_id):
    # ...delete from DB...
    return '', 204

@app.route('/api/friends')
def api_friends():
    user_id = session['user_id']
    friends = get_friends(user_id)
    all_users = get_all_users()
    requests = get_friend_requests(user_id)
    suggested = get_suggested_friends(user_id)
    return jsonify({
        'friends': friends,
        'all_users': all_users,
        'requests': requests,
        'suggested': suggested,
        'current_user_id': user_id
    })

@app.route('/api/add_friend', methods=['POST'])
def api_add_friend():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    friend_id = data.get('friend_id')
    if not friend_id:
        return jsonify({'error': 'Missing friend_id'}), 400

    user_id = session['user_id']
    add_friend(user_id, friend_id)
    return jsonify({'message': 'Friend request sent!'}), 200

@app.route('/api/accept_friend', methods=['POST'])
def api_accept_friend():
    user_id = session['user_id']
    friend_id = request.json['friend_id']
    accept_friend(user_id, friend_id)
    return '', 204

@app.route('/api/messages/<int:friend_id>')
def api_messages(friend_id):
    user_id = session['user_id']
    messages = get_dm_messages(user_id, friend_id)
    return jsonify({'messages': messages, 'current_user_id': user_id})

# ------------------ SocketIO Events ------------------

@socketio.on('join_user_room')
def handle_join_user_room(data):
    user_id = session['user_id']
    join_room(f"user_{user_id}")

@socketio.on('send_friend_request')
def handle_send_friend_request(data):
    sender_id = session['user_id']
    receiver_id = data['friend_id']
    add_friend(sender_id, receiver_id)
    # Notify the receiver in real-time
    emit('receive_friend_request', {'from_id': sender_id}, room=f"user_{receiver_id}")

@socketio.on('accept_friend_request')
def handle_accept_friend_request(data):
    user_id = session['user_id']
    friend_id = data['friend_id']
    accept_friend(user_id, friend_id)
    # Notify both users
    emit('friend_request_accepted', {'friend_id': user_id}, room=f"user_{friend_id}")
    emit('friend_request_accepted', {'friend_id': friend_id}, room=f"user_{user_id}")

@socketio.on('send_message')
def handle_send_message(data):
    sender_id = session['user_id']
    receiver_id = data['receiver_id']
    message = data['message']
    save_dm_message(sender_id, receiver_id, message)
    room = f"dm_{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    emit('new_message', {'sender_id': sender_id, 'message': message}, room=room)

@socketio.on('join_dm')
def handle_join_dm(data):
    user_id = session['user_id']
    friend_id = data['friend_id']
    room = f"dm_{min(user_id, friend_id)}_{max(user_id, friend_id)}"
    join_room(room)

@socketio.on('friend_accepted')
def handle_friend_accepted(data):
    # Optionally, broadcast to the friend that the request was accepted
    emit('friend_accepted', {}, broadcast=True)

# ------------------ Context Processor ------------------

@app.context_processor
def inject_user():
    user = get_current_user()
    return dict(user=user)

# ------------------ Main ------------------

if __name__ == "__main__":
    with app.app_context():
        initialize_admin()
    # Bind to localhost so the browser URL is valid: http://localhost:5000
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, debug=True, host="127.0.0.1", port=port)

