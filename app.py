import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from neo4j import GraphDatabase, exceptions
from werkzeug.utils import secure_filename
from functools import wraps
from flask_wtf.csrf import CSRFProtect
from forms import LoginForm
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
import qrcode

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# CSRF Protection
csrf = CSRFProtect(app)

# SocketIO initialization
socketio = SocketIO(app)

# Neo4j configuration
uri = "bolt://localhost:7687"
username = "neo4j"
password = "tripmate"
driver = GraphDatabase.driver(uri, auth=(username, password))

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

    with driver.session() as s:
        result = s.run("""
            MATCH (u:User {user_id: $user_id})
            RETURN 
                u.name AS name,
                u.email AS email,
                u.phone AS phone,
                u.profile_pic AS profile_pic,
                u.emergency_contact AS emergency_contact,
                u.user_id AS user_id
        """, user_id=user_id)

        record = result.single()
        if record:
            user = dict(record)
            return user

    return None


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
    with driver.session() as session:
        # Check if the user already exists
        result = session.run("""
            MATCH (u:User {email: $email})
            RETURN u
        """, email=email)
        if result.peek():
            return  # User already exists, do nothing

        # Create the user if it doesn't exist
        session.run("""
            CREATE (u:User {user_id: "<some-uuid>", email: $email, password: $password, role: $role})
        """, email=email, password=password, role=role)

def check_user(email, password):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {email: $email, password: $password})
            RETURN u.role AS role, id(u) AS user_id
        """, email=email, password=password)
        record = result.single()
        if record:
            return record['role'], record['user_id']
        return None, None

def fetch_concepts():
    query = "MATCH (c:Concept) RETURN c.name AS name"
    with driver.session() as session:
        result = session.run(query)
        return [record["name"] for record in result]

def fetch_packages():
    with driver.session() as session:
        result = session.run("""
            MATCH (p:Package)
            RETURN p.title AS title, p.description AS description, p.price AS price,
                   p.total_days AS total_days, p.image_path AS image_path
        """)
        return [record.data() for record in result]

def fetch_package_details(package_name):
    query = """
    MATCH (p:Package {title: $package_name})
    OPTIONAL MATCH (p)-[:INCLUDES]->(pl:Place)
    OPTIONAL MATCH (p)-[:STAY_AT]->(h:Hotel)
    RETURN p.title AS title, p.description AS description,
           p.price AS price, p.total_days AS total_days,
           p.image_url AS image_url,
           collect(DISTINCT pl.name) AS places,
           collect(DISTINCT h.name) AS hotels
    """
    with driver.session() as session:
        result = session.run(query, package_name=package_name)
        return result.single().data() if result.peek() else None

def create_package(title, description, price, total_days, image_path, places, hotels):
    with driver.session() as session:
        session.run("""
            CREATE (p:Package {
                title: $title,
                description: $description,
                price: $price,
                total_days: $total_days,
                image_path: $image_path,
                places: $places,
                hotels: $hotels
            })
        """, title=title, description=description, price=price, total_days=total_days,
            image_path=image_path, places=places, hotels=hotels)

def update_package(package_id, title, description, price, total_days, image_url, places=[], hotels=[]):
    with driver.session() as session:
        session.run("""
        MATCH (p:Package) WHERE id(p) = $package_id
        SET p.title = $title, p.description = $description,
            p.price = $price, p.total_days = $total_days,
            p.image_url = $image_url
        """, package_id=package_id, title=title, description=description,
             price=price, total_days=total_days, image_url=image_url)

        session.run("""
        MATCH (p:Package)-[r]->()
        WHERE id(p) = $package_id AND (type(r) = 'INCLUDES' OR type(r) = 'STAY_AT')
        DELETE r
        """, package_id=package_id)

        for place in places:
            session.run("""
            MATCH (p:Package) WHERE id(p) = $package_id
            MERGE (pl:Place {name: $place})
            MERGE (p)-[:INCLUDES]->(pl)
            """, package_id=package_id, place=place)

        for hotel in hotels:
            session.run("""
            MATCH (p:Package) WHERE id(p) = $package_id
            MERGE (h:Hotel {name: $hotel})
            MERGE (p)-[:STAY_AT]->(h)
            """, package_id=package_id, hotel=hotel)

def delete_package(package_id):
    with driver.session() as session:
        session.run("MATCH (p:Package) WHERE id(p) = $package_id DETACH DELETE p", package_id=package_id)

def fetch_budget(email):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {email: $email})-[:HAS_BUDGET]->(b:Budget)
            RETURN b.name AS expense_name, b.amount AS amount
        """, email=email)
        return [{"expense_name": record["expense_name"], "amount": record["amount"]} for record in result]

def fetch_user_details(email):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {email: $email})
            RETURN u.email AS email, u.role AS role
        """, email=email)
        return result.single().data() if result.peek() else None

def fetch_user_details_by_id(user_id):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User) WHERE id(u) = $user_id
            RETURN u.email AS email, u.name AS name, u.phone AS phone, u.profile_pic AS profile_pic
        """, user_id=user_id)
        return result.single().data() if result.peek() else None

def update_user_profile(user_id, name, phone, profile_pic=None):
    with driver.session() as session:
        session.run("""
            MATCH (u:User)
            WHERE id(u) = $user_id
            SET u.name = $name, u.phone = $phone, u.profile_pic = $profile_pic
        """, user_id=int(user_id), name=name, phone=phone, profile_pic=profile_pic)

def fetch_previous_trips(email):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {email: $email})-[:BOOKED]->(t:Trip)
            RETURN t.name AS trip_name, t.date AS trip_date, t.budget AS budget
        """, email=email)
        return [record.data() for record in result]

def save_itinerary(email, destination, start_date, end_date):
    with driver.session() as session:
        session.run("""
            MATCH (u:User {email: $email})
            CREATE (u)-[:PLANNED]->(:Itinerary {
                destination: $destination,
                start_date: $start_date,
                end_date: $end_date
            })
        """, email=email, destination=destination, start_date=start_date, end_date=end_date)

def create_budget(email, budget_name, amount):
    with driver.session() as session:
        session.run("""
            MATCH (u:User {email: $email})
            CREATE (u)-[:HAS_BUDGET]->(:Budget {name: $budget_name, amount: $amount})
        """, email=email, budget_name=budget_name, amount=amount)

def initialize_admin():
    with driver.session() as session:
        # Check if the admin user already exists
        result = session.run("""
            MATCH (u:User {email: 'admin@gmail.com'})
            RETURN u
        """)
        if not result.peek():
            # Create the admin user
            session.run("""
                CREATE (:User {email: 'admin@gmail.com', password: 'admin123', role: 'admin'})
            """)
            print("Admin user created with email: admin@gmail.com and password: admin123")

def save_booking(email, package_title):
    with driver.session() as session:
        session.run("""
            MATCH (u:User {email: $email})
            MATCH (p:Package {title: $package_title})
            CREATE (u)-[:BOOKED]->(p)
        """, email=email, package_title=package_title)

def fetch_user_bookings(email):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {email: $email})-[:BOOKED]->(p:Package)
            RETURN p.title AS title, p.description AS description, p.price AS price,
                   p.total_days AS total_days, p.image_path AS image_path
        """, email=email)
        return [record.data() for record in result]

def get_friends(user_id):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User)-[f:FRIEND_WITH {status:'accepted'}]-(friend:User)
            WHERE id(u) = $user_id
            RETURN id(friend) AS id, coalesce(friend.name, friend.email) AS name
        """, user_id=user_id)
        return [record.data() for record in result]

def get_all_users():
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User)
            RETURN id(u) AS id, coalesce(u.name, u.email) AS name
        """)
        return [record.data() for record in result]

def add_friend(user_id, friend_id):
    with driver.session() as session:
        # Create a pending friend request (one direction)
        session.run("""
            MATCH (a:User), (b:User)
            WHERE id(a) = $user_id AND id(b) = $friend_id
            MERGE (a)-[r:FRIEND_WITH]->(b)
            SET r.status = 'pending'
        """, user_id=user_id, friend_id=friend_id)

def accept_friend(user_id, friend_id):
    with driver.session() as session:
        # Accept the friend request (make both directions accepted)
        session.run("""
            MATCH (a:User)-[r:FRIEND_WITH]->(b:User)
            WHERE id(a) = $friend_id AND id(b) = $user_id AND r.status = 'pending'
            SET r.status = 'accepted'
            MERGE (b)-[r2:FRIEND_WITH]->(a)
            SET r2.status = 'accepted'
        """, user_id=user_id, friend_id=friend_id)

def get_dm_messages(user_id, friend_id):
    with driver.session() as session:
        result = session.run("""
            MATCH (a:User {user_id: $user_id})-[m:SENT_MESSAGE]-(b:User {user_id: $friend_id})
            RETURN m.message AS message, m.timestamp AS timestamp, 
                   startNode(m).user_id AS sender_id
            ORDER BY m.timestamp
        """, user_id=user_id, friend_id=friend_id)
        return [dict(record) for record in result]

def save_dm_message(sender_id, receiver_id, message):
    with driver.session() as session:
        session.run("""
            MATCH (a:User {user_id: $sender_id}), (b:User {user_id: $receiver_id})
            CREATE (a)-[:SENT_MESSAGE {
                message: $message,
                timestamp: datetime()
            }]->(b)
        """, sender_id=sender_id, receiver_id=receiver_id, message=message)

def get_suggested_friends(user_id):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User)
            WHERE id(u) <> $user_id
            AND NOT (u)<-[:FRIEND_WITH]-(:User {user_id: $user_id})
            AND NOT (u)-[:FRIEND_WITH]->(:User {user_id: $user_id})
            RETURN id(u) AS id, coalesce(u.name, u.email) AS name
        """, user_id=user_id)
        return [record.data() for record in result]

def get_friend_requests(user_id):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User)-[r:FRIEND_WITH {status:'pending'}]->(me:User)
            WHERE id(me) = $user_id
            RETURN id(u) AS id, coalesce(u.name, u.email) AS name
        """, user_id=user_id)
        return [record.data() for record in result]

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

        # Update user in Neo4j
        with driver.session() as s:
            s.run("""
                MATCH (u:User) WHERE id(u) = $uid
                SET u.name = $name,
                    u.email = $email,
                    u.phone = $phone,
                    u.emergency_contact = $emergency_contact,
                    u.profile_pic = $profile_pic
            """, uid=user['id'], name=name, email=email, phone=phone,
                 emergency_contact=emergency_contact, profile_pic=profile_pic)

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
    trips = get_user_trips(user_id)
    suggested_friends = get_suggested_friends_by_dates(user_id)
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
    initialize_admin()
    socketio.run(app, debug=True, host="0.0.0.0")

