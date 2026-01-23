import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from garminconnect import Garmin

# --- KONFIGURATION ---
st.set_page_config(page_title="UAE Coach", page_icon="🚴")

# --- HÄMTA NYCKLAR ---
# Vi försöker hämta från Secrets först, annars Sidebar
api_key = st.secrets.get("api_key")
garmin_user = st.secrets.get("garmin_user")
garmin_pass = st.secrets.get("garmin_pass")

if not api_key: api_key = st.sidebar.text_input("Gemini API Key", type="password")
if not garmin_user: garmin_user = st.sidebar.text_input("Garmin Email")
if not garmin_pass: garmin_pass = st.sidebar.text_input("Garmin Password", type="password")

# --- FUNKTIONER ---

def get_ai_workout(key):
    """Hämtar pass från Google Gemini (1.5 Flash)."""
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """
        Skapa ett professionellt cykelpass.
        Svara ENDAST med JSON i följande format (inget annat prat):
        {
            "name": "Passets Namn",
            "steps": [
                {"type": "warmup", "duration_seconds": 600, "target_power_min": 100, "target_power_max": 150},
                {"type": "interval", "duration_seconds": 300, "target_power_min": 250, "target_power_max": 280},
                {"type": "recovery", "duration_seconds": 300, "target_power_min": 120, "target_power_max": 140},
                {"type": "cooldown", "duration_seconds": 600, "target_power_min": 100, "target_power_max": 130}
            ]
        }
        """
        response = model.generate_content(prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Fel: {e}")
        return None

def try_upload_to_garmin(user, password, plan):
    """Försöker ladda upp, men kraschar inte om det misslyckas."""
    try:
        client = Garmin(user, password)
        client.login()
        
        steps = []
        step_order = 1
        for step in plan.get('steps', []):
            sType = 3 # Interval
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
            return True, "Uppladdat och klart!"
        else:
            return False, "Funktionen create_workout saknas på servern."

    except Exception as e:
        return False, f"Garmin-fel: {str(e)}"

# --- HUVUDPROGRAM ---
st.title("🇦🇪 UAE Team Emirates - Coach")
st.write("Skapar personliga pass med Google Gemini AI.")

if st.button("🚀 Generera Pass"):
    if not api_key:
        st.error("Saknar API-nyckel!")
    else:
        with st.spinner("AI designar passet..."):
            workout_plan = get_ai_workout(api_key)
            
        if workout_plan:
            st.success(f"Pass skapat: {workout_plan.get('name')}")
            
            # Visa passet visuellt (Plan B)
            st.subheader("📋 Ditt Pass")
            df = pd.DataFrame(workout_plan['steps'])
            # Gör tabellen snyggare
            if not df.empty:
                df['Tid (min)'] = df['duration_seconds'] / 60
                df = df.rename(columns={'type': 'Typ', 'target_power_min': 'Min Watt', 'target_power_max': 'Max Watt'})
                st.table(df[['Typ', 'Tid (min)', 'Min Watt', 'Max Watt']])
            
            # Försök ladda upp till Garmin (Plan A)
            if garmin_user and garmin_pass:
                with st.spinner("Försöker synka till Garmin..."):
                    success, msg = try_upload_to_garmin(garmin_user, garmin_pass, workout_plan)
                    
                    if success:
                        st.balloons()
                        st.success(f"✅ {msg} - Synka din cykeldator nu!")
                    else:
                        st.warning(f"⚠️ Kunde inte ladda upp till molnet just nu ({msg}).")
                        st.info("💡 Men ingen fara! Du kan köra passet baserat på tabellen ovan.")
            else:
                st.info("Fyll i Garmin-uppgifter i Secrets för automatisk uppladdning.")
