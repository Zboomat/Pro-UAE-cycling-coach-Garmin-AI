import streamlit as st
import pandas as pd
import json
import os
import re

# --- 1. GLOBAL KONFIGURATION ---
st.set_page_config(page_title="UAE Coach Pro", page_icon="🚴", layout="wide")

# Initiera bibliotek säkert
try:
    import google.generativeai as genai
    import garth
    from garminconnect import Garmin
    
    # SENIOR FIX: Tvinga Garth att använda /tmp direkt vid start.
    # Detta förhindrar "Permission Denied" eller "Home directory not writable"
    garth.configure(save_strategy="fs", home_dir="/tmp")
    
except ImportError as e:
    st.error(f"Kritiskt fel: Bibliotek saknas. Kontrollera requirements.txt. ({e})")
    st.stop()

# --- 2. HÄLPERFUNKTIONER (Logik separerad från UI) ---

def clean_json_response(text):
    """Rensar bort markdown och extra text från AI-svaret."""
    try:
        # Hitta första { och sista }
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text) # Försök direkt om regex missar
    except Exception:
        return None

def generate_workout_plan(api_key):
    """Pratar med Google Gemini."""
    try:
        genai.configure(api_key=api_key)
        # 1.5-flash är den mest stabila modellen för JSON-struktur just nu
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """
        Agera som en professionell cykelcoach för UAE Team Emirates.
        Skapa ett strukturerat intervallpass.
        VIKTIGT: Svara ENDAST med giltig JSON. Ingen annan text.
        Format:
        {
            "name": "Namn på passet",
            "steps": [
                {"type": "warmup", "duration_seconds": 600, "target_power_min": 100, "target_power_max": 150},
                {"type": "interval", "duration_seconds": 300, "target_power_min": 250, "target_power_max": 300},
                {"type": "recovery", "duration_seconds": 120, "target_power_min": 100, "target_power_max": 140},
                {"type": "cooldown", "duration_seconds": 600, "target_power_min": 100, "target_power_max": 130}
            ]
        }
        """
        response = model.generate_content(prompt)
        return clean_json_response(response.text)
    except Exception as e:
        st.error(f"Google AI Fel: {str(e)}")
        return None

def upload_to_garmin(user, password, plan_json):
    """Laddar upp passet till Garmin via Garth."""
    try:
        # Logga in
        client = Garmin(user, password)
        client.login()
        
        # Konvertera JSON till Garmins format
        steps = []
        step_order = 1
        for step in plan_json.get('steps', []):
            sType = 3 # Interval default
            t = step.get('type', 'interval').lower()
            if "warm" in t: sType = 1
            elif "cool" in t: sType = 2
            elif "recov" in t or "rest" in t: sType = 4
            
            steps.append({
                "type": "ExecutableStepDTO",
                "stepId": step_order,
                "stepOrder": step_order,
                "stepType": {"stepTypeId": sType, "stepTypeKey": step.get('type', 'interval')},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                "endConditionValue": int(step.get('duration_seconds', 300)), 
                "targetType": {"targetTypeId": 2, "targetTypeKey": "power.zone"},
                "targetValueOne": int(step.get('target_power_min', 100)),
                "targetValueTwo": int(step.get('target_power_max', 200))
            })
            step_order += 1

        payload = {
            "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
            "workoutName": f"UAE AI: {plan_json.get('name', 'Workout')}",
            "steps": steps
        }

        # --- UPLOAD STRATEGI ---
        # 1. Försök med den officiella metoden först
        if hasattr(client, 'create_workout'):
            try:
                client.create_workout(payload)
                return True, "Uppladdat via standardmetod!"
            except: pass # Fortsätt om det misslyckas
            
        # 2. Försök med Garth (Moderna API:et)
        # Eftersom vi konfigurerade garth till /tmp i början av filen ska detta fungera
        upload_url = "https://connect.garmin.com/workout-service/workout"
        if hasattr(client, 'garth'):
            res = client.garth.client.post(upload_url, json=payload)
            if res.status_code in [200, 201]:
                return True, "Uppladdat via Garth!"
            else:
                return False, f"Garth svarade med felkod: {res.status_code}"
        
        return False, "Ingen kompatibel uppladdningsmetod hittades."

    except Exception as e:
        return False, f"Garmin Error: {str(e)}"

# --- 3. HUVUDPROGRAM (UI) ---

st.title("🇦🇪 UAE Team Emirates - Service Course")
st.markdown("### AI Driven Training Planner")

# Hämta nycklar
api_key = st.secrets.get("api_key")
garmin_user = st.secrets.get("garmin_user")
garmin_pass = st.secrets.get("garmin_pass")

# Visa inloggningsfält om secrets saknas
if not (api_key and garmin_user and garmin_pass):
    st.warning("⚠️ Secrets saknas. Använd menyn till vänster för manuell inmatning.")
    with st.sidebar:
        api_key = st.text_input
