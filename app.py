import streamlit as st
import pandas as pd
import json
import sys

# --- 1. SÄKER SETUP (Kraschar aldrig) ---
st.set_page_config(page_title="UAE System Check", page_icon="🏥", layout="wide")
st.title("🏥 UAE Team Emirates - System Diagnostik")

# --- 2. KONTROLLERA INSTALLATIONER ---
# Vi försöker importera biblioteken säkert
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
    # Försök se version
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

# Fallback-rutor
with st.sidebar:
    st.header("🔑 Inställningar")
    if not api_key: api_key = st.text_input("Gemini API Key", type="password")
    if not garmin_user: garmin_user = st.text_input("Garmin Email")
    if not garmin_pass: garmin_pass = st.text_input("Garmin Password", type="password")

# --- 4. TEST-FUNKTIONER ---

def check_google_connection(key):
    """Testar att prata med Google."""
    if not STATUS_DEPS["google"]: return False, "Bibliotek saknas"
    try:
        genai.configure(api_key=key)
        # Hämta lista på modeller (snabbaste testet)
        models = list(genai.list_models())
        count = len(models)
        # Hitta en flash-modell
        flash_model = next((m.name for m in models if 'flash' in m.name), "Ingen Flash hittad")
        return True, f"OK! Hittade {count} modeller. Använder: {flash_model}"
    except Exception as e:
        return False, str(e)

def check_garmin_connection(user, password):
    """Testar att logga in på Garmin."""
    if not STATUS_DEPS["garmin"]: return False, "Bibliotek saknas"
    try:
        client = Garmin(user, password)
        client.login()
        name = client.full_name
        return True, f"OK! Inloggad som: {name} (Ver: {garmin_version})"
    except Exception as e:
        return False, str(e)

# --- 5. DASHBOARD UI ---

col1, col2, col3 = st.columns(3)

# A. GOOGLE STATUS
with col1:
    st.subheader("🤖 Google AI")
    if not api_key:
        st.warning("Ingen nyckel ifylld")
    else:
        if st.button("Testa Google"):
            ok, msg = check_google_connection(api_key)
            if ok:
                st.success(msg)
            else:
                st.error(f"Fel: {msg}")

# B. GARMIN STATUS
with col2:
    st.subheader("⌚ Garmin")
    if not (garmin_user and garmin_pass):
        st.warning("Inlogg saknas")
    else:
        if st.button("Testa Garmin"):
            ok, msg = check_garmin_connection(garmin_user, garmin_pass)
            if ok:
                st.success(msg)
            else:
                st.error(f"Fel: {msg}")

# C. GENERERA PASS (Endast om testerna går bra)
with col3:
    st.subheader("🚴 Skapa Pass")
    if st.button("Kör Skarpt!"):
        if not api_key:
            st.error("Fixa Google-nyckel först.")
        else:
            with st.spinner("Skapar pass..."):
                # Enkel logik inbäddad här för att slippa krångel
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    res = model.generate_content('Skapa ett cykelpass (JSON). Format: {"name":"Test","steps":[{"type":"interval","duration_seconds":300,"target_power_min":200,"target_power_max":250}]}')
                    clean_json = res.text.replace("```json","").replace("```","").strip()
