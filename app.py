"""Streamlit Web Application for interactive Talent Analytics and Candidate Matching."""

import io
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

# Set page config
st.set_page_config(
    page_title="Smart Talent BI | Analytics & Screening",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "data" / "output" / "talent_bi.db"
REPORTS_DIR = ROOT_DIR / "data" / "output" / "reports"

from src.cli.main import PipelineOrchestrator
from src.reporting.metrics import BIMetricsCalculator
from src.reporting.service import ReportingService

@st.cache_resource
def get_pipeline_data():
    if not DB_PATH.exists():
        orchestrator = PipelineOrchestrator()
        orchestrator.run_all(ROOT_DIR / "data" / "raw", DB_PATH, REPORTS_DIR)
    calc = BIMetricsCalculator.from_db_path(DB_PATH)
    kpis = calc.compute_kpi_summary()
    df_rankings = calc.get_rankings_dataframe()
    df_gaps = calc.get_gap_analysis_dataframe()
    df_ops = calc.get_operational_metrics_dataframe()
    return calc, kpis, df_rankings, df_gaps, df_ops

calc, kpis, df_rankings, df_gaps, df_ops = get_pipeline_data()

# Header
st.title("💼 Smart Talent BI Pipeline")
st.caption("Plateforme locale d'analyse décisionnelle RH, matching profil/poste et reporting opérationnel.")

# Sidebar navigation
st.sidebar.header("Navigation")
menu = st.sidebar.radio(
    "Modules :",
    ["📊 Tableau de Bord RH", "🎯 Matching & Évaluation Profil", "📑 Analyse des Écarts (Gaps)", "📥 Télécharger les Rapports"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Auteur :** Elias DANI")
st.sidebar.markdown("**GitHub :** [smart-talent-bi-pipeline](https://github.com/eliasdn/smart-talent-bi-pipeline)")

# --- TAB 1: Tableau de Bord RH ---
if menu == "📊 Tableau de Bord RH":
    st.subheader("Indicateurs Clés de Performance (KPIs)")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Candidats Analysés", f"{kpis.total_candidates}")
    col2.metric("Postes Ouverts", f"{kpis.total_jobs}")
    col3.metric("Évaluations Réalisées", f"{kpis.total_evaluations}")
    col4.metric("Score Moyen Global", f"{kpis.average_matching_score:.1f} %")
    
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Profils Haute Adéquation (≥70%)", f"{kpis.high_fit_count}")
    col6.metric("Taux d'Adéquation Élevé", f"{kpis.high_fit_rate:.1f} %")
    col7.metric("Temps Gagné Estimé", f"{kpis.roi.total_hours_saved:.1f} h")
    col8.metric("Économie Estimée", f"{kpis.roi.total_cost_saved:,.2f} €")
    
    st.markdown("---")
    
    c_left, c_right = st.columns(2)
    with c_left:
        st.markdown("#### Distribution des Scores par Tranche")
        dist_data = [
            {"Tranche": d.tier_name, "Volume": d.count, "Pourcentage (%)": d.percentage}
            for d in kpis.score_distribution
        ]
        df_dist = pd.DataFrame(dist_data)
        st.bar_chart(df_dist.set_index("Tranche")["Volume"])
        
    with c_right:
        st.markdown("#### Performance par Canal de Recrutement")
        if kpis.channel_metrics:
            channel_data = [
                {"Canal": c.channel, "Candidatures": c.applicant_count, "Recrutés": c.hired_count, "Taux Conv. (%)": c.conversion_rate_percentage}
                for c in kpis.channel_metrics
            ]
            st.dataframe(pd.DataFrame(channel_data), use_container_width=True, hide_index=True)

# --- TAB 2: Matching & Évaluation Profil ---
elif menu == "🎯 Matching & Évaluation Profil":
    st.subheader("Explorateur d'Adéquation Candidat / Poste")
    
    # Filter by Job
    available_jobs = sorted(df_rankings["Job Title"].unique())
    selected_job = st.selectbox("Sélectionner une Fiche de Poste :", available_jobs)
    
    df_filtered = df_rankings[df_rankings["Job Title"] == selected_job].copy()
    
    st.markdown(f"**{len(df_filtered)} profils évalués pour le poste : `{selected_job}`**")
    
    # Rankings table
    st.dataframe(
        df_filtered[["Rank", "Candidate Name", "Overall Score", "Technical Score", "Experience Score", "Education Score", "Soft Skills Score", "Tier", "Recommendation"]],
        use_container_width=True,
        hide_index=True,
    )
    
    # Detailed profile card
    selected_cand = st.selectbox("Voir le détail d'un candidat :", df_filtered["Candidate Name"].unique())
    cand_row = df_filtered[df_filtered["Candidate Name"] == selected_cand].iloc[0]
    
    st.markdown(f"### Détail de l'évaluation : {selected_cand}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Score Global", f"{cand_row['Overall Score']:.1f} %")
    m2.metric("Compétences Techniques", f"{cand_row['Technical Score']:.1f} %")
    m3.metric("Expérience", f"{cand_row['Experience Score']:.1f} %")
    m4.metric("Formation", f"{cand_row['Education Score']:.1f} %")
    m5.metric("Soft Skills", f"{cand_row['Soft Skills Score']:.1f} %")
    
    st.info(f"**Avis / Recommandation :** {cand_row['Recommendation']}")

# --- TAB 3: Analyse des Écarts (Gaps) ---
elif menu == "📑 Analyse des Écarts (Gaps)":
    st.subheader("Analyse Détaillée des Compétences Manquantes")
    st.write("Identification objective des écarts entre profil et poste pour orienter les plans de formation.")
    
    st.dataframe(
        df_gaps[["Candidate Name", "Job Title", "Matched Skills", "Missing Required Skills", "Experience Delta Years", "Key Strengths", "Key Gaps"]],
        use_container_width=True,
        hide_index=True,
    )

# --- TAB 4: Télécharger les Rapports ---
elif menu == "📥 Télécharger les Rapports":
    st.subheader("Export des Livrables Décisionnels")
    st.write("Générez et téléchargez directement les rapports au format Excel et PDF validés par le pipeline.")
    
    col_excel, col_pdf = st.columns(2)
    
    excel_path = REPORTS_DIR / "talent_bi_report.xlsx"
    pdf_path = REPORTS_DIR / "executive_evaluation_summary.pdf"
    
    with col_excel:
        st.markdown("#### Classeur Excel Décisionnel (.xlsx)")
        st.write("Contient 4 onglets : Tableau de bord, Classement, Analyse des écarts et Télémétrie opérationnelle.")
        if excel_path.exists():
            with open(excel_path, "rb") as f:
                st.download_button(
                    label="📥 Télécharger talent_bi_report.xlsx",
                    data=f.read(),
                    file_name="talent_bi_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        else:
            st.warning("Fichier Excel non trouvé. Exécutez le pipeline au préalable.")

    with col_pdf:
        st.markdown("#### Dossier Synthèse Exécutif (.pdf)")
        st.write("Dossier publication ReportLab avec pagination courante, KPIs et fiches d'évaluation individuelles.")
        if pdf_path.exists():
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📥 Télécharger executive_evaluation_summary.pdf",
                    data=f.read(),
                    file_name="executive_evaluation_summary.pdf",
                    mime="application/pdf",
                )
        else:
            st.warning("Fichier PDF non trouvé. Exécutez le pipeline au préalable.")
