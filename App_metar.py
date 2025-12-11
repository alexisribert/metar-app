import streamlit as st
import requests
import re

# --- FONCTIONS UTILITAIRES ---

def recuperer_metar(oaci):
    # Récupération via NOAA
    url = f"https://tgftp.nws.noaa.gov/data/observations/metar/stations/{oaci.upper()}.TXT"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            lines = r.text.strip().split('\n')
            for line in lines:
                if line.startswith(oaci.upper()):
                    return line.strip()
            return lines[-1].strip()
        return None
    except:
        return None

def decoder_phenomenes(token):
    # [span_0](start_span)Basé sur le Guide Aviation Page 18[span_0](end_span)
    # 1. Intensité
    intensite = ""
    if token.startswith('-'): 
        intensite = "Faible "
        token = token[1:]
    elif token.startswith('+'): 
        intensite = "Forte "
        token = token[1:]
    elif token.startswith('VC'):
        intensite = "Au voisinage : "
        token = token[2:]

    # 2. Descripteurs
    descripteurs = {
        'MI': 'Mince', 'BC': 'Bancs', 'PR': 'Partiel', 'DR': 'Chasse-basse',
        'BL': 'Chasse-élevée', 'SH': 'Averses', 'TS': 'Orageux', 'FZ': 'Se congelant'
    }
    desc_txt = ""
    if len(token) >= 2 and token[:2] in descripteurs:
        desc_txt = descripteurs[token[:2]] + " de "
        token = token[2:]

    # 3. Phénomènes
    phenomenes = {
        'DZ': 'Bruine', 'RA': 'Pluie', 'SN': 'Neige', 'SG': 'Neige en grains',
        'PL': 'Granules de glace', 'GR': 'Grêle', 'GS': 'Grésil',
        'BR': 'Brume', 'FG': 'Brouillard', 'FU': 'Fumée', 'VA': 'Cendres volcaniques',
        'DU': 'Poussières', 'SA': 'Sable', 'HZ': 'Brume sèche', 'SQ': 'Grains'
    }
    
    phen_txt = phenomenes.get(token, token)
    return f"{intensite}{desc_txt}{phen_txt}"

def analyser_metar_detaille(metar):
    if not metar:
        return None
        
    data = {
        "raw": metar,
        "station": "",
        "heure": "Heure inconnue", # Valeur par défaut
        "jour": "",
        "auto": False,
        "vent": "Indéterminé",
        "visi": "Indéterminée",
        "temps": [],
        "nuages": [],
        "temp": None,
        "dew": None,
        "qnh": None,
        "tendance": []
    }

    # Séparation Tendance
    match_trend = re.search(r'\b(NOSIG|BECMG|TEMPO)\b', metar)
    if match_trend:
        split_idx = match_trend.start()
        main_part = metar[:split_idx]
        trend_part = metar[split_idx:]
        data["tendance"].append(trend_part)
    else:
        main_part = metar

    tokens = main_part.split()
    
    for t in tokens:
        # Station (4 lettres)
        if len(t) == 4 and t.isalpha():
            data["station"] = t
            continue
            
        # Date et Heure (ex: 241030Z -> Le 24 à 10h30)
        # Regex pour JJHHMMZ
        if re.match(r'^\d{6}Z$', t):
            jour = t[0:2]
            heure = t[2:4]
            minute = t[4:6]
            data["heure"] = f"{heure}h{minute} UTC"
            data["jour"] = f"Le {jour} du mois"
            continue
            
        # Auto
        if t == "AUTO":
            data["auto"] = True
            continue

        # [span_1](start_span)Vent (ex: 32010G20KT) - Page 16[span_1](end_span)
        if re.match(r'^(VRB|\d{3})\d{2}(G\d{2})?KT$', t):
            d = t[:3]
            s = t[3:5]
            g = re.search(r'G(\d{2})', t)
            
            dir_txt = "Variable" if d == "VRB" else f"{d}°"
            rafale = f" (Rafales {g.group(1)} kt)" if g else ""
            data["vent"] = f"{dir_txt} à {int(s)} kt{rafale}"
            continue
        
        # Variation vent
        if re.match(r'^\d{3}V\d{3}$', t):
            data["vent"] += f" (Var. {t.replace('V', '° - ')}°)"
            continue

        # Visibilité
        if re.match(r'^\d{4}$', t):
            data["visi"] = "> 10 km" if t == "9999" else f"{int(t)} mètres"
            continue
            
        # [span_2](start_span)CAVOK - Page 19[span_2](end_span)
        if t == "CAVOK":
            data["visi"] = "CAVOK (>10km)"
            data["nuages"].append("R.A.S. (Plafond clair)")
            data["temps"].append("Aucun phénomène significatif")
            continue

        # [span_3](start_span)Température / Point de rosée - Page 19[span_3](end_span)
        match_temp = re.match(r'^(M?\d{2})/(M?\d{2}|//)$', t)
        if match_temp:
            t_val = match_temp.group(1).replace('M', '-')
            d_val = match_temp.group(2).replace('M', '-')
            data["temp"] = int(t_val)
            if d_val != '//':
                data["dew"] = int(d_val)
            continue

        # [span_4](start_span)QNH - Page 19[span_4](end_span)
        if re.match(r'^Q\d{3,4}$', t):
            data["qnh"] = int(t[1:])
            continue

        # [span_5](start_span)Nuages - Page 19[span_5](end_span)
        match_cloud = re.match(r'^(FEW|SCT|BKN|OVC|VV)(\d{3}|///)(CB|TCU)?$', t)
        if match_cloud:
            type_n = match_cloud.group(1)
            haut = match_cloud.group(2)
            cb = match_cloud.group(3) or ""
            h_txt = f"{int(haut)*100} ft" if haut != '///' else "Hauteur inconnue"
            noms = {'FEW': 'Peu (1-2/8)', 'SCT': 'Épars (3-4/8)', 'BKN': 'Fragmenté (5-7/8)', 'OVC': 'Couvert (8/8)', 'VV': 'Visibilité Vert.'}
            data["nuages"].append(f"{noms.get(type_n, type_n)} à {h_txt}{' ⚠️ '+cb if cb else ''}")
            continue

        # Temps
        codes_base = ['DZ', 'RA', 'SN', 'SG', 'PL', 'GR', 'GS', 'BR', 'FG', 'FU', 'VA', 'DU', 'SA', 'HZ', 'PO', 'SQ', 'FC', 'SS', 'DS', 'TS', 'SH']
        clean_t = t.replace('-','').replace('+','').replace('VC','')
        if any(code in clean_t for code in codes_base):
            data["temps"].append(decoder_phenomenes(t))

    return data

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Décodeur METAR Pro", page_icon="✈️", layout="centered")

st.title("✈️ Météo Aéronautique")
st.markdown("Décodeur METAR détaillé pour mobile.")

oaci = st.text_input("Code OACI", value="LFQQ", max_chars=4).upper()

if st.button("Actualiser", type="primary"):
    with st.spinner('Connexion NOAA...'):
        raw = recuperer_metar(oaci)
        
        if raw:
            d = analyser_metar_detaille(raw)
            
            # --- En-tête avec Date et Heure ---
            # C'est ici que l'affichage est modifié
            if d['jour']:
                st.success(f"📅 **Publication : {d['jour']} à {d['heure']}**")
            else:
                st.warning("Date et heure non identifiées")

            with st.expander("Voir le message brut"):
                st.code(raw, language="text")
            
            # --- Indicateurs ---
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Vent", d['vent'])
            with col2:
                delta = ""
                valeur_temp = "N/A"
                if d['temp'] is not None and d['dew'] is not None:
                    ecart = d['temp'] - d['dew']
                    delta = f"Spread: {ecart}°"
                    valeur_temp = f"{d['temp']}°C"
                st.metric("Température", valeur_temp, delta)
            with col3:
                st.metric("QNH", f"{d['qnh']} hPa" if d['qnh'] else "N/A")

            st.divider()
            
            # Détails
            st.markdown(f"**👀 Visibilité :** {d['visi']}")
            
            if d['dew'] is not None:
                st.markdown(f"**💧 Point de rosée :** {d['dew']}°C")
                if (d['temp'] - d['dew']) <= 2:
                     st.warning("⚠️ Risque fort de brouillard ou givrage (Ecart < 2°C)")
            
            if d['temps']:
                st.markdown(f"**🌧️ Temps présent :** {', '.join(d['temps'])}")
            else:
                st.markdown("**🌧️ Temps présent :** Aucun phénomène majeur signalé")

            if d['nuages']:
                st.markdown("**☁️ Couverture nuageuse :**")
                for n in d['nuages']:
                    st.text(f"  • {n}")
            else:
                st.markdown("**☁️ Nuages :** NSC (Pas de nuages significatifs)")

            if d['tendance']:
                with st.expander("🔮 Tendance (2h)", expanded=True):
                    st.info(d['tendance'][0])
                    st.caption("BECMG = Évolution / TEMPO = Temporaire")
            
        else:
            st.error(f"Données indisponibles pour {oaci}.")
