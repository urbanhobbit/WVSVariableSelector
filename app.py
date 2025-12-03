import streamlit as st
import pandas as pd
import io
import re
import os

# -----------------------------------------------------------------------------
# 1. AYARLAR VE BAŞLIK
# -----------------------------------------------------------------------------
st.set_page_config(page_title="EVS/WVS Analiz Platformu", layout="wide", page_icon="🌍")
st.title("🌍 EVS & WVS: Analiz Platformu")
st.markdown("""
Bu araçla verileri analiz edebilir, seçtiğiniz soruları **Excel projesi** olarak kaydedip 
daha sonra kaldığınız yerden devam edebilirsiniz.
""")

# -----------------------------------------------------------------------------
# 2. HAFIZA (SESSION STATE)
# -----------------------------------------------------------------------------
if 'project_data' not in st.session_state:
    st.session_state['project_data'] = {}

# -----------------------------------------------------------------------------
# 3. VERİ YÜKLEME (AKILLI DOSYA KONTROLÜ)
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_robust():
    # 1. Ana Excel Dosyası İsimleri (Olasılıklar)
    excel_candidates = [
        'Country_Questions_Table v02..xlsx',
        'Country_Questions_Table.xlsx'
    ]
    
    # 2. Metadata (Soru) Dosyası İsimleri (Olasılıklar)
    meta_candidates = [
        'questions.csv',
        'normalized_evsvws_catalog_THEMED_UNIFIED.xlsx - questions.csv'
    ]

    # --- Dosyaları Bulma Mantığı ---
    excel_file = next((f for f in excel_candidates if os.path.exists(f)), None)
    meta_file = next((f for f in meta_candidates if os.path.exists(f)), None)

    if not excel_file:
        return None, None, f"Ana Excel dosyası bulunamadı. Beklenen isimler: {excel_candidates}"
    
    if not meta_file:
        return None, None, f"Soru listesi (CSV) bulunamadı. Beklenen isimler: {meta_candidates}"

    try:
        # A. Excel'i Oku
        xl = pd.ExcelFile(excel_file)
        sheet_names = xl.sheet_names
        # 'Survey' içeren sayfayı bul
        survey_sheet = next((s for s in sheet_names if "Survey" in s), None)
        
        if survey_sheet:
            df = pd.read_excel(excel_file, sheet_name=survey_sheet)
        else:
            return None, None, "Excel dosyasında 'Survey' sayfası bulunamadı."
        
        # B. Metadata'yı Oku
        meta = pd.read_csv(meta_file)
        # Gerekli sütunlar var mı kontrol et
        required_cols = {'question_code', 'question_name', 'theme'}
        if not required_cols.issubset(meta.columns):
             return None, None, f"CSV dosyasında gerekli sütunlar eksik: {required_cols}"

        meta = meta[['question_code', 'question_name', 'theme']].drop_duplicates()
        
        return df, meta, None

    except Exception as e:
        return None, None, f"Dosya okunurken hata oluştu: {str(e)}"

# Veriyi Yükle
df_main, df_meta, error_msg = load_data_robust()

if error_msg:
    st.error(f"❌ {error_msg}")
    st.info("Lütfen Excel ve CSV dosyalarının app.py ile aynı klasörde olduğundan emin olun.")
    st.stop()

# Veri İşleme: S021 Sütunundan Ülke/Yıl Ayırma
try:
    if 'Country_Name' not in df_main.columns:
        extracted = df_main['S021'].astype(str).str.extract(r'^(.*)\s\[(\d{4})\]$')
        df_main['Country_Name'] = extracted[0].str.strip()
        df_main['Year'] = extracted[1]
except Exception as e:
    st.warning("Veri formatı uyarısı: Tarih sütunu (S021) tam ayrıştırılamadı.")

# -----------------------------------------------------------------------------
# 4. KENAR ÇUBUĞU (AYARLAR)
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Proje Ayarları")

# A. PROJE YÜKLEME
uploaded_project = st.sidebar.file_uploader("📂 Eski çalışmayı (.xlsx) yükle", type=['xlsx'])
if uploaded_project:
    try:
        project_xl = pd.ExcelFile(uploaded_project)
        for sheet in project_xl.sheet_names:
            if sheet == 'PROJE_BILGI': continue
            df_sheet = pd.read_excel(uploaded_project, sheet_name=sheet)
            # 'Kod' sütunu varsa o sayfadaki soru kodlarını al
            if 'Kod' in df_sheet.columns:
                st.session_state['project_data'][sheet] = df_sheet['Kod'].astype(str).tolist()
        st.sidebar.success("✅ Proje geri yüklendi!")
    except Exception as e:
        st.sidebar.error(f"Proje dosyası okunamadı: {e}")

st.sidebar.divider()

# B. ÜLKE SEÇİMİ
all_countries = sorted(df_main['Country_Name'].dropna().unique())
desired_defaults = ["Bulgaria", "Croatia", "Finland", "Sweden"]
# Hata almamak için sadece mevcut olanları varsayılan yap
default_defaults = [c for c in desired_defaults if c in all_countries]

selected_countries = st.sidebar.multiselect("Ülkeler:", all_countries, default=default_defaults)

if not selected_countries:
    st.warning("Analiz için lütfen en az bir ülke seçin.")
    st.stop()

# C. TEMA SEÇİMİ
all_themes = sorted([str(x) for x in df_meta['theme'].unique() if pd.notna(x)])
selected_theme = st.sidebar.selectbox("Konu Başlığı (Theme):", all_themes)

# -----------------------------------------------------------------------------
# 5. ANA EKRAN (SEÇİM VE TABLO)
# -----------------------------------------------------------------------------
st.divider()

# Seçilen temanın sorularını getir
theme_questions = df_meta[df_meta['theme'] == selected_theme]
# Sadece Excel'de sütun olarak var olan soruları al (Verisi olanlar)
available_q_codes = [q for q in theme_questions['question_code'] if q in df_main.columns]

if not available_q_codes:
    st.info(f"'{selected_theme}' teması için veri setinde soru bulunamadı.")
    st.stop()

format_dict = dict(zip(theme_questions.question_code, theme_questions.question_name))

# --- HAFIZA MANTIĞI ---
# Eğer bu tema için daha önce bir seçim yapılmamışsa, varsayılan olarak HEPSİNİ seç.
if selected_theme not in st.session_state['project_data']:
    st.session_state['project_data'][selected_theme] = available_q_codes

# Geçerli seçim listesi
current_selection = st.session_state['project_data'][selected_theme]

# EKRAN DÜZENİ: SOL (LİSTE) - SAĞ (SONUÇ)
col_left, col_right = st.columns([4, 6], gap="medium")

# === SOL: İNTERAKTİF SEÇİM TABLOSU ===
with col_left:
    st.subheader("1. Soruları Seç")
    
    # Hızlı İşlem Butonları
    btn_col1, btn_col2 = st.columns(2)
    if btn_col1.button("✅ Hepsini Seç", key=f"all_{selected_theme}", use_container_width=True):
        st.session_state['project_data'][selected_theme] = available_q_codes
        st.rerun()
        
    if btn_col2.button("🗑️ Temizle", key=f"clear_{selected_theme}", use_container_width=True):
        st.session_state['project_data'][selected_theme] = []
        st.rerun()

    # Editör için veri hazırlığı
    editor_data = []
    for code in available_q_codes:
        editor_data.append({
            "Seç": code in current_selection,
            "Kod": code,
            "Soru": format_dict.get(code, "")
        })
    
    df_editor = pd.DataFrame(editor_data)

    # Data Editor
    edited_df = st.data_editor(
        df_editor,
        column_config={
            "Seç": st.column_config.CheckboxColumn("Durum", width="small"),
            "Kod": st.column_config.TextColumn("Kod", disabled=True, width="small"),
            "Soru": st.column_config.TextColumn("Soru", disabled=True, width="large"),
        },
        disabled=["Kod", "Soru"],
        hide_index=True,
        use_container_width=True,
        height=500,
        key=f"editor_{selected_theme}" # Her tema için benzersiz key
    )

    # Tablodaki değişiklikleri anında kaydet
    new_selection = edited_df[edited_df["Seç"] == True]["Kod"].tolist()
    st.session_state['project_data'][selected_theme] = new_selection

# === SAĞ: ANALİZ SONUCU ===
with col_right:
    st.subheader("2. Analiz Sonucu")
    
    display_codes = st.session_state['project_data'][selected_theme]
    
    if display_codes:
        st.caption(f"Seçili **{len(display_codes)}** soru gösteriliyor.")
        
        results = []
        # Filtreleme (Hız için döngü dışında)
        filtered_df = df_main[df_main['Country_Name'].isin(selected_countries)]
        
        with st.spinner('Tablo oluşturuluyor...'):
            for q_code in display_codes:
                row = {"Kod": q_code, "Soru": format_dict.get(q_code, "-")}
                for country in selected_countries:
                    c_dat = filtered_df[filtered_df['Country_Name'] == country]
                    # 'VAR' olan yılları bul
                    years = c_dat[c_dat[q_code] == 'VAR']['Year'].dropna().unique()
                    row[country] = ", ".join(sorted(years)) if len(years) > 0 else "-"
                results.append(row)
        
        st.dataframe(pd.DataFrame(results), use_container_width=True, height=500, hide_index=True)
    
    else:
        st.warning("⚠️ Şu an hiçbir soru seçili değil.")
        st.info("Listeden soru seçerek analize başlayabilirsiniz.")

# -----------------------------------------------------------------------------
# 6. İNDİRME BÖLÜMÜ (MASTER EXCEL)
# -----------------------------------------------------------------------------
st.divider()

# Aktif (dolu) temaları bul
active_themes = {k: v for k, v in st.session_state['project_data'].items() if v}

c1, c2 = st.columns([3, 1])

with c1:
    if active_themes:
        st.success(f"Toplam **{len(active_themes)} farklı tema** projenize dahil edildi.")
    else:
        st.info("İndirilecek veri yok. Lütfen sorulardan seçim yapın.")

with c2:
    if active_themes:
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        
        # 1. Bilgi Sayfası
        pd.DataFrame({'Seçili Ülkeler': selected_countries}).to_excel(writer, sheet_name='PROJE_BILGI', index=False)
        
        # 2. Tema Sayfaları
        for theme, codes in active_themes.items():
            sheet_data = []
            filtered_df = df_main[df_main['Country_Name'].isin(selected_countries)]
            
            for q in codes:
                q_name = format_dict.get(q, "-")
                row = {"Kod": q, "Soru": q_name}
                for c in selected_countries:
                    c_dat = filtered_df[filtered_df['Country_Name'] == c]
                    years = c_dat[c_dat[q] == 'VAR']['Year'].dropna().unique()
                    row[c] = ", ".join(sorted(years)) if len(years) > 0 else "-"
                sheet_data.append(row)
            
            # Excel sayfa adı temizliği
            safe_name = re.sub(r'[\\/*?:\[\]]', '', theme)[:30]
            pd.DataFrame(sheet_data).to_excel(writer, sheet_name=safe_name, index=False)
        
        writer.close()
        
        st.download_button(
            label="💾 Projeyi İndir (Excel)",
            data=output.getvalue(),
            file_name="EVS_WVS_Proje.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )