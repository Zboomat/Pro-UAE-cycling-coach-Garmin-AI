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

# --- HÄMTA API-NYCKLAR SÄKERT ---
# Vi hämtar dessa först så de finns tillgängliga i hela programmet
api_key = st.sidebar.text_input("Gemini API Key", type="password")
garmin_user = st.sidebar.text_input("Garmin Email")
garmin_pass = st.sidebar.text_input("Garmin Password", type="password")

# --- FUNKTIONER ---
def test_google_connection(key):
    """En liten funktion för att testa vilken hjärna vi kan nå"""
    try:
        genai.configure(api_key=key)
        # Vi listar modeller för att se vad servern ser
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        return True, models
    except Exception as e:
        return False, str(e)

# --- KLASS: GARMIN WORKOUT CREATOR ---
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
            return False

    def create_workout_from_json(self, workout_json):
        if not self.connect(): return False, "Kunde inte logga in på Garmin."
        try:
            plan = json.loads(workout_json)
        except:
            return False, "Kunde inte läsa AI:ns format."
        
        steps = []
        step_order = 1
        for step in plan.get('steps', []):
            sType = 3 # Interval default
            t = step.get('type', 'interval').lower()
            if t == "warmup": sType = 1
            elif t == "cooldown": sType = 2
            elif t == "recovery": sType = 4
            
            steps.append({
                "type": "ExecutableStepDTO",
                "stepId": step_order,
                "stepOrder": step_order,
                "stepType": {"stepTypeId": sType, "stepTypeKey": step.get('type', 'interval')},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                "endConditionValue": step.get('duration_seconds', 300), 
                "targetType": {"targetTypeId": 2, "targetTypeKey": "power.zone"},
                "targetValueOne": step.get('target_power_min', 100),
                "targetValueTwo": step.get('target_power_max', 200)
            })
            step_order += 1

        payload = {
            "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
            "workoutName": f"UAE AI: {plan.get('name', 'Pass')}",
            "steps": steps
        }
        try:
            self.client.create_workout(payload)
            return True, f"Passet '{payload['workoutName']}' skapat!"
        except Exception as e:
            return False, str(e)

# --- KLASS: AI & LOGIK ---
class SmartCoachBrain:
    def __init__(self):
        self.history = pd.DataFrame(columns=["date", "tss", "activity_name", "distance_km"])
        if os.path.exists(DATA_FILE):
            try:
                self.history = pd.read_csv(DATA_FILE)
                if 'distance_km' not in self.history.columns: self.history['distance_km'] = 0
            except: pass # Börja om om filen är trasig

    def save_workout(self, name, tss, km):
        entry = pd.DataFrame({"date": [str(datetime.date.today())], "tss": [tss], "activity_name": [name], "distance_km": [km]})
        self.history = pd.concat([self.history, entry], ignore_index=True)
        self.history.to_csv(DATA_FILE, index=False)

    def get_metrics(self):
        if self.history.empty: return 0, 0, 0, 0
        ctl = self.history['tss'].ewm(span=42).mean().iloc[-1]
        atl = self.history['tss'].ewm(span=7).mean().iloc[-1]
        tsb = ctl - atl
        dist = self.history['distance_km'].sum()
        return ctl, atl, tsb, dist

# --- HUVUDPROGRAM ---
st.title("🇦🇪 Team UAE - Pro Cycling System")

coach = SmartCoachBrain()
ctl, atl, tsb, total_km = coach.get_metrics()

# Flikar
tab1, tab2, tab3, tab4 = st.tabs(["📊 Coach", "🔧 Service", "📝 Logga", "🕵️ Felsökning"])

with tab1:
    col1, col2 = st.columns(2)
    col1.metric("Form (TSB)", f"{tsb:.1f}", delta=tsb)
    col2.metric("Fitness (CTL)", f"{ctl:.1f}")
    
    if st.button("🤖 Generera & Synka till Garmin"):
        if not (api_key and garmin_user and garmin_pass):
            st.error("Fyll i nycklar i menyn till vänster!")
        else:
            status_text = st.empty()
            status_text.info("Kontaktar Google Gemini...")
            
            try:
                genai.configure(api_key=api_key)
                # Vi försöker med Flash först, annars faller vi tillbaka
                model_name = 'gemini-3-flash-preview'
                model = genai.GenerativeModel(model_name)
                
                prompt = f"""
                Skapa ett cykelpass (JSON) för en cyklist med TSB {tsb:.1f}.
                Format: {{"name": "...", "steps": [{{"type": "interval", "duration_seconds": 300, "target_power_min": 200, "target_power_max": 220}}]}}
                Svara ENDAST med JSON.
                """
                response = model.generate_content(prompt)
                json_data = response.text.replace("```json", "").replace("```", "").strip()
                
                status_text.info("Laddar upp till Garmin...")
                uploader = GarminWorkoutCreator(garmin_user, garmin_pass)
                ok, msg = uploader.create_workout_from_json(json_data)
                
                if ok: 
                    status_text.success(f"✅ {msg}")
                    st.balloons()
                else: 
                    status_text.error(f"Garmin fel: {msg}")
                    
            except Exception as e:
                status_text.error(f"AI Fel: {e}. Gå till fliken Felsökning!")

with tab2:
    st.write(f"Total distans: {int(total_km)} km. (Service-modulen är aktiv i bakgrunden)")

with tab3:
    with st.form("log"):
        name = st.text_input("Namn")
        tss = st.number_input("TSS", value=50)
        km = st.number_input("Km", value=30)
        if st.form_submit_button("Spara"):
            coach.save_workout(name, tss, km)
            st.success("Sparat!")
            st.rerun()

with tab4:
    st.subheader("Systemstatus")
    if st.button("Testa anslutning till Google"):
        if not api_key:
            st.warning("Ingen nyckel ifylld.")
        else:
            ok, data = test_google_connection(api_key)
            if ok:
                st.success("✅ Koppling lyckades!")
                st.write("Tillgängliga modeller:", data)
            else:
                st.error(f"❌ Koppling misslyckades: {data}")
