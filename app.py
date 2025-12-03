import streamlit as st
import pandas as pd
import io
import re
import os

# -----------------------------------------------------------------------------
# 1. AYARLAR
# -----------------------------------------------------------------------------
st.set_page_config(page_title="EVS/WVS Analiz Platformu", layout="wide", page_icon="🌍")
st.title("🌍 EVS & WVS: Analiz Platformu")
st.markdown("""
**Kullanım:** Kutucukları işaretlediğinizde seçimleriniz anında kaydedilir. 
İşiniz bitince sol menüden **'Projeyi Kaydet'** butonuna basarak Excel alabilirsiniz.
""")

DEFAULT_PROJECT_FILE = "baslangic_projesi.xlsx"

# -----------------------------------------------------------------------------
# 2. YARDIMCI FONKSİYONLAR
# -----------------------------------------------------------------------------
def clean_sheet_name(name):
    safe = re.sub(r'[\\/*?:\[\]]', '', str(name))
    return safe[:30]

# --- CALLBACK FONKSİYONU (SORUNU ÇÖZEN KISIM) ---
def update_selection_state(key_name, theme_name):
    """
    Kullanıcı tabloya tıkladığı AN (sayfa yenilenmeden önce) bu fonksiyon çalışır.
    Tablonun son halini alır ve hafızaya kaydeder.
    """
    # Tablonun o anki halini al
    edited_data = st.session_state[key_name]
    
    # Sadece seçili olanların kodlarını filtrele
    # edited_data bir DataFrame olarak gelir
    selected_codes = edited_data[edited_data["Seç"] == True]["Kod"].tolist()
    
    # Ana hafızayı güncelle
    st.session_state['project_data'][theme_name] = selected_codes

# -----------------------------------------------------------------------------
# 3. VERİ YÜKLEME
# -----------------------------------------------------------------------------
if 'project_data' not in st.session_state:
    st.session_state['project_data'] = {}

@st.cache_data
def load_data_robust():
    excel_candidates = ['Country_Questions_Table v02..xlsx', 'Country_Questions_Table.xlsx']
    meta_candidates = ['questions.csv', 'normalized_evsvws_catalog_THEMED_UNIFIED.xlsx - questions.csv']

    excel_file = next((f for f in excel_candidates if os.path.exists(f)), None)
    meta_file = next((f for f in meta_candidates if os.path.exists(f)), None)

    if not excel_file: return None, None, "Ana Excel dosyası bulunamadı."
    if not meta_file: return None, None, "Soru listesi (CSV) bulunamadı."

    try:
        xl = pd.ExcelFile(excel_file)
        sheet_names = xl.sheet_names
        survey_sheet = next((s for s in sheet_names if "Survey" in s), None)
        if survey_sheet:
            df = pd.read_excel(excel_file, sheet_name=survey_sheet)
        else:
            return None, None, "Excel dosyasında 'Survey' sayfası bulunamadı."
        
        meta = pd.read_csv(meta_file)
        meta = meta[['question_code', 'question_name', 'theme']].drop_duplicates()
        return df, meta, None
    except Exception as e:
        return None, None, str(e)

df_main, df_meta, error_msg = load_data_robust()

if error_msg:
    st.error(error_msg)
    st.stop()

# S021 Ayrıştırma
try:
    if 'Country_Name' not in df_main.columns:
        extracted = df_main['S021'].astype(str).str.extract(r'^(.*)\s\[(\d{4})\]$')
        df_main['Country_Name'] = extracted[0].str.strip()
        df_main['Year'] = extracted[1]
except: pass

# Listeleri Hazırla
all_countries = sorted(df_main['Country_Name'].dropna().unique())
all_themes = sorted([str(x) for x in df_meta['theme'].unique() if pd.notna(x)])

# -----------------------------------------------------------------------------
# 4. BAŞLANGIÇTA HER ŞEYİ SEÇME
# -----------------------------------------------------------------------------
if 'initialized' not in st.session_state:
    # Sadece ilk açılışta çalışır
    with st.spinner('Proje başlatılıyor...'):
        for theme in all_themes:
            t_qs = df_meta[df_meta['theme'] == theme]
            valid_codes = [q for q in t_qs['question_code'] if q in df_main.columns]
            if valid_codes:
                st.session_state['project_data'][theme] = valid_codes
    st.session_state['initialized'] = True

# -----------------------------------------------------------------------------
# 5. KENAR ÇUBUĞU
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Proje İşlemleri")

# --- A. PROJE YÜKLEME ---
uploaded_project = st.sidebar.file_uploader("📂 Eski çalışmayı yükle", type=['xlsx'])
if uploaded_project:
    try:
        project_xl = pd.ExcelFile(uploaded_project)
        # Ülkeler
        if 'PROJE_BILGI' in project_xl.sheet_names:
            df_info = pd.read_excel(uploaded_project, sheet_name='PROJE_BILGI')
            if 'Seçili Ülkeler' in df_info.columns:
                saved_cs = df_info['Seçili Ülkeler'].dropna().tolist()
                valid_cs = [c for c in saved_cs if c in all_countries]
                if valid_cs: st.session_state['selected_countries_key'] = valid_cs
        
        # Temalar
        theme_map = {clean_sheet_name(t): t for t in all_themes}
        count = 0
        for sheet in project_xl.sheet_names:
            if sheet == 'PROJE_BILGI': continue
            matched = theme_map.get(sheet)
            if not matched and sheet in all_themes: matched = sheet
            if matched:
                df_sh = pd.read_excel(uploaded_project, sheet_name=sheet)
                if 'Kod' in df_sh.columns:
                    st.session_state['project_data'][matched] = df_sh['Kod'].astype(str).tolist()
                    count += 1
        st.sidebar.success(f"{count} tema yüklendi!")
    except Exception as e:
        st.sidebar.error(f"Hata: {e}")

st.sidebar.divider()

# --- B. KAYDETME BUTONU ---
st.sidebar.subheader("💾 Projeyi Kaydet")
active_themes = {k: v for k, v in st.session_state['project_data'].items() if v}

if active_themes:
    current_countries = st.session_state.get('selected_countries_key', ["Bulgaria", "Croatia", "Finland", "Sweden"])
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    # 1. Bilgi
    pd.DataFrame({'Seçili Ülkeler': current_countries}).to_excel(writer, sheet_name='PROJE_BILGI', index=False)
    
    # 2. Temalar
    for theme, codes in active_themes.items():
        sheet_data = []
        for q in codes:
            q_name = df_meta[df_meta['question_code'] == q]['question_name'].values[0] if not df_meta[df_meta['question_code'] == q].empty else "-"
            row = {"Kod": q, "Soru": q_name}
            # Analiz verisini ekle
            filtered_df = df_main[df_main['Country_Name'].isin(current_countries)]
            for c in current_countries:
                c_dat = filtered_df[filtered_df['Country_Name'] == c]
                years = c_dat[c_dat[q] == 'VAR']['Year'].dropna().unique()
                row[c] = ", ".join(sorted(years)) if len(years)>0 else "-"
            sheet_data.append(row)
        pd.DataFrame(sheet_data).to_excel(writer, sheet_name=clean_sheet_name(theme), index=False)
    
    writer.close()
    st.sidebar.download_button(
        "📥 Excel Olarak İndir", 
        output.getvalue(), 
        "EVS_WVS_Projem.xlsx", 
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
        type="primary"
    )
else:
    st.sidebar.warning("Henüz veri yok.")

st.sidebar.divider()

# --- C. FİLTRELER ---
if 'selected_countries_key' not in st.session_state:
    st.session_state['selected_countries_key'] = ["Bulgaria", "Croatia", "Finland", "Sweden"]

selected_countries = st.sidebar.multiselect("Ülkeler:", all_countries, key='selected_countries_key')
selected_theme = st.sidebar.selectbox("Konu Başlığı:", all_themes)

if not selected_countries: st.stop()

# -----------------------------------------------------------------------------
# 6. ANA EKRAN
# -----------------------------------------------------------------------------
st.divider()

theme_questions = df_meta[df_meta['theme'] == selected_theme]
available_q_codes = [q for q in theme_questions['question_code'] if q in df_main.columns]
format_dict = dict(zip(theme_questions.question_code, theme_questions.question_name))

if not available_q_codes:
    st.info("Bu tema için veri yok.")
    st.stop()

# Hafızadan Durumu Al
current_selection = st.session_state['project_data'].get(selected_theme, [])

col_left, col_right = st.columns([4, 6], gap="medium")

with col_left:
    st.subheader(f"1. Düzenle: {selected_theme}")
    
    # Butonlar
    c1, c2 = st.columns(2)
    if c1.button("Hepsini Geri Getir", key="all"):
        st.session_state['project_data'][selected_theme] = available_q_codes
        st.rerun()
    if c2.button("Bu Temayı Boşalt", key="clr"):
        st.session_state['project_data'][selected_theme] = []
        st.rerun()

    # Data Editor Verisi Hazırla
    editor_data = []
    for code in available_q_codes:
        editor_data.append({
            "Seç": code in current_selection,
            "Kod": code,
            "Soru": format_dict.get(code, "")
        })
    
    # Unique Key oluştur (Tema adı değişince tablo sıfırlansın)
    editor_key = f"editor_{selected_theme}"

    # --- KRİTİK DÜZELTME: ON_CHANGE KULLANIMI ---
    edited_df = st.data_editor(
        pd.DataFrame(editor_data),
        column_config={
            "Seç": st.column_config.CheckboxColumn("Durum", width="small"),
            "Kod": st.column_config.TextColumn("Kod", disabled=True, width="small"),
            "Soru": st.column_config.TextColumn("Soru", disabled=True, width="large"),
        },
        disabled=["Kod", "Soru"], 
        hide_index=True, 
        use_container_width=True, 
        height=600,
        key=editor_key,
        # Callback burada devreye giriyor!
        on_change=update_selection_state,
        args=(editor_key, selected_theme)
    )

with col_right:
    st.subheader("2. Analiz Önizleme")
    
    # Veriyi direkt hafızadan oku (Callback sayesinde günceldir)
    display_codes = st.session_state['project_data'].get(selected_theme, [])
    
    if display_codes:
        st.caption(f"Bu temada **{len(display_codes)}** soru aktif.")
        results = []
        filtered_df = df_main[df_main['Country_Name'].isin(selected_countries)]
        
        with st.spinner('Tablo güncelleniyor...'):
            for q in display_codes:
                row = {"Kod": q, "Soru": format_dict.get(q, "-")}
                for c in selected_countries:
                    c_dat = filtered_df[filtered_df['Country_Name'] == c]
                    years = c_dat[c_dat[q] == 'VAR']['Year'].dropna().unique()
                    row[c] = ", ".join(sorted(years)) if len(years)>0 else "-"
                results.append(row)
        
        st.dataframe(pd.DataFrame(results), use_container_width=True, height=600, hide_index=True)
    else:
        st.warning("Bu tema için tüm soruları kaldırdınız (Boş).")