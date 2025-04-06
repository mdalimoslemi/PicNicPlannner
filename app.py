from flask import Flask, render_template, request, jsonify
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import bleach
import re
import random
import datetime
import os
import google.generativeai as genai
from dotenv import load_dotenv
from logging import StreamHandler

# Load environment variables
load_dotenv()

# Initialize security extensions
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
talisman = Talisman()

# Initialize Flask app
app = Flask(__name__)

# Configuration
class Config:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    SECRET_KEY = os.environ.get("SECRET_KEY")
    CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(minutes=30)
    WTF_CSRF_TIME_LIMIT = 3600

app.config.from_object(Config)

# Initialize security
csrf.init_app(app)
limiter.init_app(app)
talisman.init_app(app,
    content_security_policy={
        'default-src': "'self'",  # Allow resources only from the same origin
        'script-src': "'self'",  # Allow scripts only from the same origin
        'style-src': "'self' fonts.googleapis.com",  # Allow styles from the same origin and Google Fonts
        'font-src': "'self' fonts.gstatic.com",  # Allow fonts from the same origin and Google Fonts
        'img-src': "'self' data:",  # Allow images from the same origin and inline data URIs
        'connect-src': "'self'",  # Allow AJAX requests only to the same origin
        'frame-src': "'none'",  # Disallow embedding in iframes
        'object-src': "'none'",  # Disallow plugins like Flash
    },
    force_https=True
)

# Initialize Gemini
try:
    genai.configure(api_key=Config.GEMINI_API_KEY)
except Exception as e:
    pass  # Handle Gemini API initialization failure gracefully

def clean_weather_text(text):
    """
    Removes Markdown formatting and cleans up weather text.
    """
    cleaned = text.replace('*', '').replace('**', '')
    cleaned = cleaned.replace('\n\n', '\n').strip()
    return cleaned

def format_weather_response(text):
    """
    Formats and cleans the weather response to remove redundant information.
    """
    # Remove introductory phrases
    text = text.replace("Okay, here's the current weather information for ", "")
    text = text.replace("Okay, here's the weather forecast for ", "")
    text = text.replace("The current temperature", "Temperature")
    text = text.replace("The temperature is currently", "Temperature")
    text = text.replace("Generally, ", "")
    text = text.replace("The wind is ", "Wind: ")
    text = text.replace("The humidity is ", "Humidity: ")
    
    # Clean up any remaining artifacts
    return clean_weather_text(text)

def get_weather(city):
    """
    Fetches weather data for a given city using the Gemini API.
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"Give me a concise weather report for {city} with temperature, condition, wind, and humidity"
        
        response = model.generate_content(prompt)
        full_response = format_weather_response(response.text)
        
        return {"weather_description": full_response}

    except Exception as e:
        return {"error": "Unable to fetch weather information. Please try again later."}

def suggest_park(city):
    """
    Suggests a park in the given city.
    """
    return f"Gemini suggests a park in {city} for a delightful picnic."

def find_next_sunny_day():
    """
    Predicts the next sunny day.
    """
    # Simulate next sunny day
    today = datetime.date.today()
    days_ahead = random.randint(1, 5)
    next_sunny_day = today + datetime.timedelta(days=days_ahead)
    return next_sunny_day.strftime("%Y-%m-%d")

def generate_text(prompt):
    """
    Generates text using the Gemini API.
    """
    return f"{prompt}"

def sanitize_input(text):
    """Sanitize user input"""
    # Remove any HTML tags
    text = bleach.clean(text, tags=[], strip=True)
    # Only allow alphanumeric characters and basic punctuation
    text = re.sub(r'[^a-zA-Z0-9\s,.-]', '', text)
    return text

# Store previous suggestions (in-memory, for demonstration)
previous_suggestions = []

@app.route("/", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def index():
    global previous_suggestions

    if request.method == "POST":
        previous_suggestions = []
        city = sanitize_input(request.form.get("city", ""))
        if not city:
            return jsonify({"error": "Invalid city name"}), 400
        weather = get_weather(city)
        if "error" in weather:
            prompt = f"Could not retrieve weather information for {city}. Please check the city name."
            suggestion_text = generate_text(prompt)
        else:
            weather_description = weather["weather_description"]
            prompt = f" You asked for {city} {weather_description}. "
            if "sunny" in weather_description.lower() or "clear" in weather_description.lower():
                park = suggest_park(city)
                prompt += f"Perfect for a picnic! {park}"
            else:
                next_sunny = find_next_sunny_day()
                prompt += f"Not ideal for a picnic today. Next sunny day: {next_sunny}"
            suggestion_text = generate_text(prompt)

        previous_suggestions.append(suggestion_text)
        return jsonify(suggestions=previous_suggestions)

    else:
        return render_template("index.html", suggestions=previous_suggestions)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
