import streamlit as st
import pandas as pd
import json
import tempfile
import os

# --- 1. SETUP ---
st.set_page_config(page_title="UAE Pro Coach", page_icon="🚴", layout="wide")
st.title("🇦🇪 UAE Team Emirates - Service Course")

# --- 2. HÄMTA NYCKLAR ---
api_key = st.secrets.get("api_key")
garmin_user = st.secrets.get("garmin_user")
garmin_pass = st.secrets.get("garmin_pass")

# Fallback-rutor om secrets saknas
if not (api_key and garmin_user and garmin_pass):
    with st.sidebar:
        st.warning("Fyll i uppgifter")
        api_key = st.text_input("Gemini API Key", type="password")
        garmin_user = st.text_input("Garmin Email")
        garmin_pass = st.text_input("Garmin Password", type="password")

# --- 3. SENIOR LOGIK: TEMPORÄR SANDLÅDA ---
def process_workout(ai_key, g_user, g_pass):
    """
    Hela processen (AI -> JSON -> Garmin) inuti en temporär katalog.
    Detta löser 'Permission Denied' eftersom vi skriver till en tillåten temp-mapp.
    """
    log = []
    
    # Skapa en tillfällig mapp som raderas automatiskt när vi är klara
    with tempfile.TemporaryDirectory() as temp_dir:
        log.append(f"🔧 Skapade temporär sandlåda: {temp_dir}")
        
        try:
            # A. KONFIGURERA IDAG: GARTH (Inuti sandlådan)
            import garth
            from garminconnect import Garmin
            import google.generativeai as genai
            
            # Tvinga garth att använda vår temp-mapp för tokens
            garth.configure(save_strategy="fs", home_dir=temp_dir)
            
            # B. GENERERA PASS (AI)
            log.append("🧠 Kontaktar AI...")
            genai.configure(api_key=ai_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = """
            Skapa ett cykelpass (JSON).
            Format: {"name":"UAE Intervals","steps":[{"type":"warmup","duration_seconds":600,"target_power_min":100,"target_power_max":150},{"type":"interval","duration_seconds":300,"target_power_min":250,"target_power_max":300}]}
            Svara ENDAST med JSON.
            """
            res = model.generate_content(prompt)
            json_text = res.text.replace("```json", "").replace("```", "").strip()
            plan = json.loads(json_text)
            log.append(f"✅ AI skapade: {plan.get('name')}")
            
            # C. LOGGA IN PÅ GARMIN
            log.append("⌚ Loggar in på Garmin...")
            client = Garmin(g_user, g_pass)
            client.login() # Nu sparas tokens lagligt i temp_dir
            log.append(f"✅ Inloggad som: {client.full_name}")
            
            # D. KONVERTERA TILL GARMIN-FORMAT
            steps = []
            step_order = 1
            for step in plan.get('steps', []):
                sType = 3
                t = step.get('type', 'interval').lower()
                if "warm" in t: sType = 1
                elif "cool" in t: sType = 2
                elif "rec" in t: sType = 4
                
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
                "workoutName": f"UAE AI {pd.Timestamp.now().strftime('%H:%M')}",
                "steps": steps
            }
            
            # E. LADDA UPP (Garth-metoden)
            log.append("🚀 Laddar upp...")
            if hasattr(client, 'create_workout'):
                 client.create_workout(payload)
                 return True, log, "Uppladdat via standardmetod!"
            
            # Fallback: Direkt POST via garth client
            url = "https://connect.garmin.com/workout-service/workout"
            client.garth.client.post(url, json=payload)
            return True, log, "Uppladdat via Garth!"

        except Exception as e:
            log.append(f"❌ FEL: {str(e)}")
            return False, log, str(e)

# --- 4. UI ---
if st.button("🚀 KÖR SKARPT", type="primary"):
    if not (api_key and garmin_user and garmin_pass):
        st.error("Fyll i nycklar först.")
    else:
        status_box = st.status("Jobbar...", expanded=True)
        success, logs, msg = process_workout(api_key, garmin_user, garmin_pass)
        
        # Skriv ut loggarna snyggt
        for line in logs:
            status_box.write(line)
            
        if success:
            status_box.update(label="Klar!", state="complete", expanded=False)
            st.balloons()
            st.success(f"✅ {msg}")
        else:
            status_box.update(label="Misslyckades", state="error")
            st.error(msg)
