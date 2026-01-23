import streamlit as st
import pandas as pd
import datetime
import os
import json
import google.generativeai as genai
from garminconnect import Garmin
import garth

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

# --- AI MODELL ---
def get_ai_workout(key):
    try:
        genai.configure(api_key=key)
        # Vi använder en standardmodell som vi vet fungerar
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """
        Agera som en proffstränare. Skapa ett strukturerat cykelpass.
        VIKTIGT: Svara ENDAST med giltig JSON. Inget annat.
        Format:
        {
            "name": "Passets Namn",
            "steps": [
                {"type": "warmup", "duration_seconds": 600, "target_power_min": 100, "target_power_max": 150},
                {"type": "interval", "duration_seconds": 300, "target_power_min": 250, "target_power_max": 280},
                {"type": "recovery", "duration_seconds": 300, "target_power_min": 100, "target_power_max": 140},
                {"type": "cooldown", "duration_seconds": 600, "target_power_min": 100, "target_power_max": 130}
            ]
        }
        """
        response = model.generate_content(prompt)
        # Städa bort eventuell markdown
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        return None

# --- GARMIN UPLOAD (MED KROCKKUDDE) ---
def upload_to_garmin(email, password, plan):
    try:
        # Konfigurera garth för att spara tokens temporärt (löser KeyError)
        garth.configure(save_strategy="fs", home_dir="/tmp")
        
        client = Garmin(email, password)
        client.login() # Detta använder nu garth automatiskt
        
        # Bygg Garmin-struktur
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
                "endConditionValue": step.get('duration_seconds'), 
                "targetType": {"targetTypeId": 2, "targetTypeKey": "power.zone"},
                "targetValueOne": step.get('target_power_min'),
                "targetValueTwo": step.get('target_power_max')
            })
            step_order += 1

        payload = {
            "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
            "workoutName": f"UAE AI: {plan.get('name')}",
            "steps": steps
        }

        # Försök ladda upp
        if hasattr(client, 'create_workout'):
            client.create_workout(payload)
            return True, "Uppladdat via standardmetod!"
            
        return False, "Kunde inte hitta uppladdningsfunktionen."
        
    except Exception as e:
        return False, f"Garmin-fel: {str(e)}"

# --- APP UI ---
st.title("🇦🇪 UAE Team Emirates - Coach")

if st.button("🚀 Skapa Pass"):
    if not (api_key and garmin_user and garmin_pass):
        st.error("Saknar inloggningsuppgifter.")
    else:
        status = st.empty()
        status.info("AI designar passet...")
        
        # 1. Hämta pass från AI
        workout_plan = get_ai_workout(api_key)
        
        if workout_plan:
            st.subheader(f"📅 {workout_plan['name']}")
            
            # 2. Försök ladda upp
            status.info("Försöker ladda upp till Garmin...")
            success, msg = upload_to_garmin(garmin_user, garmin_pass, workout_plan)
            
            if success:
                st.balloons()
                status.success(f"✅ KLART! {msg}")
                st.info("Passet finns nu i din Edge-enhet (efter synk).")
            else:
                # PLAN B: Visa passet om uppladdning misslyckas
                status.warning(f"Kunde inte ladda upp automatiskt ({msg}).")
                st.markdown("### ⚠️ Manuell Inmatning")
                st.write("Eftersom Garmins servrar blockerade oss, här är passet. Lägg in det manuellt på din Edge:")
                
                df_steps = pd.DataFrame(workout_plan['steps'])
                df_steps['Min Watt'] = df_steps['target_power_min']
                df_steps['Max Watt'] = df_steps['target_power_max']
                df_steps['Tid (sek)'] = df_steps['duration_seconds']
                st.table(df_steps[['type', 'Tid (sek)', 'Min Watt', 'Max Watt']])
                
        else:
            status.error("Kunde inte skapa pass med AI.")
