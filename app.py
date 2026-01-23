import streamlit as st
import pandas as pd
import json
import sys
import os

# --- 1. SÄKER SETUP ---
st.set_page_config(page_title="UAE System Fix", page_icon="🛠️", layout="wide")
st.title("🛠️ UAE Team Emirates - Final Fix")

# --- 2. HÄMTA NYCKLAR ---
api_key = st.secrets.get("api_key")
garmin_user = st.secrets.get("garmin_user")
garmin_pass = st.secrets.get("garmin_pass")

with st.sidebar:
    st.header("Inställningar")
    if not api_key: api_key = st.text_input("Gemini API Key", type="password")
    if not garmin_user: garmin_user = st.text_input("Garmin Email")
    if not garmin_pass: garmin_pass = st.text_input("Garmin Password", type="password")

# --- 3. DEN KRITISKA GARMIN-KOPPLINGEN ---
def get_garmin_client(user, password):
    """Loggar in och konfigurerar Garth korrekt för molnet."""
    try:
        from garminconnect import Garmin
        import garth

        # --- HÄR ÄR LÖSNINGEN ---
        # Vi tvingar Garth att spara tokens i /tmp istället för hemkatalogen
        # Detta löser problemet med skrivrättigheter på Streamlit Cloud
        garth.configure(save_strategy="fs", home_dir="/tmp")
        # ------------------------

        client = Garmin(user, password)
        client.login()
        return True, client, "Inloggad & Klar"
    except Exception as e:
        return False, None, str(e)

# --- 4. HUVUDPROGRAM ---
st.write("### Status: Systemkontroll")

col1, col2 = st.columns(2)

# TESTA GOOGLE
with col1:
    if st.button("1. Testa Google"):
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            res = model.generate_content("Säg hej")
            st.success(f"Google svarar: {res.text}")
        except Exception as e:
            st.error(f"Google fel: {e}")

# KÖR SKARPT (Med felhantering)
with col2:
    if st.button("2. KÖR SKARPT (Generera & Ladda upp)"):
        status = st.empty()
        
        # A. Logga in Garmin
        status.info("Loggar in på Garmin (med /tmp fix)...")
        ok, client, msg = get_garmin_client(garmin_user, garmin_pass)
        
        if not ok:
            status.error(f"Inloggning misslyckades: {msg}")
        else:
            status.success(f"Inloggning OK! ({msg})")
            
            # B. Skapa Pass med AI
            try:
                status.info("AI skapar passet...")
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # Enkel prompt för att minimera felkällor
                prompt = 'Skapa ett cykelpass (JSON). Format: {"name":"UAE Test","steps":[{"type":"interval","duration_seconds":300,"target_power_min":200,"target_power_max":250}]}'
                res = model.generate_content(prompt)
                clean_json = res.text.replace("```json", "").replace("```", "").strip()
                plan = json.loads(clean_json)
                st.write(f"AI skapade: {plan['name']}")
                
                # C. Bygg Payload (Manuellt för säkerhet)
                steps = []
                # Vi hårdkodar ett steg för att testa uppladdningen isolerat
                steps.append({
                    "type": "ExecutableStepDTO",
                    "stepId": 1,
                    "stepOrder": 1,
                    "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"}, 
                    "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                    "endConditionValue": 300, 
                    "targetType": {"targetTypeId": 2, "targetTypeKey": "power.zone"},
                    "targetValueOne": 200, 
                    "targetValueTwo": 250
                })
                
                payload = {
                    "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
                    "workoutName": f"UAE AI {pd.Timestamp.now().strftime('%H:%M:%S')}",
                    "steps": steps
                }
                
                # D. Ladda Upp
                status.info("Laddar upp till Garmin...")
                try:
                    # Vi använder create_workout som ska fungera nu när garth är konfigurerat
                    if hasattr(client, 'create_workout'):
                        client.create_workout(payload)
                        st.balloons()
                        status.success(f"✅ SUCCÉ! Passet '{payload['workoutName']}' är uppladdat!")
                    else:
                        # Fallback om funktionen saknas
                        url = "https://connect.garmin.com/workout-service/workout"
                        if hasattr(client, 'garth'):
                            client.garth.client.post(url, json=payload)
                            st.balloons()
                            status.success("✅ SUCCÉ (via Garth)!")
                        else:
                            status.error("Kunde inte hitta en uppladdningsmetod.")
                            
                except Exception as e:
                    # Fånga exakt vad Garmin svarar
                    error_msg = str(e)
                    if hasattr(e, 'response'):
                        error_msg += f" | Server Svar: {e.response.text}"
                    status.error(f"Uppladdningsfel: {error_msg}")
                    
            except Exception as e:
                status.error(f"AI/Data fel: {e}")

# --- VISA LOGGAR ---
with st.expander("Visa filsystem (Debug)"):
    st.write("Kollar /tmp mappen...")
    try:
        st.write(os.listdir("/tmp"))
    except:
        st.write("Kunde inte läsa /tmp")
