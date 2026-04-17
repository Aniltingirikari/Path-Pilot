from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
import json
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, firestore
import uuid

# Load environment variables
load_dotenv() 

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app, supports_credentials=True)

# ========================================
# FIREBASE INITIALIZATION (ADMIN SDK)
# ========================================

firebase_initialized = False
db = None

# Check if firebase-config.json exists (local development)
if os.path.exists('firebase-config.json'):
    try:
        cred = credentials.Certificate('firebase-config.json')
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        firebase_initialized = True
        print("✅ Firebase initialized with local config")
    except Exception as e:
        print(f"⚠️ Firebase error: {e}")
        firebase_initialized = False
else:
    # Use environment variables (for production)
    print("⚠️ firebase-config.json not found. Running in demo mode")
    firebase_initialized = False

# ========================================
# AUTHENTICATION DECORATOR
# ========================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ========================================
#  TRAVEL PLANNER
# ========================================

class TravelPlanner:
    def __init__(self):
        self.usd_to_inr = 85
        
        # ========== TRANSPORT COSTS ==========
        self.train_costs = {
            ("hyderabad", "tirupati"): 400,
            ("hyderabad", "chennai"): 500,
            ("hyderabad", "bangalore"): 420,
            ("hyderabad", "mumbai"): 520,
            ("hyderabad", "delhi"): 900,
            ("hyderabad", "goa"): 480,
            ("mumbai", "goa"): 350,
            ("delhi", "agra"): 200,
            ("chennai", "bangalore"): 250,
        }
        
        self.bus_costs = {
            ("hyderabad", "tirupati"): 600,
            ("hyderabad", "chennai"): 800,
            ("hyderabad", "bangalore"): 700,
            ("hyderabad", "goa"): 900,
        }
        
        self.flight_costs = {
            ("hyderabad", "usa"): 8000,
            ("hyderabad", "uk"): 7000,
            ("hyderabad", "canada"): 9000,
            ("hyderabad", "australia"): 6500,
            ("hyderabad", "dubai"): 30000,
            ("hyderabad", "singapore"): 25000,
            ("hyderabad", "thailand"): 20000,
            ("hyderabad", "malaysia"): 22000,
            ("hyderabad", "goa"): 15000,
            ("hyderabad", "delhi"): 1200,
            ("mumbai", "goa"): 800,
        }
        
        self.car_rental_costs = {
            "small": 1500,
            "suv": 2500,
            "luxury": 5000
        }
        
        # ========== HOTEL DATABASE ==========
        self.hotels = {
            "tirupati": {
                "budget": [{"name": "Tirumala Dormitory", "price": 200, "rating": 3.5, "amenities": ["Free WiFi", "Lockers"]},
                           {"name": "Sri Balaji Lodge", "price": 500, "rating": 4.0, "amenities": ["AC", "TV", "Free WiFi"]}],
                "mid": [{"name": "Hotel Bliss", "price": 1200, "rating": 4.2, "amenities": ["AC", "Restaurant", "Free WiFi", "Parking"]},
                        {"name": "Mayura Hotel", "price": 1500, "rating": 4.0, "amenities": ["AC", "Restaurant", "Room Service"]}],
                "luxury": [{"name": "Fortune Grand", "price": 3500, "rating": 4.5, "amenities": ["Pool", "Spa", "Restaurant", "Gym", "Free Breakfast"]}]
            },
            "goa": {
                "budget": [{"name": "Zostel Goa", "price": 500, "rating": 4.3, "amenities": ["Dormitory", "Common Room", "Kitchen"]},
                           {"name": "Jungle Hostel", "price": 600, "rating": 4.1, "amenities": ["Pool", "Free WiFi", "Cafe"]}],
                "mid": [{"name": "Resort Rio", "price": 2500, "rating": 4.2, "amenities": ["Pool", "Restaurant", "Beach Access"]}],
                "luxury": [{"name": "Taj Fort Aguada", "price": 12000, "rating": 4.8, "amenities": ["Pool", "Spa", "Beach Front", "Fine Dining"]}]
            }
        }
        
        # ========== SEASONAL INFORMATION ==========
        self.seasons = {
            "tirupati": {
                "peak": "Oct-Mar",
                "off": "Apr-Sep",
                "weather": "Pleasant in winter, hot in summer",
                "best_time": "November to February",
                "festivals": ["Brahmotsavam (Sep-Oct)", "Vaikunta Ekadasi (Dec-Jan)"],
                "packing": ["Light cotton clothes", "Umbrella if rainy", "Comfortable shoes"]
            },
            "goa": {
                "peak": "Nov-Feb",
                "off": "May-Sep",
                "weather": "Pleasant in winter, monsoon in summer",
                "best_time": "November to February",
                "festivals": ["Carnival (Feb)", "Sunburn Festival (Dec)"],
                "packing": ["Swimwear", "Sunscreen", "Light clothes", "Raincoat if monsoon"]
            },
            "default": {
                "peak": "Oct-Mar",
                "off": "Apr-Sep",
                "weather": "Pleasant weather",
                "best_time": "October to March",
                "festivals": ["Check local calendar"],
                "packing": ["Seasonal clothing", "Comfortable shoes"]
            }
        }
        
        # ========== LOCATION TIPS ==========
        self.location_tips = {
            "tirupati": {
                "must_try": ["Tirumala Laddu", "Andhra Thali", "Gongura Pickle"],
                "attractions": ["Tirumala Temple", "Akasa Ganga", "Silathoranam", "Sri Venkateswara Museum"],
                "transport_tips": ["Free buses to temple", "Walk from Alipiri (4km)", "Special darshan tickets online"],
                "local_etiquette": ["Remove shoes before temple", "Dress modestly", "No phones inside temple"]
            },
            "goa": {
                "must_try": ["Fish Curry Rice", "Feni", "Bebinca", "Kingfish"],
                "attractions": ["Baga Beach", "Fort Aguada", "Basilica of Bom Jesus", "Dudhsagar Falls"],
                "transport_tips": ["Rent a scooter (₹300-500/day)", "Local buses are cheap", "Uber available"],
                "local_etiquette": ["Respect beach rules", "Cover up in churches", "Bargain at markets"]
            },
            "default": {
                "must_try": ["Local cuisine", "Street food", "Traditional dishes"],
                "attractions": ["Main landmarks", "Local markets", "Cultural sites"],
                "transport_tips": ["Public transport", "Taxis", "Walking tours"],
                "local_etiquette": ["Respect local customs", "Ask before photos", "Dress appropriately"]
            }
        }
    
    def get_transport_cost(self, from_city, to_city, travelers, transport_mode):
        """Get cost based on transport mode"""
        key = (from_city.lower(), to_city.lower())
        
        if transport_mode == "train":
            cost = self.train_costs.get(key, 500)
        elif transport_mode == "bus":
            cost = self.bus_costs.get(key, 700)
        elif transport_mode == "flight":
            cost = self.flight_costs.get(key, 2000)
        elif transport_mode == "car":
            cost = self.car_rental_costs["small"]
        else:
            cost = 500
            
        return cost * travelers
    
    def format_table(self, headers, data):
        """Create beautifully formatted ASCII table"""
        if not headers or not data:
            return "No data available"
        
        # Calculate column widths
        col_widths = [len(str(h)) for h in headers]
        for row in data:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Create top border
        table = "┌" + "┬".join(["─" * (col_widths[i] + 2) for i in range(len(headers))]) + "┐\n"
        
        # Header row
        table += "│"
        for i, header in enumerate(headers):
            table += f" {str(header):<{col_widths[i]}} │"
        table += "\n"
        
        # Header separator
        table += "├" + "┼".join(["─" * (col_widths[i] + 2) for i in range(len(headers))]) + "┤\n"
        
        # Data rows
        for row in data:
            table += "│"
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    cell_str = str(cell)
                    clean_cell = cell_str.replace('₹', '').replace(',', '').replace('⭐', '').strip()
                    if clean_cell.replace('.', '').isdigit() or (clean_cell.startswith('-') and clean_cell[1:].replace('.', '').isdigit()):
                        table += f" {cell_str:>{col_widths[i]}} │"
                    else:
                        table += f" {cell_str:<{col_widths[i]}} │"
            table += "\n"
        
        # Bottom border
        table += "└" + "┴".join(["─" * (col_widths[i] + 2) for i in range(len(headers))]) + "┘"
        
        return table
    
    def get_hotel_recommendations(self, destination, budget_per_night):
        """Get hotel recommendations based on budget"""
        dest_key = destination.lower()
        hotels = self.hotels.get(dest_key, {})
        
        if budget_per_night < 1000:
            category = "budget"
        elif budget_per_night < 3000:
            category = "mid"
        else:
            category = "luxury"
        
        recommendations = hotels.get(category, [])
        if not recommendations:
            recommendations = [{"name": "Local Lodge", "price": 500, "rating": 3.0, "amenities": ["Basic amenities"]}]
        
        return recommendations, category
    
    def get_seasonal_info(self, destination, month):
        """Get seasonal information for destination"""
        dest_key = destination.lower()
        season_info = self.seasons.get(dest_key, self.seasons["default"])
        
        month_num = int(month)
        if 11 <= month_num <= 2 or month_num == 3:
            current = "Peak Season"
        else:
            current = "Off Season"
        
        return {
            "current_season": current,
            "best_time": season_info["best_time"],
            "weather": season_info["weather"],
            "festivals": season_info["festivals"],
            "packing": season_info["packing"],
            "peak_months": season_info["peak"],
            "off_months": season_info["off"]
        }
    
    def get_location_tips(self, destination):
        """Get location-specific travel tips"""
        dest_key = destination.lower()
        return self.location_tips.get(dest_key, self.location_tips["default"])
    
    def plan_domestic_trip(self, from_city, to_city, days, travelers, budget, transport_mode, month):
        """Enhanced domestic trip planning"""
        
        # Get transport cost
        travel_cost = self.get_transport_cost(from_city, to_city, travelers, transport_mode)
        
        # Get hotel recommendations
        daily_budget = (budget - travel_cost) / days if budget > travel_cost else 500
        hotels, hotel_category = self.get_hotel_recommendations(to_city, daily_budget)
        
        # Calculate hotel cost
        avg_hotel_price = hotels[0]["price"] if hotels else 500
        hotel_cost = avg_hotel_price * days
        
        # Other costs
        food_cost = 250 * days
        local_cost = 150 * days
        
        total_cost = travel_cost + hotel_cost + food_cost + local_cost
        within_budget = total_cost <= budget
        
        # Get seasonal info
        season_info = self.get_seasonal_info(to_city, month)
        
        # Get location tips
        location_tips = self.get_location_tips(to_city)
        
        # Transport options - Simple list format (no table)
        transport_train = self.get_transport_cost(from_city, to_city, travelers, 'train')
        transport_bus = self.get_transport_cost(from_city, to_city, travelers, 'bus')
        transport_flight = self.get_transport_cost(from_city, to_city, travelers, 'flight')
        transport_car = self.get_transport_cost(from_city, to_city, travelers, 'car')
        
        transport_list = f"""
                           TRANSPORT OPTIONS                            
  🚆 TRAIN  : ₹{transport_train:,}  (IRCTC - Book 120 days ahead)                                    
  🚌 BUS    : ₹{transport_bus:,}  (RedBus - Book 30 days ahead)                                     
  ✈️ FLIGHT : ₹{transport_flight:,} (MakeMyTrip - Book 2 months ahead)                                 
  🚗 CAR    : ₹{transport_car:,}  (Zoomcar - Self drive rental)                                     

💡 Selected: {transport_mode.upper()} (₹{travel_cost:,})
"""
        
        # Hotel recommendations - Simple list format (no table)
        hotel_list = f"""
                    HOTEL RECOMMENDATIONS ({hotel_category.upper()})                            
"""
        for h in hotels[:3]:
            hotel_list += f"  🏨 {h['name']:<30} ₹{h['price']:>6}  ⭐{h['rating']}  {', '.join(h['amenities'][:2])}\n"
        hotel_list += ""
        
        # Food & attractions - Simple list format (no table)
        food_attractions = f"""

                         MUST-TRY FOOD & ATTRACTIONS                          

  🍽️ MUST-TRY FOOD:                                                          
"""
        for food in location_tips['must_try']:
            food_attractions += f"    • {food}\n"
        
        food_attractions += f"""

  📍 TOP ATTRACTIONS:                                                         
"""
        for attraction in location_tips['attractions']:
            food_attractions += f"   • {attraction}\n"
        
        food_attractions += f"""

  🚌 LOCAL TRANSPORT TIPS:                                                    
"""
        for tip in location_tips['transport_tips']:
            food_attractions += f"    • {tip}\n"
        
        food_attractions += f"""

  📋 LOCAL ETIQUETTE:                                                         
"""
        for etiquette in location_tips['local_etiquette']:
            food_attractions += f"    • {etiquette}\n"
        
        food_attractions += ""
        
        # Seasonal info table (keep this as table - it's fine)
        seasonal_data = [
            ["Current Season", season_info['current_season']],
            ["Best Time", season_info['best_time']],
            ["Weather", season_info['weather']],
            ["Peak Months", season_info['peak_months']],
            ["Off Months", season_info['off_months']],
            ["Festivals", ", ".join(season_info['festivals'])],
            ["Packing Tips", ", ".join(season_info['packing'])]
        ]
        seasonal_table = self.format_table(["Category", "Information"], seasonal_data)
        
        # Cost breakdown table (keep this as table - it's fine)
        cost_data = [
            [f"Travel ({transport_mode})", f"₹{travel_cost:,}", f"{travelers} person(s)"],
            [f"Hotel ({days} nights)", f"₹{hotel_cost:,}", f"{hotel_category} stay"],
            [f"Food ({days} days)", f"₹{food_cost:,}", "3 meals per day"],
            ["Local Transport", f"₹{local_cost:,}", "Auto/bus/local travel"],
            ["─" * 20, "─" * 15, "─" * 20],
            ["TOTAL", f"₹{total_cost:,}", ""],
            ["Your Budget", f"₹{budget:,}", ""],
            ["Remaining", f"₹{budget - total_cost:,}", "✅ Within Budget" if within_budget else "⚠️ Over Budget"]
        ]
        cost_table = self.format_table(["Category", "Cost (₹)", "Details"], cost_data)
        
        status_text = "✅ WITHIN BUDGET" if within_budget else "⚠️ OVER BUDGET"
        
        itinerary = f"""
{'='*80}
✈️ PATH PILOT - ENHANCED DOMESTIC TRIP PLAN
{'='*80}

📍 {from_city.upper()} → {to_city.upper()}
📅 Duration: {days} days | 👥 Travelers: {travelers}
🚗 Selected Transport: {transport_mode.upper()}
💰 Budget: ₹{budget:,.0f} | 💵 Estimated: ₹{total_cost:,.0f}
{status_text}

{'='*80}
🌤️ SEASONAL INFORMATION
{'='*80}

{seasonal_table}

{'='*80}
🚗 TRANSPORT OPTIONS
{'='*80}

{transport_list}

{'='*80}
🏨 HOTEL RECOMMENDATIONS
{'='*80}

{hotel_list}

{'='*80}
🍴 TRAVEL TIPS & ATTRACTIONS
{'='*80}

{food_attractions}

{'='*80}
💰 DETAILED COST BREAKDOWN
{'='*80}

{cost_table}

{'='*80}
✅ MONEY-SAVING TIPS
{'='*80}

• Book {transport_mode} tickets in advance for best prices
• Stay in {hotel_category} hotels to save on accommodation
• Eat at local eateries instead of tourist restaurants
• Use public transport instead of taxis
• Travel during off-season ({season_info['off_months']}) for better deals

{'='*80}
🎉 Safe travels! - Path Pilot Team
{'='*80}
"""
        return itinerary, total_cost, within_budget
    
    def plan_international_trip(self, from_city, to_city, days, travelers, budget, month):
        """Enhanced international trip planning"""
        
        flight_cost = self.get_transport_cost(from_city, to_city, travelers, "flight")
        hotel_cost = 6000 * days
        food_cost = 3400 * days
        local_cost = 1700 * days
        
        visa_cost = 16000
        insurance_cost = 8000
        buffer_cost = 25000
        
        subtotal = flight_cost + hotel_cost + food_cost + local_cost
        total_cost = subtotal + visa_cost + insurance_cost + buffer_cost
        within_budget = total_cost <= budget
        
        # Get seasonal info
        season_info = self.get_seasonal_info(to_city, month)
        
        # Get location tips
        location_tips = self.get_location_tips(to_city)
        
        # Cost breakdown table
        cost_data = [
            ["Flight", f"₹{flight_cost:,}", f"Round trip ({travelers} person(s))"],
            [f"Hotel ({days} nights)", f"₹{hotel_cost:,}", "Mid-range hotel"],
            [f"Food ({days} days)", f"₹{food_cost:,}", "3 meals per day"],
            ["Local Transport", f"₹{local_cost:,}", "Public transport/taxis"],
            ["─" * 20, "─" * 15, "─" * 20],
            ["SUBTOTAL", f"₹{subtotal:,}", "Before extras"],
            ["Visa", f"₹{visa_cost:,}", "Tourist visa fee"],
            ["Insurance", f"₹{insurance_cost:,}", "Travel insurance"],
            ["Buffer", f"₹{buffer_cost:,}", "Emergency fund"],
            ["─" * 20, "─" * 15, "─" * 20],
            ["GRAND TOTAL", f"₹{total_cost:,}", ""],
            ["Your Budget", f"₹{budget:,}", ""],
            ["Remaining", f"₹{budget - total_cost:,}", "✅ Within Budget" if within_budget else "⚠️ Over Budget"]
        ]
        cost_table = self.format_table(["Category", "Cost (₹)", "Details"], cost_data)
        
        # Seasonal info table
        seasonal_data = [
            ["Best Time", season_info['best_time']],
            ["Weather", season_info['weather']],
            ["Peak Season", season_info['peak_months']],
            ["Off Season", season_info['off_months']],
            ["Festivals", ", ".join(season_info['festivals'])],
            ["Packing Tips", ", ".join(season_info['packing'])]
        ]
        seasonal_table = self.format_table(["Category", "Information"], seasonal_data)
        
        # Food & attractions - Simple list format
        food_attractions = f"""

                         MUST-TRY FOOD & ATTRACTIONS                          

  🍽️ MUST-TRY FOOD:                                                          
"""
        for food in location_tips['must_try']:
            food_attractions += f"     • {food}\n"
        
        food_attractions += f"""

  📍 TOP ATTRACTIONS:                                                        
"""
        for attraction in location_tips['attractions']:
            food_attractions += f"    • {attraction}\n"
        
        food_attractions += f"""

  🚌 TRANSPORT TIPS:                                                          
"""
        for tip in location_tips['transport_tips']:
            food_attractions += f"    • {tip}\n"
        
        food_attractions += ""
        
        status_text = "✅ WITHIN BUDGET" if within_budget else "⚠️ OVER BUDGET"
        
        itinerary = f"""
{'='*80}
🌍 PATH PILOT - INTERNATIONAL TRIP PLAN
{'='*80}

📍 {from_city.upper()} → {to_city.upper()}
📅 Duration: {days} days | 👥 Travelers: {travelers}
💰 Budget: ₹{budget:,.0f} | 💵 Estimated: ₹{total_cost:,.0f}
{status_text}
💱 Exchange Rate: 1 USD = ₹85

{'='*80}
🌤️ SEASONAL INFORMATION
{'='*80}

{seasonal_table}

{'='*80}
✈️ FLIGHT INFORMATION
{'='*80}


 • Round trip cost: ₹{flight_cost:,.0f}                                                      
 • Duration: 20-24 hours (including layover)                                              
 • Airlines: Emirates, Qatar Airways, Singapore Airlines                                  
 • Best time to book: 2-3 months in advance                                               
 • Cheapest months: May-September                                                        

{'='*80}
🍴 TRAVEL TIPS & ATTRACTIONS
{'='*80}

{food_attractions}

{'='*80}
💰 DETAILED COST BREAKDOWN
{'='*80}

{cost_table}

{'='*80}
✅ MONEY-SAVING TIPS
{'='*80}

• Book flights 2-3 months in advance for best prices
• Use comparison sites (Skyscanner, Kayak)
• Stay in hostels if solo traveler (saves 50-60%)
• Eat where locals eat (cheaper and authentic)
• Get travel insurance for medical emergencies
• Use public transport instead of taxis/Uber

{'='*80}
🎉 Safe travels! - Path Pilot Team
{'='*80}
"""
        return itinerary, total_cost, within_budget

planner = TravelPlanner()

# ========================================
# FLASK ROUTES
# ========================================

# ========================================
# FLASK ROUTES
# ========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/firebase-config')
def get_firebase_config():
    """Return Firebase config from environment variables"""
    return jsonify({
        'apiKey': os.getenv('FIREBASE_API_KEY', ''),
        'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN', ''),
        'databaseURL': os.getenv('FIREBASE_DATABASE_URL', ''),
        'projectId': os.getenv('FIREBASE_PROJECT_ID', ''),
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId': os.getenv('FIREBASE_APP_ID', ''),
        'measurementId': os.getenv('FIREBASE_MEASUREMENT_ID', '')
    })

@app.route('/api/verify_token', methods=['POST'])
def verify_token():
    try:
        data = request.get_json()
        id_token = data.get('idToken')
        
        if not id_token:
            return jsonify({'error': 'No token provided'}), 400
        
        if firebase_initialized:
            decoded_token = firebase_auth.verify_id_token(id_token)
            session['user_id'] = decoded_token['uid']
            session['user_email'] = decoded_token.get('email', '')
            session['user_name'] = decoded_token.get('name', session['user_email'].split('@')[0])
        else:
            session['user_id'] = 'demo_user'
            session['user_email'] = 'demo@example.com'
            session['user_name'] = 'Demo User'
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/signup', methods=['POST'])
def signup():
    # ... rest of your routes
    if not firebase_initialized:
        return jsonify({'success': True, 'message': 'Demo mode'}), 200
    
    try:
        data = request.get_json()
        email = data.get('email')
        name = data.get('name')
        uid = data.get('uid')
        
        user_data = {
            'name': name,
            'email': email,
            'created_at': datetime.now().isoformat(),
            'trips': []
        }
        db.collection('users').document(uid).set(user_data)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/save_trip', methods=['POST'])
@login_required
def save_trip():
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        
        if not firebase_initialized:
            return jsonify({'success': True, 'message': 'Trip saved (demo mode)'}), 200
        
        trip_data = {
            'id': str(uuid.uuid4()),
            'from': data.get('from'),
            'to': data.get('to'),
            'start_date': data.get('start_date'),
            'end_date': data.get('end_date'),
            'budget': data.get('budget'),
            'travelers': data.get('travelers'),
            'transport_mode': data.get('transport_mode', 'train'),
            'trip_type': data.get('trip_type'),
            'itinerary': data.get('itinerary'),
            'saved_at': datetime.now().isoformat()
        }
        
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            trips = user_doc.to_dict().get('trips', [])
            trips.append(trip_data)
            user_ref.update({'trips': trips})
        else:
            user_ref.set({'trips': [trip_data]})
        
        return jsonify({'success': True, 'trip_id': trip_data['id']})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/get_trips', methods=['GET'])
@login_required
def get_trips():
    try:
        user_id = session.get('user_id')
        
        if not firebase_initialized:
            return jsonify({'success': True, 'trips': []}), 200
        
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            trips = user_doc.to_dict().get('trips', [])
            return jsonify({'success': True, 'trips': trips})
        return jsonify({'success': True, 'trips': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/plan_trip', methods=['POST'])
def plan_trip():
    try:
        data = request.get_json()
        
        trip_type = data.get('trip_type', 'domestic')
        from_city = data.get('fromPlace')
        to_city = data.get('destination')
        start_date = data.get('startDate')
        end_date = data.get('endDate')
        budget = float(data.get('budget'))
        travelers = int(data.get('numTravelers'))
        transport_mode = data.get('transportMode', 'train')
        
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end - start).days
        month = start.month
        
        if days <= 0:
            return jsonify({'error': 'End date must be after start date'}), 400
        
        if trip_type == 'domestic':
            itinerary, total_cost, within_budget = planner.plan_domestic_trip(
                from_city, to_city, days, travelers, budget, transport_mode, month
            )
        else:
            itinerary, total_cost, within_budget = planner.plan_international_trip(
                from_city, to_city, days, travelers, budget, month
            )
        
        return jsonify({
            'success': True,
            'itinerary': itinerary,
            'total_cost': total_cost,
            'budget': budget,
            'within_budget': within_budget
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'firebase': firebase_initialized,
        'session': 'active' if 'user_id' in session else 'none'
    })

if __name__ == '__main__':
    print("\n" + "="*80)
    print("✈️  PATH PILOT - Travel Planning System")
    print("="*80)
    print(f"\n🔥 Firebase: {'Connected' if firebase_initialized else 'Demo Mode'}")
    print("📍 Server: http://127.0.0.1:5000")
    print("\n✨ ENHANCED FEATURES:")
    print("   • Beautiful ASCII formatted tables")
    print("   • Seasonal recommendations")
    print("   • Multiple transport options (Train/Bus/Flight/Car)")
    print("   • Hotel recommendations with prices")
    print("   • Local food & attraction tips")
    print("   • Cultural etiquette guides")
    print("="*80 + "\n")
    
    app.run(debug=True, host='127.0.0.1', port=5000)