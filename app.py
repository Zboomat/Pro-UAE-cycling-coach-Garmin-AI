import streamlit as st
import pandas as pd
import json
import sys
import os

# --- 1. SETUP & IMPORTER ---
st.set_page_config(page_title="UAE System", page_icon="🛠️", layout="wide")
st.title("🛠️ UAE Team Emirates - Dashboard")

# Importera bibliotek säkert
try:
    import google.generativeai as genai
    GOOGLE_OK = True
except ImportError:
    GOOGLE_OK = False
    st.error("Google-biblioteket saknas. (Kolla requirements.txt)")

try:
    from garminconnect import Garmin
    import garth
    # --- FIXEN FÖR GARMIN PÅ MOLNET ---
    # Detta måste göras INNAN vi försöker logga in
    garth.configure(save_strategy="fs", home_dir="/tmp")
    GARMIN_OK = True
except ImportError:
    GARMIN_OK = False
    st.error("Garmin-biblioteket saknas. (Kolla requirements.txt)")

# --- 2. HÄMTA NYCKLAR ---
api_key = st.secrets.get("api_key")
garmin_user = st.secrets.get("garmin_user")
garmin_pass = st.secrets.get("garmin_pass")

# Fallback om secrets saknas
with st.sidebar:
    st.header("Inställningar")
    if not api_key: api_key = st.text_input("Gemini API Key", type="password")
    if not garmin_user: garmin_user = st.text_input("Garmin Email")
    if not garmin_pass: garmin_pass = st.text_input("Garmin Password", type="password")

# --- 3. KONFIGURERA GOOGLE DIREKT (Detta saknades sist) ---
if api_key and GOOGLE_OK:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.error(f"Kunde inte konfigurera Google: {e}")

# --- 4. FUNKTIONER ---

def test_google():
    """Enkelt test för att se om Google svarar."""
    try:
        # Vi använder en standardmodell
        model = genai.GenerativeModel('gemini-1.5-flash')
        res = model.generate_content("Svara bara ordet: 'Kontakt'")
        return True, res.text
    except Exception as e:
        return False, str(e)

def upload_workout(user, password, json_plan):
    """Laddar upp passet med flera metoder."""
    try:
        # Logga in
        client = Garmin(user, password)
        client.login()
        
        # Förbered passet
        plan = json.loads(json_plan)
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
            "workoutName": f"UAE AI {pd.Timestamp.now().strftime('%H:%M')}",
            "steps": steps
        }

        # Försök ladda upp (Universalmetoden)
        
        # Metod 1: create_workout (Om den finns)
        if hasattr(client, 'create_workout'):
            try:
                client.create_workout(payload)
                return True, "Uppladdat (Metod 1)"
            except: pass

        # Metod 2: Garth Post (Tack vare /tmp fixen bör denna fungera)
        if hasattr(client, 'garth'):
            try:
                url = "https://connect.garmin.com/workout-service/workout"
                client.garth.client.post(url, json=payload)
                return True, "Uppladdat (Metod 2 - Garth)"
            except Exception as e:
                return False, f"Garth misslyckades: {e}"
        
        return False, "Ingen uppladdningsmetod fungerade."

    except Exception as e:
        return False, f"Totalt fel: {e}"

#
