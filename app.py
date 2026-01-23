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
    import garth
    STATUS_DEPS["garmin"] = True
    try:
        import garminconnect
        garmin_version = garminconnect.__version__
    except: 
        garmin_version = "Okänd"
except ImportError as e:
    ERRORS.append(f"Garmin/Garth saknas: {e}")
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

# --- 4. DEN NYA UNIVERSAL-ADAPTERN ---
def universal_upload(client, payload):
    """Provar 4 olika sätt att ladda upp passet beroende på version."""
    url = "https://connect.garmin.com/workout-service/workout"
    log = []

    # METOD 1: Officiell funktion (Nyaste versionen)
    if hasattr(client, 'create_workout'):
        try:
            client.create_workout(payload)
            return True, "Lyckades med Metod 1 (create_workout)"
        except Exception as e:
            log.append(f"Metod 1 fel: {e}")
    
    # METOD 2: Garth (Moderna sättet)
    if hasattr(client, 'garth'):
        try:
            res = client.garth.client.post(url, json=payload)
            if res.status_code in [200, 201]: return True, "Lyckades med Metod 2 (Garth)"
            else: log.append(f"Metod 2 felkod: {res.status_code}")
        except Exception as e:
            log.append(f"Metod 2 krasch: {e}")

    # METOD 3: Session (Gamla sättet)
    if hasattr(client, 'session'):
        try:
            res = client.session.post(url, json=payload)
            if res.status_code in [200, 201]: return True, "Lyckades med Metod 3 (Session)"
            else: log.append(f"Metod 3 felkod: {res.status_code}")
        except Exception as e:
            log.append(f"Metod 3 krasch: {e}")

    # METOD 4: Req (Urgamla sättet)
    if hasattr(client, 'req'):
        try:
            res = client.req.post(url, json=payload)
            if res.status_code in [200, 201]: return True, "Lyckades med Metod 4 (Req)"
        except Exception as e:
            log.append(f"Metod 4 krasch: {e}")

    return False, "ALLA METODER MISSLYCKADES. Logg: " + "; ".join(log)

# --- 5. TEST-FUNKTIONER ---
def check_google_connection(key):
    if not STATUS_DEPS["google"]: return False, "Bibliotek saknas"
    try:
        genai.configure(api_key=key)
        models = list(genai.list_models())
        flash_model = next((m.name for m in models if 'flash' in m.name), "Ingen Flash hittad")
        return True, f"OK! Vald modell: {flash_model}"
    except Exception as e:
        return False, str(e)

def check_garmin_connection(user, password):
    if not STATUS_DEPS["garmin"]: return False, "Bibliotek saknas"
    try:
        # Konfigurera garth för att undvika token-fel
        try:
            garth.configure(save_strategy="fs", home_dir="/tmp")
        except: pass
        
        client = Garmin(user, password)
        client.login()
        return True, f"OK! Inloggad (Ver: {garmin_version})", client
    except Exception as e:
        return False, str(e), None

# --- 6. DASHBOARD UI ---
col1, col2, col3 = st.columns(3)

# A. GOOGLE STATUS
with col1:
    st.subheader("🤖 1. Google AI")
    if st.button("Testa Google"):
        ok, msg = check_google_connection(api_key)
        if ok: st.success(msg)
        else: st.error(msg)

# B. GARMIN STATUS
with col2:
    st.subheader("⌚ 2. Garmin")
    if st.button("Testa Garmin"):
        ok, msg, _ = check_garmin_connection(garmin_user, garmin_pass)
        if ok: st.success(msg)
        else: st.error(msg)

# C. GENERERA PASS
with col3:
    st.subheader("🚀 3. Skapa & Ladda Upp")
    if st.button("Kör Skarpt!"):
        status = st.empty()
        
        # 1. Logga in Garmin först
        status.info("Loggar in på Garmin...")
        garmin_ok, garmin_msg, client = check_garmin_connection(garmin_user, garmin_pass)
        
        if not garmin_ok:
            status.error(f"Garmin inloggning misslyckades: {garmin_msg}")
        else:
            try:
                # 2. Skapa Pass med AI
                status.info("AI designar passet...")
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                res = model.generate_content('Skapa ett cykelpass (JSON). Format: {"name":"Test","steps":[{"type":"interval","duration_seconds":300,"target_power_min":200,"target_power_max":250}]}')
                clean_json = res.text.replace("```json","").replace("```","").strip()
                plan = json.loads(clean_json)
                
                st.info(f"Pass designat: {plan.get('name')}")
                
                # 3. Bygg payload
                steps = [{"type":"ExecutableStepDTO", "stepId":1, "stepOrder":1, "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"}, "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"}, "endConditionValue": 300, "targetType": {"targetTypeId": 2, "targetTypeKey": "power.zone"}, "targetValueOne": 200, "targetValueTwo": 250}]
                payload = {"sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"}, "workoutName": f"UAE AI {pd.Timestamp.now().strftime('%H:%M')}", "steps": steps}
                
                # 4. ANVÄND UNIVERSAL-ADAPTERN
                status.info("Laddar upp med Universal-adaptern...")
                success, upload_msg = universal_upload(client, payload)
                
                if success:
                    st.balloons()
                    status.success(f"✅ {upload_msg}")
                    st.success("Passet finns nu i din Garmin Connect!")
                else:
                    status.error(f"Uppladdning misslyckades: {upload_msg}")
                    
            except Exception as e:
                status.error(f"Ett oväntat fel uppstod: {e}")

# --- TEKNISK INFO ---
with st.expander("Visa teknisk info"):
    st.write(f"Python: {sys.version}")
    st.write(f"Garmin Ver: {garmin_version}")
    if ERRORS: st.error(str(ERRORS))
