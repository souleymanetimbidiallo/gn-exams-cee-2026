# Explorer CEE 2026

Place `CEE-2026.xlsx` dans ce dossier, puis lance :

```bash
pip install -r requirements.txt
rm -f cee_2026.parquet
streamlit run app.py
```

La correction importante est `header=1`, car la première ligne Excel contient le titre du document, pas les noms des colonnes.

---

Les 5 que je développerais en priorité pour avoir un projet impressionnant :

🤖 Assistant IA qui répond aux questions
