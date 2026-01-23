import streamlit as st
import pandas as pd
import datetime
import os
import json
import google.generativeai as genai
from garminconnect import Garmin

# --- KONFIGURATION ---
DATA_FILE = "training_history.csv"

st.set_page_config(page_title="UAE Coach", page_icon="🚴", layout="wide")

# --- HÄMTA NYCKLAR ---
api_key = st.secrets.get("api_key", None)
garmin_user = st.secrets.get("garmin_user", None)
garmin_pass = st.secrets.get("garmin_pass", None)

if not api_key: api_key = st.sidebar.text_input("Gemini API Key", type="password")
if not garmin_user: garmin_user = st.sidebar.text_input("Garmin Email")
if not garmin_pass: garmin_pass = st.sidebar.text_input("Garmin Password", type="password")

# --- NY FUNKTION: HITTA MODELL AUTOMATISKT ---
def get_working_model(key):
    """Frågar Google vilka modeller som finns och väljer den bästa."""
    try:
        genai.configure(api_key=key)
        # Lista alla modeller
        all_models = genai.list_models()
        # Spara bara de som kan generera text
        valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        
        if not valid_models:
            return None, "Inga modeller tillgängliga för detta konto."
            
        # Prioritera Flash-modeller om de finns
        best_model = next((m for m in valid_models if 'flash' in m and 'lite' not in m), valid_models[0])
        return best_model, None
        
    except Exception as e:
        return None, f"Kunde inte kontakta Google. Är nyckeln rätt? Fel: {str(e)}"

# --- GARMIN UPLOADER (MANUAL MODE) ---
class GarminWorkoutCreator:
    def __init__(self, email, password):
        self.client = None
        self.email = email
        self.password = password

    def create_workout(self, json_data):
        try:
            self.client = Garmin(self.email, self.password)
            self.client.login()
        except:
            return False, "Login misslyckades."

        try:
            plan = json.loads(json_data)
        except:
            return False, "Felaktig JSON från AI."

        steps = []
        step_order = 1
        for step in plan.get('steps', []):
            sType = 3
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
            # Manuell POST för att undvika versionsfel
            url = "https://connect.garmin.com/workout-service/workout"
            res = self.client.req.post(url, json=payload)
            if res.status_code in [200, 201]:
                return True, f"Passet '{payload['workoutName']}' skapat!"
            return False, f"Garmin error: {res.status_code}"
        except Exception as e:
            return False, str(e)

# --- APP LOGIK ---
st.title("🇦🇪 Team UAE - Autopilot")

if st.button("🚀 Generera & Synka"):
    if not (api_key and garmin_user and garmin_pass):
        st.error("Saknar nycklar!")
    else:
        status = st.empty()
        
        # 1. Hitta modell
        status.info("Letar efter fungerande AI-modell...")
        model_name, error = get_working_model(api_key)
        
        if not model_name:
            st.error(f"Kritiskt fel: {error}")
            st.stop()
            
        status.success(f"Hittade modell: {model_name}")
        
        # 2. Generera
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("""
                Skapa ett cykelpass (JSON). 
                Format: {"name": "Testpass", "steps": [{"type": "interval", "duration_seconds": 300, "target_power_min": 200, "target_power_max": 220}]}
                Svara ENDAST med JSON.
            """)
            json_str = response.text.replace("```json", "").replace("```", "").strip()
            
            # 3. Ladda upp
            status.info("Laddar upp till Garmin...")
            uploader = GarminWorkoutCreator(garmin_user, garmin_pass)
            ok, msg = uploader.create_workout(json_str)
            
            if ok:
                st.balloons()
                status.success(f"✅ {msg}")
            else:
                status.error(msg)
                
        except Exception as e:
            st.error(f"Ett fel uppstod: {e}")
