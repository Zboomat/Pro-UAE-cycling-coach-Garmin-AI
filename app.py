import streamlit as st
import pandas as pd
import json
import google.generativeai as genai

# --- 1. KONFIGURATION (Måste vara absolut först) ---
st.set_page_config(page_title="UAE Coach", page_icon="🚴")

# --- 2. SÄKER IMPORT AV GARMIN ---
# Detta block förhindrar att appen kraschar direkt om biblioteket saknas
try:
    from garminconnect import Garmin
    GARMIN_AVAILABLE = True
except ImportError as e:
    GARMIN_AVAILABLE = False
    GARMIN_ERROR = str(e)
except Exception as e:
    GARMIN_AVAILABLE = False
    GARMIN_ERROR = str(e)

# --- 3. HÄMTA NYCKLAR ---
api_key = st.secrets.get("api_key")
garmin_user = st.secrets.get("garmin_user")
garmin_pass = st.secrets.get("garmin_pass")

# Fallback för Sidebar
if not api_key: api_key = st.sidebar.text_input("Gemini API Key", type="password")
if not garmin_user: garmin_user = st.sidebar.text_input("Garmin Email")
if not garmin_pass: garmin_pass = st.sidebar.text_input("Garmin Password", type="password")

# --- 4. FUNKTIONER ---

def get_ai_workout(key):
    """Hämtar pass från AI (Gemini 1.5 Flash)."""
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """
        Du är cykelcoach. Skapa ett pass.
        Svara ENDAST med JSON:
        {
            "name": "Passnamn",
            "steps": [
                {"type": "warmup", "duration_seconds": 300, "target_power_min": 100, "target_power_max": 150},
                {"type": "interval", "duration_seconds": 180, "target_power_min": 250, "target_power_max": 280}
            ]
        }
        """
        response = model.generate_content(prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Fel: {e}")
        return None

def upload_to_garmin(user, password, plan):
    """Laddar upp till Garmin."""
    if not GARMIN_AVAILABLE:
        return False, "Garmin-biblioteket kunde inte laddas."
        
    try:
        client = Garmin(user, password)
        client.login()
        
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
            return True, "Uppladdat!"
        else:
            # Manuell metod
            url = "https://connect.garmin.com/workout-service/workout"
            if hasattr(client, 'session'):
                 res = client.session.post(url, json=payload)
            elif hasattr(client, 'req'):
                 res = client.req.post(url, json=payload)
            else:
                 return False, "Kunde inte hitta rätt metod för uppladdning."
                 
            if res.status_code in [200, 201]:
                return True, "Uppladdat manuellt!"
            return False, f"Felkod: {res.status_code}"

    except Exception as e:
        return False, f"Garmin-fel: {str(e)}"

# --- 5. HUVUDPROGRAM (UI) ---
st.title("🇦🇪 UAE Team Emirates - Safe Mode")

# Diagnostik-ruta
if not GARMIN_AVAILABLE:
    st.warning(f"⚠️ Garmin-modulen startade inte. Du kan skapa pass, men inte ladda upp automatiskt.\nFelmeddelande: {GARMIN_ERROR}")
else:
    st.success("✅ Garmin-modulen är aktiv.")

if st.button("🚀 Generera Pass"):
    if not api_key:
        st.error("Ingen API-nyckel hittades.")
    else:
        with st.spinner("AI jobbar..."):
            plan = get_ai_workout(api_key)
            
        if plan:
            st.success(f"Pass skapat: {plan.get('name')}")
            
            # Visa tabell
            df = pd.DataFrame(plan['steps'])
            st.table(df)
            
            # Försök ladda upp
            if GARMIN_AVAILABLE and garmin_user and garmin_pass:
                with st.spinner("Laddar upp..."):
                    ok, msg = upload_to_garmin(garmin_user, garmin_pass, plan)
                    if ok:
                        st.balloons()
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"Uppladdning misslyckades: {msg}")
            elif not GARMIN_AVAILABLE:
                st.info("Kör passet manuellt baserat på tabellen ovan.")
            else:
                st.info("Fyll i Garmin-uppgifter i Secrets för automatisk uppladdning.")
