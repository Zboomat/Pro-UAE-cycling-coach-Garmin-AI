import streamlit as st
import pandas as pd
import datetime
import os
import json
import google.generativeai as genai
from garminconnect import Garmin

# --- KONFIGURATION ---
DATA_FILE = "training_history.csv"
MAINTENANCE_FILE = "service_log.json"

st.set_page_config(page_title="UAE Service Course", page_icon="🔧", layout="wide")

# --- KLASS: SERVICE COURSE (MEKANIKER) ---
class ServiceCourse:
    def __init__(self):
        # Service-intervall i kilometer
        self.rules = {
            "Smörja kedjan": 300,      # Var 300:e km
            "Tvätta cykeln": 500,      # Var 500:e km
            "Kontrollera däck": 1500,  # Var 1500:e km
            "Byta kedja": 3000,        # Var 3000:e km (konservativt)
            "Byta kassett": 8000       # Var 8000:e km
        }
        self.log = self.load_log()

    def load_log(self):
        if os.path.exists(MAINTENANCE_FILE):
            with open(MAINTENANCE_FILE, 'r') as f:
                return json.load(f)
        # Standard: Antag att allt är servat vid 0 km
        return {k: 0 for k in self.rules.keys()}

    def save_service(self, item, current_total_km):
        """Nollställer räknaren för en specifik del."""
        self.log[item] = current_total_km
        with open(MAINTENANCE_FILE, 'w') as f:
            json.dump(self.log, f)

    def check_status(self, total_ridden_km):
        """Returnerar status för alla delar."""
        status_report = []
        for item, interval in self.rules.items():
            last_service = self.log.get(item, 0)
            km_since_service = total_ridden_km - last_service
            usage_pct = min(km_since_service / interval, 1.0)
            
            status = {
                "item": item,
                "km_driven": int(km_since_service),
                "km_limit": interval,
                "usage": usage_pct,
                "needs_action": km_since_service >= interval
            }
            status_report.append(status)
        return status_report

# --- KLASS: GARMIN WORKOUT CREATOR (Samma som förut) ---
class GarminWorkoutCreator:
    def __init__(self, email, password):
        self.client = None
        self.email = email
        self.password = password

    def connect(self):
        try:
            self.client = Garmin(self.email, self.password)
            self.client.login()
            return True
        except Exception as e:
            st.error(f"Garmin Login misslyckades: {e}")
            return False

    def create_workout_from_json(self, workout_json):
        if not self.client:
            if not self.connect(): return False

        try:
            plan = json.loads(workout_json)
        except:
            return False, "Invalid JSON"

        steps = []
        step_order = 1
        for step in plan['steps']:
            sType = 3
            if step['type'].lower() == "warmup": sType = 1
            elif step['type'].lower() == "cooldown": sType = 2
            elif step['type'].lower() == "recovery": sType = 4
            
            new_step = {
                "type": "ExecutableStepDTO",
                "stepId": step_order,
                "stepOrder": step_order,
                "childStepId": None,
                "description": step.get('description', ''),
                "stepType": {"stepTypeId": sType, "stepTypeKey": step['type']},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                "endConditionValue": step['duration_seconds'], 
                "targetType": {"targetTypeId": 2, "targetTypeKey": "power.zone"},
                "targetValueOne": step['target_power_min'],
                "targetValueTwo": step['target_power_max']
            }
            steps.append(new_step)
            step_order += 1

        workout_payload = {
            "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
            "workoutName": f"UAE AI: {plan['name']}",
            "steps": steps
        }

        try:
            self.client.create_workout(workout_payload)
            return True, f"UAE AI: {plan['name']}"
        except Exception as e:
            return False, str(e)

# --- KLASS: AI BRAIN ---
class SmartCoachBrain:
    def __init__(self):
        self.history = self.load_history()

    def load_history(self):
        if os.path.exists(DATA_FILE):
            df = pd.read_csv(DATA_FILE)
            # Se till att distans-kolumnen finns (om man har gammal fil)
            if 'distance_km' not in df.columns:
                df['distance_km'] = 0
            return df
        return pd.DataFrame(columns=["date", "tss", "activity_name", "distance_km"])

    def save_workout(self, activity_name, tss, km):
        new_entry = pd.DataFrame({
            "date": [str(datetime.date.today())],
            "tss": [tss],
            "activity_name": [activity_name],
            "distance_km": [km]
        })
        self.history = pd.concat([self.history, new_entry], ignore_index=True)
        self.history.to_csv(DATA_FILE, index=False)

    def calculate_metrics(self):
        if self.history.empty: return 0, 0, 0, 0
        ctl = self.history['tss'].ewm(span=42).mean().iloc[-1]
        atl = self.history['tss'].ewm(span=7).mean().iloc[-1]
        tsb = ctl - atl
        total_km = self.history['distance_km'].sum()
        return ctl, atl, tsb, total_km

# --- UI LOGIK ---
st.title("🇦🇪 Team UAE - Pro Cycling System")

# Initiera system
coach = SmartCoachBrain()
mechanic = ServiceCourse()

# Sidebar Setup
with st.sidebar:
    st.header("⚙️ Inställningar")
    api_key = st.text_input("Gemini API Key", type="password")
    garmin_user = st.text_input("Garmin Email")
    garmin_pass = st.text_input("Garmin Password", type="password")

# Hämta Metrics
ctl, atl, tsb, total_km = coach.calculate_metrics()

# --- FLIKAR FÖR OLIKA FUNKTIONER ---
tab1, tab2, tab3 = st.tabs(["📊 Coach", "🔧 Service Course", "📝 Logga Pass"])

# --- FLIK 1: COACHING ---
with tab1:
    col1, col2, col3 = st.columns(3)
    col1.metric("Fitness (CTL)", f"{ctl:.1f}")
    col2.metric("Form (TSB)", f"{tsb:.1f}", delta=tsb)
    col3.metric("Total Distans", f"{int(total_km)} km")

    st.divider()
    
    if st.button("🤖 Generera & Synka Pass (Garmin 1040)"):
        if not (api_key and garmin_user and garmin_pass):
            st.error("Saknar inloggningsuppgifter!")
        else:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')
            prompt = f"""
            Agera som en cykeltränare. Cyklistens TSB är {tsb:.1f}.
            Skapa ett JSON-pass.
            Format: {{"name": "...", "steps": [{{"type": "interval", "duration_seconds": 300, "target_power_min": 200, "target_power_max": 220}}]}}
            """
            with st.spinner("Skapar pass..."):
                try:
                    res = model.generate_content(prompt)
                    json_str = res.text.strip().replace("```json", "").replace("```", "")
                    uploader = GarminWorkoutCreator(garmin_user, garmin_pass)
                    success, msg = uploader.create_workout_from_json(json_str)
                    if success: st.success(f"Pass '{msg}' skickat till enhet!")
                    else: st.error(f"Fel: {msg}")
                except Exception as e:
                    st.error(f"AI fel: {e}")

# --- FLIK 2: SERVICE COURSE (NY FUNKTION) ---
with tab2:
    st.subheader("🔧 Mekaniker-status")
    st.caption(f"Baserat på total körsträcka: {int(total_km)} km")
    
    parts_status = mechanic.check_status(total_km)
    
    for part in parts_status:
        # Färgkodning
        color = "green"
        if part['usage'] > 0.8: color = "orange"
        if part['needs_action']: color = "red"
        
        c1, c2, c3 = st.columns([2, 4, 2])
        
        with c1:
            st.markdown(f"**{part['item']}**")
        
        with c2:
            st.progress(part['usage'], text=f"{part['km_driven']} / {part['km_limit']} km")
            
        with c3:
            if part['needs_action']:
                st.error("⚠️ ÅTGÄRDA NU")
                if st.button(f"Markera {part['item']} som fixad"):
                    mechanic.save_service(part['item'], total_km)
                    st.rerun()
            elif part['usage'] > 0.8:
                st.warning("Snart dags")
            else:
                st.success("OK")
    
    st.info("Logiken baseras på generella rekommendationer. Klicka på 'Markera som fixad' när du servat cykeln för att nollställa mätaren.")

# --- FLIK 3: LOGGA PASS ---
with tab3:
    st.header("Logga manuellt")
    with st.form("log_form"):
        name = st.text_input("Passnamn")
        tss_val = st.number_input("TSS", value=50)
        dist_val = st.number_input("Distans (km)", value=30.0)
        
        if st.form_submit_button("Spara till historik"):
            coach.save_workout(name, tss_val, dist_val)
            st.success("Pass sparat! Service-mätarna har uppdaterats.")
            st.rerun()
