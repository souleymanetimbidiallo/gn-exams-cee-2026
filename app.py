import unicodedata
import warnings
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import pydeck as pdk

warnings.filterwarnings("ignore", message="Cannot parse header or footer.*")

st.set_page_config(page_title="Explorer CEE 2026", page_icon="🎓", layout="wide")

EXCEL_FILE = "CEE-2026.xlsx"
PARQUET_FILE = "cee_2026.parquet"

EXPECTED_COLUMNS = ["DPE", "Rang", "ex", "Prénoms et Noms", "Centre", "PV", "Origine", "Mention"]


def normalize_text(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().lower()
    value = unicodedata.normalize("NFD", value)
    return "".join(c for c in value if unicodedata.category(c) != "Mn")


def clean_col_name(col):
    return "_".join(str(col).strip().split())


def normalize_mention(value):
    v = normalize_text(value).replace(" ", "")
    if v in ("tbien", "tresbien", "t.bien"):
        return "Très Bien"
    if v == "bien":
        return "Bien"
    if v in ("abien", "assezbien", "a.bien"):
        return "Assez Bien"
    if not v or v == "nan":
        return "Sans mention"
    return str(value).strip()


@st.cache_data(show_spinner="Chargement du fichier Excel...")
def load_excel(file_path: str) -> pd.DataFrame:
    frames = []
    sheets = pd.ExcelFile(file_path).sheet_names

    for sheet_name in sheets:
        # IMPORTANT : la vraie ligne d'en-tête est la 2e ligne Excel, donc header=1.
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=1, dtype=str)
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")

        # Si une feuille est mal lue, on force les colonnes attendues.
        if len(df.columns) >= 8:
            df = df.iloc[:, :8]
            df.columns = EXPECTED_COLUMNS

        df["Type"] = "Franco-Arabe" if "FA" in sheet_name.upper() else "Enseignement général"
        df["Feuille"] = sheet_name
        frames.append(df)

    data = pd.concat(frames, ignore_index=True)
    data.columns = [clean_col_name(c) for c in data.columns]

    for col in ["DPE", "Rang", "ex", "Prénoms_et_Noms", "Centre", "PV", "Origine", "Mention", "Type", "Feuille"]:
        if col not in data.columns:
            data[col] = ""
        data[col] = data[col].fillna("").astype(str).str.strip()

    data["Mention_Normalisée"] = data["Mention"].map(normalize_mention)

    data["search_text"] = (
        data["Prénoms_et_Noms"].map(normalize_text) + " " +
        data["PV"].map(normalize_text) + " " +
        data["Centre"].map(normalize_text) + " " +
        data["Origine"].map(normalize_text) + " " +
        data["DPE"].map(normalize_text)
    )

    return data


def convert_to_parquet():
    if not Path(EXCEL_FILE).exists():
        return False
    df = load_excel(EXCEL_FILE)
    for col in df.columns:
        df[col] = df[col].fillna("").astype(str)
    df.to_parquet(PARQUET_FILE, index=False, engine="pyarrow")
    return True


@st.cache_data(show_spinner="Chargement des données...")
def load_data() -> pd.DataFrame:
    if Path(PARQUET_FILE).exists():
        return pd.read_parquet(PARQUET_FILE)
    if Path(EXCEL_FILE).exists():
        return load_excel(EXCEL_FILE)
    st.error(f"Fichier introuvable : {EXCEL_FILE}. Mets-le dans le même dossier que app.py")
    st.stop()


def apply_filters(df):
    with st.sidebar:
        st.header("Filtres")
        types = sorted([x for x in df["Type"].unique() if x])
        selected_types = st.multiselect("Type", types, default=types)

        dpes = sorted([x for x in df["DPE"].unique() if x])
        selected_dpes = st.multiselect("DPE", dpes)

        mentions = sorted([x for x in df["Mention_Normalisée"].unique() if x])
        selected_mentions = st.multiselect("Mention", mentions)

        search = st.text_input("Recherche nom, PV, école, centre...")

    filtered = df[df["Type"].isin(selected_types)]
    if selected_dpes:
        filtered = filtered[filtered["DPE"].isin(selected_dpes)]
    if selected_mentions:
        filtered = filtered[filtered["Mention_Normalisée"].isin(selected_mentions)]
    if search:
        filtered = filtered[filtered["search_text"].str.contains(normalize_text(search), na=False, regex=False)]
    return filtered


def create_student_card(row):
    width, height = 1080, 1350
    img = Image.new("RGB", (width, height), "#F3F6FA")
    draw = ImageDraw.Draw(img)

    red = "#CE1126"
    yellow = "#FCD116"
    green = "#009460"
    dark = "#111827"
    gray = "#6B7280"
    light_gray = "#E5E7EB"

    def font(size, bold=False):
        paths = [
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return ImageFont.load_default()

    title_font = font(72, True)
    subtitle_font = font(36, False)
    name_font = font(52, True)
    label_font = font(30, False)
    value_font = font(38, True)
    small_font = font(26, False)

    name = str(row.get("Prénoms_et_Noms", "")).upper()
    mention = str(row.get("Mention_Normalisée", ""))
    school = str(row.get("Origine", ""))
    dpe = str(row.get("DPE", ""))
    centre = str(row.get("Centre", ""))
    rang = str(row.get("Rang", ""))
    pv = str(row.get("PV", ""))

    # Bandeau Guinée
    draw.rectangle([0, 0, 360, 55], fill=red)
    draw.rectangle([360, 0, 720, 55], fill=yellow)
    draw.rectangle([720, 0, 1080, 55], fill=green)

    # Header
    draw.text((80, 130), "Félicitations !", fill=green, font=title_font)
    draw.text((80, 230), "Certificat d'Études Élémentaires", fill=dark, font=subtitle_font)
    draw.text((80, 280), "CEE Guinée 2026", fill=gray, font=subtitle_font)

    # Badge admis
    draw.rounded_rectangle([780, 145, 1000, 225], radius=35, fill=green)
    draw.text((835, 165), "ADMIS", fill="white", font=font(34, True))

    # Carte principale
    draw.rounded_rectangle(
        [80, 390, 1000, 1160],
        radius=45,
        fill="white",
        outline=light_gray,
        width=4
    )

    y = 455

    draw.text((130, y), "ÉLÈVE", fill=gray, font=label_font)
    y += 45
    draw.text((130, y), name[:32], fill=dark, font=name_font)

    y += 100
    draw.text((130, y), "MENTION", fill=gray, font=label_font)
    y += 45
    draw.text((130, y), mention.upper(), fill=green, font=value_font)

    y += 85
    draw.text((130, y), "ÉCOLE", fill=gray, font=label_font)
    y += 45
    draw.text((130, y), school[:34], fill=dark, font=value_font)

    y += 85
    draw.text((130, y), "DPE", fill=gray, font=label_font)
    y += 45
    draw.text((130, y), dpe, fill=dark, font=value_font)

    y += 80
    draw.text((130, y), "CENTRE", fill=gray, font=label_font)
    y += 40
    draw.text((130, y), centre[:40], fill=dark, font=small_font)

    y += 65
    draw.rounded_rectangle(
        [130, y, 900, y + 70],
        radius=20,
        fill="#F3F6FA"
    )

    draw.text((160, y + 18), f"Rang : {rang}", fill=dark, font=small_font)
    draw.text((560, y + 18), f"PV : {pv}", fill=dark, font=small_font)

    # Footer
    draw.line([80, 1230, 1000, 1230], fill=light_gray, width=2)

    draw.text(
        (80, 1260),
        "Explorer CEE 2026",
        fill=dark,
        font=font(32, True)
    )

    draw.text(
        (80, 1305),
        "Analyse des performances scolaires guinéennes",
        fill=gray,
        font=small_font
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer


DPE_COORDS = {
    "RATOMA": [9.6412, -13.5784],
    "MATOTO": [9.5700, -13.6200],
    "DIXINN": [9.5600, -13.6700],
    "KALOUM": [9.5092, -13.7122],
    "MATAM": [9.5350, -13.6700],
    "COYAH": [9.7056, -13.3847],
    "DUBREKA": [9.7911, -13.5144],
    "KINDIA": [10.0569, -12.8658],
    "BOKE": [10.9409, -14.2967],
    "LABE": [11.3182, -12.2833],
    "MAMOU": [10.3755, -12.0915],
    "FARANAH": [10.0404, -10.7434],
    "KANKAN": [10.3854, -9.3057],
    "SIGUIRI": [11.4189, -9.1686],
    "KOUROUSSA": [10.6500, -9.8833],
    "KEROUANE": [9.2667, -9.0167],
    "MANDIANA": [10.6333, -8.6833],
    "NZEREKORE": [7.7562, -8.8179],
    "N'ZEREKORE": [7.7562, -8.8179],
    "GUECKEDOU": [8.5667, -10.1333],
    "MACENTA": [8.5435, -9.4710],
    "LOLA": [7.8000, -8.5333],
    "BEYLA": [8.6833, -8.6333],
    "YOMOU": [7.5600, -9.2700],
    "DALABA": [10.7000, -12.2500],
    "PITA": [11.0833, -12.4000],
    "TOUGUE": [11.4667, -11.6000],
    "MALI": [12.0833, -12.3000],
    "KOUNDARA": [12.4833, -13.3000],
    "GAOUAL": [11.7500, -13.2000],
    "TELIMELE": [10.9000, -13.0333],
    "FORECARIAH": [9.4300, -13.0881],
    "FRIA": [10.4500, -13.5333],
    "Boffa": [10.1667, -14.0333],
}


def main():
    st.title("🎓 Explorer des résultats CEE 2026")
    st.caption("Recherche, filtres, statistiques et classements.")

    df = load_data()
    filtered = apply_filters(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidats", f"{len(filtered):,}".replace(",", " "))
    c2.metric("DPE", filtered["DPE"].nunique())
    c3.metric("Centres", filtered["Centre"].nunique())
    c4.metric("Écoles", filtered["Origine"].nunique())

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🔎 Recherche",
        "📊 Statistiques",
        "🏫 Écoles",
        "🏫 Fiche école",
        "🥇 Fiche élève",
        "🏆 Classements",
        "📍 Carte Guinée",
        "⚙️ Données"
    ])

    cols = ["DPE", "Rang", "ex", "Prénoms_et_Noms", "Centre", "PV", "Origine", "Mention", "Mention_Normalisée", "Type"]

    with tab1:
        st.subheader("Résultats filtrés")
        st.dataframe(filtered[cols], use_container_width=True, height=600)
        st.download_button(
            "Télécharger les résultats filtrés en CSV",
            data=filtered[cols].to_csv(index=False).encode("utf-8-sig"),
            file_name="resultats_cee_2026_filtres.csv",
            mime="text/csv",
        )

    with tab2:
        st.subheader("Répartition par mention")
        mention_stats = filtered.groupby("Mention_Normalisée").size().reset_index(name="Nombre").sort_values("Nombre", ascending=False)
        st.plotly_chart(px.bar(mention_stats, x="Mention_Normalisée", y="Nombre", text="Nombre"), use_container_width=True)

        st.subheader("Top 20 DPE par nombre de candidats")
        dpe_stats = filtered.groupby("DPE").size().reset_index(name="Nombre").sort_values("Nombre", ascending=False).head(20)
        st.plotly_chart(px.bar(dpe_stats, x="DPE", y="Nombre", text="Nombre"), use_container_width=True)

    with tab3:
        st.subheader("Classement des écoles")
        con = duckdb.connect(database=":memory:")
        con.register("filtered_view", filtered)
        school_stats = con.execute('''
            SELECT
                Origine AS Ecole,
                DPE,
                COUNT(*) AS Nombre,
                SUM(CASE WHEN Mention_Normalisée = 'Très Bien' THEN 1 ELSE 0 END) AS Tres_Bien,
                SUM(CASE WHEN Mention_Normalisée = 'Bien' THEN 1 ELSE 0 END) AS Bien,
                SUM(CASE WHEN Mention_Normalisée = 'Assez Bien' THEN 1 ELSE 0 END) AS Assez_Bien
            FROM filtered_view
            WHERE Origine IS NOT NULL AND Origine <> ''
            GROUP BY Origine, DPE
            ORDER BY Nombre DESC
            LIMIT 100
        ''').fetchdf()
        con.close()
        st.dataframe(school_stats, use_container_width=True, height=600)

    with tab4:
        st.subheader("🏫 Fiche détaillée d’une école")

        ecoles = sorted([x for x in filtered["Origine"].unique() if x])
        selected_school = st.selectbox("Choisir une école", ecoles)

        school_df = filtered[filtered["Origine"] == selected_school].copy()

        if school_df.empty:
            st.warning("Aucune donnée trouvée pour cette école.")
        else:
            dpe_school = school_df["DPE"].mode()[0]
            type_school = school_df["Type"].mode()[0]

            total = len(school_df)
            tb = (school_df["Mention_Normalisée"] == "Très Bien").sum()
            bien = (school_df["Mention_Normalisée"] == "Bien").sum()
            abien = (school_df["Mention_Normalisée"] == "Assez Bien").sum()

            score = tb * 5 + bien * 3 + abien * 1
            taux_tb = round((tb / total) * 100, 2) if total else 0

            st.markdown(f"## {selected_school}")
            st.caption(f"DPE : {dpe_school} | Type : {type_school}")

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Admis", total)
            c2.metric("Très Bien", tb)
            c3.metric("Bien", bien)
            c4.metric("Assez Bien", abien)
            c5.metric("Score excellence", score)

            st.metric("Taux Très Bien", f"{taux_tb} %")

            st.divider()

            st.markdown("### 📊 Répartition des mentions")
            mention_stats = (
                school_df.groupby("Mention_Normalisée")
                .size()
                .reset_index(name="Nombre")
                .sort_values("Nombre", ascending=False)
            )

            st.plotly_chart(
                px.bar(
                    mention_stats,
                    x="Mention_Normalisée",
                    y="Nombre",
                    text="Nombre",
                    title=f"Répartition des mentions - {selected_school}"
                ),
                use_container_width=True
            )

            st.divider()

            st.markdown("### 🥇 Meilleurs élèves de l’école")

            mention_order = {
                "Très Bien": 3,
                "Bien": 2,
                "Assez Bien": 1,
                "Sans mention": 0
            }

            school_df["Score_Mention"] = school_df["Mention_Normalisée"].map(mention_order).fillna(0)
            school_df["Rang_Num"] = pd.to_numeric(school_df["Rang"], errors="coerce")

            best_students = school_df.sort_values(
                by=["Score_Mention", "Rang_Num"],
                ascending=[False, True]
            )

            st.dataframe(
                best_students[
                    ["Rang", "Prénoms_et_Noms", "Centre", "PV", "Mention_Normalisée", "Type"]
                ].head(50),
                use_container_width=True,
                height=500
            )

            st.download_button(
                "Télécharger la fiche école en CSV",
                data=school_df[
                    ["DPE", "Rang", "Prénoms_et_Noms", "Centre", "PV", "Origine", "Mention_Normalisée", "Type"]
                ].to_csv(index=False).encode("utf-8-sig"),
                file_name=f"fiche_ecole_{selected_school}.csv",
                mime="text/csv",
            )

    with tab5:
        st.subheader("🥇 Fiche élève partageable")

        search_student = st.text_input(
            "Rechercher un élève par PV",
            key="student_card_search"
        )

        student_results = filtered.copy()

        if search_student:
            student_results = student_results[
                student_results["PV"].astype(str).str.strip().str.contains(
                    search_student.strip(),
                    na=False,
                    regex=False
                )
            ]

        st.dataframe(
            student_results[
                ["DPE", "Rang", "Prénoms_et_Noms", "Centre", "PV", "Origine", "Mention_Normalisée", "Type"]
            ].head(100),
            use_container_width=True,
            height=350
        )

        if not student_results.empty:
            student_options = (
                student_results["Prénoms_et_Noms"]
                + " | "
                + student_results["Origine"]
                + " | PV: "
                + student_results["PV"]
            ).head(100).tolist()

            selected_student_label = st.selectbox(
                "Choisir l’élève pour générer la fiche",
                student_options
            )

            selected_index = student_options.index(selected_student_label)
            selected_student = student_results.head(100).iloc[selected_index]

            st.markdown("### Aperçu de la fiche")

            c1, c2, c3 = st.columns(3)
            c1.metric("Élève", selected_student["Prénoms_et_Noms"])
            c2.metric("Mention", selected_student["Mention_Normalisée"])
            c3.metric("DPE", selected_student["DPE"])

            card = create_student_card(selected_student)

            st.image(card, caption="Fiche élève générée", use_column_width=True)

            st.download_button(
                "Télécharger la fiche en PNG",
                data=card,
                file_name=f"fiche_eleve_{selected_student['PV']}.png",
                mime="image/png",
            )
        else:
            st.info("Aucun élève trouvé avec ce PV.")

    with tab6:
        st.subheader("🏆 Classements élèves / écoles")

        st.markdown("### 🥇 Top élèves")
        top_eleves = filtered.copy()

        mention_order = {
            "Très Bien": 3,
            "Bien": 2,
            "Assez Bien": 1,
            "Sans mention": 0
        }

        top_eleves["Score_Mention"] = top_eleves["Mention_Normalisée"].map(mention_order).fillna(0)
        top_eleves["Rang_Num"] = pd.to_numeric(top_eleves["Rang"], errors="coerce")

        top_eleves = top_eleves.sort_values(
            by=["Score_Mention", "Rang_Num"],
            ascending=[False, True]
        )

        st.dataframe(
            top_eleves[
                ["DPE", "Rang", "Prénoms_et_Noms", "Centre", "PV", "Origine", "Mention_Normalisée", "Type"]
            ].head(100),
            use_container_width=True,
            height=500
        )

        st.download_button(
            "Télécharger Top élèves en CSV",
            data=top_eleves[
                ["DPE", "Rang", "Prénoms_et_Noms", "Centre", "PV", "Origine", "Mention_Normalisée", "Type"]
            ].head(1000).to_csv(index=False).encode("utf-8-sig"),
            file_name="top_eleves_cee_2026.csv",
            mime="text/csv",
        )

        st.divider()

        st.markdown("### 🏫 Top écoles par excellence")

        school_ranking = (
            filtered.groupby(["Origine", "DPE", "Type"])
            .agg(
                Nombre=("Origine", "size"),
                Tres_Bien=("Mention_Normalisée", lambda x: (x == "Très Bien").sum()),
                Bien=("Mention_Normalisée", lambda x: (x == "Bien").sum()),
                Assez_Bien=("Mention_Normalisée", lambda x: (x == "Assez Bien").sum()),
            )
            .reset_index()
        )

        school_ranking["Score_Excellence"] = (
            school_ranking["Tres_Bien"] * 5
            + school_ranking["Bien"] * 3
            + school_ranking["Assez_Bien"] * 1
        )

        school_ranking["Taux_Tres_Bien"] = (
            school_ranking["Tres_Bien"] / school_ranking["Nombre"] * 100
        ).round(2)

        school_ranking = school_ranking.sort_values(
            by=["Score_Excellence", "Tres_Bien", "Bien", "Nombre"],
            ascending=False
        )

        st.dataframe(
            school_ranking.head(100),
            use_container_width=True,
            height=600
        )

        st.download_button(
            "Télécharger Top écoles en CSV",
            data=school_ranking.to_csv(index=False).encode("utf-8-sig"),
            file_name="top_ecoles_cee_2026.csv",
            mime="text/csv",
        )

        st.divider()

        st.markdown("### 🎯 Top écoles par DPE")

        selected_dpe_ranking = st.selectbox(
            "Choisir une DPE pour le classement des écoles",
            sorted(filtered["DPE"].dropna().unique()),
            key="ranking_dpe"
        )

        top_ecoles_dpe = school_ranking[
            school_ranking["DPE"] == selected_dpe_ranking
        ].head(20)

        st.dataframe(
            top_ecoles_dpe,
            use_container_width=True,
            height=500
        )

    with tab7:
        st.subheader("📍 Carte interactive des performances par DPE")

        map_stats = (
            filtered.groupby("DPE")
            .agg(
                Candidats=("DPE", "size"),
                Tres_Bien=("Mention_Normalisée", lambda x: (x == "Très Bien").sum()),
                Bien=("Mention_Normalisée", lambda x: (x == "Bien").sum()),
                Assez_Bien=("Mention_Normalisée", lambda x: (x == "Assez Bien").sum()),
            )
            .reset_index()
        )

        map_stats["Score"] = (
            map_stats["Tres_Bien"] * 5
            + map_stats["Bien"] * 3
            + map_stats["Assez_Bien"] * 1
        )

        map_stats["Latitude"] = map_stats["DPE"].map(lambda x: DPE_COORDS.get(str(x).upper(), [None, None])[0])
        map_stats["Longitude"] = map_stats["DPE"].map(lambda x: DPE_COORDS.get(str(x).upper(), [None, None])[1])

        map_stats = map_stats.dropna(subset=["Latitude", "Longitude"])

        map_stats["Rayon"] = (map_stats["Score"] / map_stats["Score"].max() * 50000).clip(lower=8000)

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_stats,
            get_position="[Longitude, Latitude]",
            get_radius="Rayon",
            get_fill_color="[0, 148, 96, 140]",
            pickable=True,
        )

        view_state = pdk.ViewState(
            latitude=9.9456,
            longitude=-9.6966,
            zoom=5.5,
            pitch=0,
        )

        tooltip = {
            "html": """
            <b>DPE :</b> {DPE}<br/>
            <b>Candidats :</b> {Candidats}<br/>
            <b>Très Bien :</b> {Tres_Bien}<br/>
            <b>Bien :</b> {Bien}<br/>
            <b>Score :</b> {Score}
            """,
            "style": {
                "backgroundColor": "white",
                "color": "black"
            }
        }

        st.pydeck_chart(
            pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip=tooltip,
                map_style="light"
            )
        )

        st.dataframe(
            map_stats.sort_values("Score", ascending=False),
            use_container_width=True
        )

    with tab8:
        st.subheader("Aperçu technique")
        st.write("Dimensions du dataset :", df.shape)
        st.write("Colonnes détectées :", list(df.columns))
        st.dataframe(df.head(20), use_container_width=True)

        if st.button("Recréer le fichier Parquet"):
            if convert_to_parquet():
                st.success(f"Fichier recréé : {PARQUET_FILE}. Relance l'app si nécessaire.")
            else:
                st.error("Fichier Excel introuvable.")


if __name__ == "__main__":
    main()
