import streamlit as st
import requests
import re

# — FONCTIONS DE DÉCODAGE (Basées sur le Guide Aviation Météo-France) —
def recuperer_metar(oaci):
    # Récupération via NOAA
    url = f "https://tgftp.nws.noaa.gov/data/observations/metar/stations/{oaci.upper()}.TXT"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            lines = r.text.strip().split(‘\n’)
            # On cherche la ligne qui commence par le code OACI
            for line in lines:
                if line.startswith(oaci.upper()):
                    return line.strip()
            return lines[-1].strip()
        return None
    except:
        return None

def decoder_metar_pour_affichage(metar):
    if not metar:
        return « Données indisponibles. »
        
    explications = []
    
    # 1. Vent (Direction, Vitesse, Rafales) - Guide p.16
    vent = re.search(r’\b(VRB|\d{3})(\d{2})(G\d{2})?KT\b’, metar)
    if vent:
        d, s, g = vent.groups()
        dir_txt = « Variable » if d == « VRB » else f »{d}° »
        rafale = f » (Rafales {g[1:]} kt) » if g else «  »
        explications.append(f »🌬️ **Vent :** {dir_txt} à {int(s)} kt{rafale} »)
        
    # 2. Visibilité & CAVOK - Guide p.16 et 19
    if ‘CAVOK’ in metar:
        explications.append(« 👀 **Visibilité :** CAVOK (Visibilité > 10km, Pas de nuages bas, Pas de phénomènes) »)
    else:
        visi = re.search(r’\b(\d{4})\b’, metar)
        if visi and not re.match(r’^\d{4}Z’, visi.group(0)): # Éviter de prendre l’heure pour la visi
             dist = « 10 km ou plus » if visi.group(1) == « 9999 » else f »{int(visi.group(1))} mètres »
             explications.append(f »👀 **Visibilité :** {dist} »)
             
    # 3. Phénomènes (Pluie, Brume, Orage...) - Guide p.18
    # Dictionnaire simplifié pour l’exemple
    codes = {‘RA’: ‘Pluie’, ‘DZ’: ‘Bruine’, ‘SN’: ‘Neige’, ‘BR’: ‘Brume’, ‘FG’: ‘Brouillard’, ‘TS’: ‘Orage’, ‘SH’: ‘Averses’}
    temps_trouve = []
    for code, desc in codes.items():
        if code in metar:
            temps_trouve.append(desc)
    if temps_trouve:
        explications.append(f »🌧️ **Temps :** {‘, ‘.join(temps_trouve)} »)

    # 4. Nuages (BKN, OVC...) - Guide p.19
    nuages = re.findall(r’(FEW|SCT|BKN|OVC)(\d{3})’, metar)
    if nuages:
        desc_nuages = []
        for type_n, haut in nuages:
            altitude = int(haut) * 100
            desc_nuages.append(f »{type_n} à {altitude} ft »)
        explications.append(f »☁️ **Nuages :** {‘, ‘.join(desc_nuages)} »)

    # 5. Température / QNH - Guide p.19
    temp = re.search(r’\b(M?\d{2})/(M?\d{2}|//)\b’, metar)
    if temp:
        t = temp.group(1).replace(‘M’, ‘-‘)
        explications.append(f »🌡️ **Température :** {t}°C »)
        
    qnh = re.search(r’Q(\d{4})’, metar)
    if qnh:
        explications.append(f »⏱️ **Pression :** {qnh.group(1)} hPa »)
        
    return « \n\n ».join(explications)

# — INTERFACE STREAMLIT —
st.set_page_config(page_title=« Décodeur METAR », page_icon=« ✈️ »)

st.title(« ✈️ Météo Aéro »)
st.markdown(« Décodeur rapide pour mobile. »)

# Entrée utilisateur (LFQQ par défaut)
oaci = st.text_input(« Code OACI », value=« LFQQ », max_chars=4).upper()

if st.button(« Actualiser », type=« primary »):
    with st.spinner(‘Connexion NOAA...’):
        raw = recuperer_metar(oaci)
        
        if raw:
            st.success(f »Données reçues pour {oaci} »)
            # Affichage du message brut dans une boîte de code
            st.code(raw, language=« text »)
            
            # Affichage du décodage
            st.markdown(« ### Analyse »)
            resultat = decoder_metar_pour_affichage(raw)
            st.info(resultat)
        else:
            st.error(f »Impossible de trouver le METAR pour {oaci}. Vérifiez le code. »)
