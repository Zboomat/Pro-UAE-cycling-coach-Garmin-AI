import streamlit as st
import pandas as pd
import json
import sys

# --- 1. SÄKER SETUP ---
st.set_page_config(page_title="UAE System Check", page_icon="🏥", layout="wide")
st.title("🏥 UAE Team Emirates - System Diagnostik")

# --- 2. KONTROLLERA INSTALLATIONER ---
STATUS_DEPS = {"google": False, "garmin": False}
ERRORS = []

try:
    import google.generativeai as genai
    STATUS_DEPS["google"] = True
except ImportError as e:
    ERRORS.append(f"Google AI saknas: {e}")

try:
    from garminconnect import Garmin
    STATUS_DEPS["garmin"] = True
    try:
        import garminconnect
        garmin_version = garminconnect.__version__
    except: 
        garmin_version = "Okänd"
except ImportError as e:
    ERRORS.append(f"Garmin Connect saknas: {e}")
    garmin_version = "N/A"

# --- 3. HÄMTA NYCKLAR ---
api_key = st.secrets.get("api_key")
garmin_user = st.secrets.get("garmin_user")
garmin_pass = st.secrets.get("garmin_pass")

with st.sidebar:
    st.header("🔑 Inställningar")
    if not api_key: api_key = st.text_input("Gemini API Key", type="password")
    if not garmin_user: garmin_user = st.text_input("Garmin Email")
    if not garmin_pass: garmin_pass = st.text_input("Garmin Password", type="password")

# --- 4. TEST-FUNKTIONER ---
def check_google_connection(key):
    if not STATUS_DEPS["google"]: return False, "Bibliotek saknas"
    try:
        genai.configure(api_key=key)
        models = list(genai.list_models())
        count = len(models)
        flash_model = next((m.name for m in models if 'flash' in m.name), "Ingen Flash hittad")
        return True, f"OK! Hittade {count} modeller. Vald: {flash_model}"
    except Exception as e:
        return False, str(e)

def check_garmin_connection(user, password):
    if not STATUS_DEPS["garmin"]: return False, "Bibliotek saknas"
    try:
        client = Garmin(user, password)
        client.login()
        return True, f"OK! Inloggad (Ver: {garmin_version})"
    except Exception as e:
        return False, str(e)

# --- 5. DASHBOARD UI ---
col1, col2, col3 = st.columns(3)

# A. GOOGLE STATUS
with col1:
    st.subheader("🤖 Google AI")
    if st.button("Testa Google"):
        if not api_key:
            st.warning("Ingen nyckel ifylld")
        else:
            ok, msg = check_google_connection(api_key)
            if ok: st.success(msg)
            else: st.error(f"Fel: {msg}")

# B. GARMIN STATUS
with col2:
    st.subheader("⌚ Garmin")
    if st.button("Testa Garmin"):
        if not (garmin_user and garmin_pass):
            st.warning("Inlogg saknas")
        else:
            ok, msg = check_garmin_connection(garmin_user, garmin_pass)
            if ok: st.success(msg)
            else: st.error(f"Fel: {msg}")

# C. GENERERA PASS
with col3:
    st.subheader("🚴 Skapa Pass")
    if st.button("Kör Skarpt!"):
        if not api_key:
            st.error("Kräver Google-nyckel")
        else:
            status = st.empty()
            status.info("Arbetar...")
            
            # --- HÄR BÖRJAR TRY-BLOCKET SOM SAKNADES SIST ---
            try:
                # 1. AI Generering
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                res = model.generate_content('Skapa ett cykelpass (JSON). Format: {"name":"Test","steps":[{"type":"interval","duration_seconds":300,"target_power_min":200,"target_power_max":250}]}')
                clean_json = res.text.replace("```json","").replace("```","").strip()
                plan = json.loads(clean_json)
                
                st.success(f"Pass skapat: {plan.get('name')}")
                
                # 2. Uppladdning
                if garmin_user and garmin_pass:
                    try:
                        client = Garmin(garmin_user, garmin_pass)
                        client.login()
                        
                        steps = [{"type":"ExecutableStepDTO", "stepId":1, "stepOrder":1, "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"}, "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"}, "endConditionValue": 300, "targetType": {"targetTypeId": 2, "targetTypeKey": "power.zone"}, "targetValueOne": 200, "targetValueTwo": 250}]
                        payload = {"sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"}, "workoutName": f"UAE TEST {pd.Timestamp.now().strftime('%H:%M')}", "steps": steps}
                        
                        if hasattr(client, 'create_workout'):
                            client.create_workout(payload)
                            st.balloons()
                            status.success("✅ UPPPLADDAT OCH KLART!")
                        else:
                            status.warning("Funktionen 'create_workout' saknas.")
                            
                    except Exception as e:
                        status.error(f"Garmin Error: {e}")
                else:
                    st.json(plan)
                    
            except Exception as e:
                status.error(f"Krasch: {e}")

# --- SYSTEM INFO ---
with st.expander("Visa teknisk info"):
    st.write(f"Python version: {sys.version}")
    st.write(f"Garmin Library: {STATUS_DEPS['garmin']}")
    st.write(f"Google Library: {STATUS_DEPS['google']}")
    if ERRORS:
        st.error("Fel vid start:")
        st.code("\n".join(ERRORS))
