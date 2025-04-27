from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from neo4j import GraphDatabase

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Connect to Neo4j
uri = "bolt://localhost:7687"
username = "neo4j"
password = "rashvi023"
driver = GraphDatabase.driver(uri, auth=(username, password))

# --- DATABASE FUNCTIONS ---

def fetch_concepts(tx):
    result = tx.run("MATCH (c:Concept) RETURN c.name AS name")
    return [record["name"] for record in result]

def fetch_packages(tx):
    result = tx.run("MATCH (p:Package) RETURN p.name AS name")
    return [{"name": record["name"]} for record in result]

def fetch_package_details(tx, package_name):
    result = tx.run("""
        MATCH (p:Package {name: $name})
        RETURN p.name AS name, p.price AS price, p.duration AS duration, p.description AS description
    """, name=package_name)
    record = result.single()
    if record:
        return {
            "name": record["name"],
            "price": record["price"],
            "duration": record["duration"],
            "description": record["description"]
        }
    return None

def create_user(tx, username, password):
    tx.run("CREATE (u:User {username: $username, password: $password})", username=username, password=password)

def check_user(tx, username, password):
    result = tx.run("MATCH (u:User {username: $username, password: $password}) RETURN u", username=username, password=password)
    return result.single()

def create_tip(tx, tip_text):
    tx.run("CREATE (t:Tip {content: $content})", content=tip_text)

def fetch_tips(tx):
    result = tx.run("MATCH (t:Tip) RETURN t.content AS content")
    return [record["content"] for record in result]

def create_itinerary(tx, destination, start_date, end_date):
    tx.run("CREATE (i:Itinerary {destination: $destination, start_date: $start_date, end_date: $end_date})",
           destination=destination, start_date=start_date, end_date=end_date)

def create_budget(tx, category, amount):
    tx.run("CREATE (b:Budget {category: $category, amount: $amount})", category=category, amount=amount)

def fetch_manage_expenses(tx):
    result = tx.run("MATCH (c:Concept {name: 'Manage Expenses'}) RETURN c.name AS name")
    record = result.single()
    return record['name'] if record else None

def fetch_enjoy_more(tx):
    result = tx.run("MATCH (c:Concept {name: 'Enjoy More'}) RETURN c.name AS name")
    record = result.single()
    return record['name'] if record else None

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/packages')
def packages():
    with driver.session() as session_db:
        packages = session_db.read_transaction(fetch_packages)
    return render_template('packages.html', packages=packages)

@app.route('/get_package_details', methods=['GET'])
def get_package_details():
    package_name = request.args.get('package_name')
    if package_name:
        with driver.session() as session_db:
            package_details = session_db.read_transaction(fetch_package_details, package_name)
            if package_details:
                return jsonify(package_details)
            return jsonify({"error": "Package not found"})
    return jsonify({"error": "No package selected"})

@app.route('/budget', methods=['GET', 'POST'])
def budget():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    email = session['email']
    
    if request.method == 'POST':
        # Capture the form data
        expense_name = request.form['expense_name']
        amount = request.form['amount']

        # Insert into Neo4j database
        with driver.session() as session_neo:
            session_neo.run("""
                MERGE (u:User {email: $email})
                CREATE (b:Budget {expense_name: $expense_name, amount: $amount})
                MERGE (u)-[:HAS_BUDGET]->(b)
            """, email=email, expense_name=expense_name, amount=amount)
        
        return redirect(url_for('budget'))  # Redirect to refresh the page

    return render_template('budget.html', email=email)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with driver.session() as session_db:
            session_db.write_transaction(create_user, email, password)
        flash('Account created successfully! Please login.')
        return redirect(url_for('login'))
    return render_template('b_user_page.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if check_admin(email, password):
            session['email'] = email
            session['role'] = 'admin'
            return redirect(url_for('landing'))

        with driver.session() as session_db:
            user = session_db.read_transaction(check_user, email, password)
            if user:
                session['email'] = email
                session['role'] = 'user'
                return redirect(url_for('landing'))

        flash('Invalid credentials. Please try again.')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/landing')
def landing():
    if 'email' not in session:
        return redirect(url_for('login'))
    with driver.session() as session_db:
        concepts = session_db.read_transaction(fetch_concepts)
    return render_template('index.html', email=session['email'], role=session['role'], concepts=concepts)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/plan_smart', methods=['GET', 'POST'])
def plan_smart():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        tip = request.form['tip']
        with driver.session() as session_db:
            session_db.write_transaction(create_tip, tip)
        return redirect(url_for('plan_smart'))

    with driver.session() as session_db:
        tips = session_db.read_transaction(fetch_tips)

    return render_template('plan_smart.html', email=session['email'], role=session['role'], tips=tips)

@app.route('/plan_itinerary', methods=['POST'])
def plan_itinerary():
    if 'email' not in session:
        return redirect(url_for('login'))

    destination = request.form['destination']
    start_date = request.form['start_date']
    end_date = request.form['end_date']

    with driver.session() as session_db:
        session_db.write_transaction(create_itinerary, destination, start_date, end_date)
    return redirect(url_for('plan_smart'))

@app.route('/plan_budget', methods=['POST'])
def plan_budget():
    if 'email' not in session:
        return redirect(url_for('login'))

    category = request.form['category']
    amount = request.form['amount']

    with driver.session() as session_db:
        session_db.write_transaction(create_budget, category, amount)
    return redirect(url_for('plan_smart'))

@app.route('/book-package', methods=['POST'])
def book_package():
    try:
        data = request.get_json()

        username = data.get('username')      # coming from frontend
        package_name = data.get('package_name')

        if not username or not package_name:
            return jsonify({"error": "Username or package name missing."}), 400

        with driver.session() as session_neo:
            session_neo.run("""
                MATCH (u:User {username: $username}), (p:Package {name: $package_name})
                MERGE (u)-[:BOOKED]->(p)
            """, username=username, package_name=package_name)

        return jsonify({"message": "Package booked successfully!"}), 200

    except Exception as e:
        print("Booking Error:", e)
        return jsonify({"error": "Booking failed."}), 500


@app.route('/my-bookings', methods=['POST'])
def my_bookings():
    try:
        data = request.get_json()
        username = data.get('username')  # Get username from frontend

        if not username:
            return jsonify({"error": "Username is required."}), 400

        with driver.session() as session_neo:
            result = session_neo.run("""
                MATCH (u:User {username: $username})-[:BOOKED]->(p:Package)
                RETURN p.name AS name, p.duration AS duration, p.price AS price, p.description AS description
            """, username=username)

            packages = [record.data() for record in result]

        return jsonify({"packages": packages}), 200

    except Exception as e:
        print("Error fetching bookings:", e)
        return jsonify({"error": "Could not fetch bookings."}), 500



@app.route('/manage_expenses')
def manage_expenses():
    if 'email' not in session:
        return redirect(url_for('login'))
    with driver.session() as session_db:
        concept_name = session_db.read_transaction(fetch_manage_expenses)
    return render_template('manage_expenses.html', concept_name=concept_name, email=session['email'], role=session['role'])

@app.route('/enjoy_more')
def enjoy_more():
    if 'email' not in session:
        return redirect(url_for('login'))
    with driver.session() as session_db:
        concept_name = session_db.read_transaction(fetch_enjoy_more)
    return render_template('enjoy_more.html', concept_name=concept_name, email=session['email'], role=session['role'])

# --- HELPER ---

def check_admin(username, password):
    return username == "admin" and password == "admin123"

# --- MAIN ---
if __name__ == '__main__':
    app.run(debug=True)
