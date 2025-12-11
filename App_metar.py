import streamlit as st
import requests
import re

# --- FONCTIONS DE RÉCUPÉRATION ET DÉCODAGE ---

def recuperer_metar(oaci):
    # Utilisation de f-string sans espaces parasites
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
    # Basé sur le Guide Aviation Page 18
    intensite = ""
    if token.startswith('-'): intensite = "Faible "; token = token[1:]
    elif token.startswith('+'): intensite = "Forte "; token = token[1:]
    elif token.startswith('VC'): intensite = "Au voisinage : "; token = token[2:]

    descripteurs = {'MI': 'Mince', 'BC': 'Bancs', 'PR': 'Partiel', 'DR': 'Chasse-basse', 'BL': 'Chasse-élevée', 'SH': 'Averses', 'TS': 'Orageux', 'FZ': 'Se congelant'}
    desc_txt = ""
    if len(token) >= 2 and token[:2] in descripteurs:
        desc_txt = descripteurs[token[:2]] + " de "
        token = token[2:]

    phenomenes = {'DZ': 'Bruine', 'RA': 'Pluie', 'SN': 'Neige', 'SG': 'Neige en grains', 'PL': 'Granules de glace', 'GR': 'Grêle', 'GS': 'Grésil', 'BR': 'Brume', 'FG': 'Brouillard', 'FU': 'Fumée', 'VA': 'Cendres', 'DU': 'Poussières', 'SA': 'Sable', 'HZ': 'Brume sèche', 'SQ': 'Grains', 'NSW': 'Fin des phénomènes significatifs'}
    
    phen_txt = phenomenes.get(token, token)
    return f"{intensite}{desc_txt}{phen_txt}"

def analyser_bloc_tendance(trend_raw):
    """Analyse détaillée de la partie tendance (BECMG, TEMPO...)"""
    if "NOSIG" in trend_raw:
        return ["**Aucun changement significatif prévu** dans les 2 prochaines heures."]

    analyses = []
    # On découpe s'il y a plusieurs tendances successives
    blocs = re.split(r'\s+(?=BECMG|TEMPO)', trend_raw)
    
    for bloc in blocs:
        message = ""
        # 1. Type d'évolution
        if "TEMPO" in bloc:
            message += "**Temporairement** (Fluctuation < 1h) : "
        elif "BECMG" in bloc:
            message += "**Évolution progressive** (Devenant) : "
        
        tokens = bloc.split()
        details = []
        
        for t in tokens:
            # Horaires (FM=From, TL=Until, AT=At)
            if t.startswith("FM"):
                details.append(f"à partir de {t[2:4]}h{t[4:6]} UTC")
            elif t.startswith("TL"):
                details.append(f"jusqu'à {t[2:4]}h{t[4:6]} UTC")
            elif t.startswith("AT"):
                details.append(f"à {t[2:4]}h{t[4:6]} UTC")
            
            # Paramètres météo
            elif re.match(r'^\d{4}$', t):
                v = "> 10 km" if t == "9999" else f"{int(t)} m"
                details.append(f"Visibilité {v}")
            elif re.match(r'^(VRB|\d{3})\d{2}(G\d{2})?KT$', t):
                details.append(f"Vent {t}")
            elif re.match(r'^(FEW|SCT|BKN|OVC|VV)\d{3}(CB|TCU)?$', t) or t == "NSC":
                if t == "NSC": details.append("Nuages sans importance")
                elif t.startswith("VV"): details.append(f"Ciel invisible ({t})")
                else: details.append(f"Plafond {t}")
            elif t == 'NSW':
                 details.append("Fin du temps significatif")
            elif any(code in t for code in ['RA', 'SN', 'FG', 'BR', 'TS', 'SH', 'DZ']):
                details.append(decoder_phenomenes(t))
                
        # Assemblage
        changes = ", ".join(details)
        if changes:
            analyses.append(f"{message} {changes}")
        else:
            if len(message) > 5:
                analyses.append(f"{message} (Paramètres non décodés : {bloc})")
            
    return analyses

def analyser_metar_detaille(metar):
    if not metar: return None
        
    data = {
        "raw": metar, "station": "", "heure": "Inconnue", "jour": "", "auto": False,
        "vent": "Indéterminé", "visi": "Indéterminée", "temps": [], "nuages": [],
        "temp": None, "dew": None, "qnh": None, "tendance_raw": None, "tendance_analyse": []
    }

    # Extraction de la partie tendance (NOSIG, BECMG, TEMPO)
    match_trend = re.search(r'\b(NOSIG|BECMG|TEMPO)\b', metar)
    if match_trend:
        split_idx = match_trend.start()
        main_part = metar[:split_idx]
        data["tendance_raw"] = metar[split_idx:]
        data["tendance_analyse"] = analyser_bloc_tendance(data["tendance_raw"])
    else:
        main_part = metar

    tokens = main_part.split()
    
    for t in tokens:
        if len(t) == 4 and t.isalpha(): data["station"] = t
        elif re.match(r'^\d{6}Z$', t):
            data["heure"] = f"{t[2:4]}h{t[4:6]} UTC"
            data["jour"] = f"Le {t[0:2]}"
        elif t == "AUTO": data["auto"] = True
        elif re.match(r'^(VRB|\d{3})\d{2}(G\d{2})?KT$', t):
            d, s, g = t[:3], t[3:5], re.search(r'G(\d{2})', t)
            data["vent"] = f"{'Var' if d=='VRB' else d+'°'} / {int(s)} kt{' (Raf '+g.group(1)+')' if g else ''}"
        elif re.match(r'^\d{3}V\d{3}$', t): data["vent"] += f" (Var {t})"
        elif re.match(r'^\d{4}$', t): data["visi"] = "> 10 km" if t == "9999" else f"{int(t)} m"
        elif t == "CAVOK":
            data["visi"], data["nuages"] = "CAVOK (>10km)", ["Plafond et visibilité OK"]
        elif re.match(r'^(M?\d{2})/(M?\d{2}|//)$', t):
            t_val, d_val = t.split('/')
            data["temp"] = int(t_val.replace('M', '-'))
            if d_val != '//': data["dew"] = int(d_val.replace('M', '-'))
        elif re.match(r'^Q\d{3,4}$', t): data["qnh"] = int(t[1:])
        
        # --- BLOC NUAGES MIS A JOUR ---
        elif re.match(r'^(FEW|SCT|BKN|OVC|VV)(\d{3}|///)(CB|TCU)?$', t):
            match_cloud = re.match(r'^(FEW|SCT|BKN|OVC|VV)(\d{3}|///)(CB|TCU)?$', t)
            type_n = match_cloud.group(1)
            haut = match_cloud.group(2)
            cb = match_cloud.group(3) or ""

            # Gestion spécifique du VV (Ciel invisible)
            if type_n == "VV":
                h_txt = f"Visibilité vert. {int(haut)*100} ft" if haut != '///' else "Hauteur indéterminée"
                data["nuages"].append(f"Ciel invisible ({h_txt})")
            else:
                # Gestion classique des nuages
                h_txt = f"{int(haut)*100} ft" if haut != '///' else "H. inconnue"
                noms = {'FEW': 'Peu (1-2/8)', 'SCT': 'Épars (3-4/8)', 'BKN': 'Fragmenté (5-7/8)', 'OVC': 'Couvert (8/8)'}
                data["nuages"].append(f"{noms.get(type_n, type_n)} à {h_txt}{' ⚠️ '+cb if cb else ''}")
        
        else:
            codes = ['DZ', 'RA', 'SN', 'GR', 'BR', 'FG', 'FU', 'HZ', 'TS', 'SH']
            clean = t.replace('-','').replace('+','').replace('VC','')
            if any(c in clean for c in codes): data["temps"].append(decoder_phenomenes(t))

    return data

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Décodeur METAR", page_icon="✈️", layout="centered")

st.title("METAR")
st.caption("Décodeur temps réel & Analyse de tendance (2h)")

oaci = st.text_input("Code OACI", value="LFQQ", max_chars=4).upper()

if st.button("Actualiser", type="primary"):
    with st.spinner('Analyse en cours...'):
        raw = recuperer_metar(oaci)
        
        if raw:
            d = analyser_metar_detaille(raw)
            
            # En-tête Date/Heure
            if d['jour']: st.success(f"**{d['jour']} à {d['heure']}** (Publication)")
            
            # Affichage Brut
            with st.expander("Message METAR brut"):
                st.code(raw, language="text")

            # --- Indicateurs Clés ---
            c1, c2, c3 = st.columns(3)
            c1.metric("Vent", d['vent'])
            
            temp_aff = "N/A"
            delta = ""
            if d['temp'] is not None and d['dew'] is not None:
                spread = d['temp'] - d['dew']
                temp_aff = f"{d['temp']}°C"
                delta = f"Spread: {spread}°"
            c2.metric("Température", temp_aff, delta)
            
            c3.metric("QNH", f"{d['qnh']} hPa" if d['qnh'] else "N/A")

            # --- Conditions Actuelles ---
            st.markdown("### Conditions Actuelles")
            
            if d['temp'] is not None and d['dew'] is not None and (d['temp'] - d['dew']) <= 2:
                 st.warning(f"⚠️ **Attention :** Écart Temp/Rosée faible ({d['temp']-d['dew']}°C). Risque de brouillard ou givrage.")

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**👀 Visibilité :** {d['visi']}")
                if d['temps']: st.markdown(f"**🌧️ Phénomènes :** {', '.join(d['temps'])}")
                else: st.markdown("**🌧️ Phénomènes :** Aucun")
            
            with col_b:
                if d['dew'] is not None: st.markdown(f"**💧 Point de rosée :** {d['dew']}°C")
                if d['nuages']: 
                    st.markdown("**☁️ Nuages :**")
                    for n in d['nuages']: st.caption(f"• {n}")
                else: st.markdown("**☁️ Nuages :** NSC / CAVOK")

            # --- Analyse de Tendance (2h) ---
            st.divider()
            st.subheader("Prévision immédiate (Tendance 2h)")
            
            if d['tendance_analyse']:
                for item in d['tendance_analyse']:
                    if "Aucun changement" in item:
                        st.success(item)
                    elif "Temporairement" in item:
                        st.warning(item)
                    else:
                        st.info(item)
                
                with st.expander("Comprendre la tendance"):
                    st.markdown("""
                    *Validité : 2 heures à partir de l'observation.*
                    - **NOSIG** : Pas de changement significatif.
                    - **BECMG** : Changement durable qui s'installe.
                    - **TEMPO** : Fluctuation temporaire (moins d'une heure).
                    """)
            else:
                st.markdown("Pas de données de tendance disponibles dans ce message.")

        else:
            st.error("Station introuvable ou erreur de connexion.")
