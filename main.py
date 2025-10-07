from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import joblib
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time
import re
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or "your_secret_key"

# Configure SQL Alchemy
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class PriceTracker(db.Model):
    __tablename__ = 'price_tracker'
    
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False)
    current_price = db.Column(db.Float, nullable=False)
    desired_price = db.Column(db.Float, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    product_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    notification_sent = db.Column(db.Boolean, default=False)
    notification_sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<PriceTracker {self.product_name}>'

# Routes
@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for('dashboard'))
    return render_template("index.html")

# Login
@app.route("/login", methods=["POST"])
def login():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        session['username'] = username
        return redirect(url_for('dashboard'))
    else:
        return render_template("index.html", error = "Invaild username or password.")

# Register
@app.route("/register", methods=["POST"])
def register():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user:
        return render_template("index.html", error="User already here!!")
    else:
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        session['username'] = username
        return redirect(url_for('dashboard'))

# Dashboard
@app.route("/dashboard")
def dashboard():
    if 'username' in session:
        return render_template("dashboard.html", username=session['username'])
    return redirect(url_for('home'))

# Logout
@app.route("/logout")
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

# Fake Review Detector
MODEL_PATH = os.path.join("fake_review_models", "fake_review_model.pkl")
VECT_PATH  = os.path.join("fake_review_models", "tfidf_vectorizer.pkl")
LE_PATH    = os.path.join("fake_review_models", "label_encoder.pkl")  # optional

model = joblib.load(MODEL_PATH)
vectorizer = joblib.load(VECT_PATH)
label_encoder = None
if os.path.exists(LE_PATH):
    label_encoder = joblib.load(LE_PATH)

def predict_review(text):
    X = vectorizer.transform([text])
    pred = model.predict(X)[0]
    if label_encoder is not None:
        return label_encoder.inverse_transform([pred])[0]
    return "Real" if int(pred) == 1 else "Fake"

@app.route('/fake_review_detector', methods=['GET','POST'])
def fake_review_detector():
    result = None
    text = ""
    if request.method == 'POST':
        text = request.form.get('review', '')
        result = predict_review(text)
    return render_template('fake_review_detector.html', result=result, review=text)

# Price Comparison
from scraping_functions import scrape_croma, scrape_flipkart

@app.route('/price_comparison', methods=['GET', 'POST'])
def price_comparison():
    if request.method == 'POST':
        product_name = request.form['product']
        
        croma_name, croma_price, croma_url = scrape_croma(product_name)
        flipkart_name, flipkart_price, flipkart_url = scrape_flipkart(product_name)
        
        # Debug output
        print(f"Croma result: {croma_name}, {croma_price}, {croma_url}")
        print(f"Flipkart result: {flipkart_name}, {flipkart_price}, {flipkart_url}")
        
        recommendation = None
        if croma_price and flipkart_price:
            if croma_price < flipkart_price:
                recommendation = {
                    'site': 'Croma',
                    'price': croma_price,
                    'url': croma_url,
                    'savings': flipkart_price - croma_price
                }
            else:
                recommendation = {
                    'site': 'Flipkart',
                    'price': flipkart_price,
                    'url': flipkart_url,
                    'savings': croma_price - flipkart_price
                }
        
        return render_template('comparison_results.html', 
                            product=product_name,
                            croma_name=croma_name,
                            croma_price=croma_price,
                            croma_url=croma_url,
                            flipkart_name=flipkart_name,
                            flipkart_price=flipkart_price,
                            flipkart_url=flipkart_url,
                            recommendation=recommendation)
    
    return render_template('price_comparison.html')

# Price Tracker Routes
@app.route('/price_tracker', methods=['GET', 'POST'])
def price_tracker():
    if 'username' not in session:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        product_name = request.form['product_name']
        desired_price = request.form['desired_price']
        email = request.form['email']
        
        # Validate inputs
        if not product_name or not desired_price or not email:
            flash('Please fill all fields')
            return redirect(url_for('price_tracker'))
        
        try:
            desired_price = float(desired_price)
        except ValueError:
            flash('Please enter a valid price')
            return redirect(url_for('price_tracker'))
        
        # Scrape current price
        name, current_price, product_url = scrape_flipkart_price_tracker(product_name)
        
        if current_price is None:
            flash('Could not retrieve product price. Please check the product name.')
            return redirect(url_for('price_tracker'))
        
        # Save to database
        tracker = PriceTracker(
            product_name=name,
            current_price=current_price,
            desired_price=desired_price,
            email=email,
            product_url=product_url
        )
        db.session.add(tracker)
        db.session.commit()
        
        flash(f'Product "{name}" added for tracking! Current price: ₹{current_price}')
        return redirect(url_for('price_tracker'))
    
    return render_template('price_tracker.html')

@app.route('/trackings')
def trackings():
    """Show all active trackings"""
    if 'username' not in session:
        return redirect(url_for('home'))
        
    active_trackings = PriceTracker.query.filter_by(is_active=True).order_by(PriceTracker.created_at.desc()).all()
    return render_template('trackings.html', trackings=active_trackings)

# Utility functions for price tracker
def clean_price(price_text):
    """Extract numeric value from price string"""
    if not price_text:
        return None
    # Remove non-digit characters except decimal point
    cleaned = re.sub(r'[^\d.]', '', price_text)
    try:
        return float(cleaned)
    except ValueError:
        return None

def make_absolute(href, base_url):
    """Convert relative URL to absolute"""
    if href.startswith('http'):
        return href
    return base_url + href

def scrape_flipkart_price_tracker(product_name):
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

        search_q = product_name.replace(' ', '+')
        search_url = f"https://www.flipkart.com/search?q={search_q}"
        driver.get(search_url)
        time.sleep(3)

        name = driver.find_element(By.CSS_SELECTOR, 'div.KzDlHZ').text
        price = clean_price(driver.find_element(By.CSS_SELECTOR, 'div.Nx9bqj').text)
        href = driver.find_element(By.CSS_SELECTOR, 'a.CGtC98').get_attribute('href')

        product_url = make_absolute(href, "https://www.flipkart.com")

        return name, price, product_url

    except Exception as e:
        print(f"Flipkart Scraping Error: {str(e)}")
        return None, None, None
    finally:
        if driver:
            driver.quit()

def send_email(recipient, product_name, current_price, product_url):
    """Send price drop notification email"""
    email_address = os.environ.get('EMAIL_ADDRESS')
    email_password = os.environ.get('EMAIL_PASSWORD')
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    
    if not all([email_address, email_password]):
        print("Email credentials not configured. Cannot send notification.")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = email_address
        msg['To'] = recipient
        msg['Subject'] = f'Price Drop Alert for {product_name}'
        
        body = f"""
        Good news! The price for {product_name} has dropped to ₹{current_price}.
        
        Product URL: {product_url}
        
        Happy shopping!
        """
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(email_address, email_password)
        text = msg.as_string()
        server.sendmail(email_address, recipient, text)
        server.quit()
        
        print(f"Notification email sent to {recipient}")
        return True
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        return False

def check_price_changes():
    """Background task to check for price changes"""
    with app.app_context():
        while True:
            try:
                # Get all active trackers
                active_trackers = PriceTracker.query.filter_by(is_active=True).all()
                
                for tracker in active_trackers:
                    # Scrape current price using product name search
                    name, price, product_url = scrape_flipkart_price_tracker(tracker.product_name)
                    
                    if price is None:
                        print(f"Could not retrieve price for {tracker.product_name}")
                        continue
                    
                    # Update current price
                    tracker.current_price = price
                    db.session.commit()
                    
                    # Check if price has dropped to or below desired price
                    if price <= tracker.desired_price:
                        # Send notification
                        success = send_email(
                            tracker.email, 
                            tracker.product_name, 
                            price, 
                            tracker.product_url or product_url
                        )
                        if success:
                            # Deactivate this tracking request
                            tracker.is_active = False
                            tracker.notification_sent = True
                            tracker.notification_sent_at = datetime.utcnow()
                            db.session.commit()
                            print(f"Price alert sent and tracking deactivated for {tracker.product_name}")
            
            except Exception as e:
                print(f"Error in price check: {str(e)}")
            
            # Wait for 1 hour before checking again
            time.sleep(3600)

# ---------------- Chatbot ----------------
@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():
    response = None
    if request.method == "POST":
        user_message = request.form.get("message", "").lower()

        # Simple rule-based responses
        if "hello" in user_message or "hi" in user_message:
            response = "Hello 👋! I’m ShopSage Assistant. How can I help you today?"
        elif "price" in user_message and "compare" in user_message:
            response = "You can use our Price Comparison tool to check prices between Flipkart and Croma."
        elif "track" in user_message or "alert" in user_message:
            response = "You can set a price alert in our Price Tracker, and we’ll notify you when the price drops."
        elif "review" in user_message or "fake" in user_message:
            response = "Our Fake Review Detector helps you check if a review is genuine or not."
        elif "help" in user_message:
            response = "Sure! I can help you with:\n1️⃣ Price Comparison\n2️⃣ Fake Review Detection\n3️⃣ Price Tracker"
        else:
            response = "Sorry, I didn’t understand 🤔. You can ask me about price comparison, reviews, or tracking."

    return render_template("chatbot.html", response=response)


# Start background thread for price checking
thread = threading.Thread(target=check_price_changes, daemon=True)
thread.start()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)