import io
import os
import re
import pandas as pd
import pdfplumber
import streamlit as st
from supabase import create_client

# Sayfa Ayarları
st.set_page_config(
    page_title="Kurye Araç & Evrak Portalı", page_icon="🏍️", layout="wide"
)


# Supabase Bağlantısı
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"].strip()
    key = st.secrets["SUPABASE_KEY"].strip()
    return create_client(url, key)


try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Supabase bağlantısı başlatılamadı: {e}")
    st.stop()


# Güvenli PDF Plaka Okuma Fonksiyonu
def pdf_icinden_plaka_oku(pdf_bytes: bytes) -> str | None:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            tam_metin = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    tam_metin += text + "\n"

            # Plaka Regex
            plaka_pattern = r"\b\d{2}\s?[A-Z]{1,3}\s?\d{2,4}\b"
            eslesmeler = re.findall(plaka_pattern, tam_metin)
            if eslesmeler:
                return eslesmeler[0].replace(" ", "").upper()
    except Exception as e:
        st.write(f"PDF Okuma Uyarısı: {e}")
    return None


st.title("🏍️ Kurye Araç Kontrol & Evrak Portalı")

tab1, tab2, tab3, tab4 = st.tabs([
    "📝 Tekli Araç / Evrak Kaydı",
    "📁 Toplu Evrak Yükle",
    "🔍 Plaka Sorgula",
    "📊 Toplu Bakım (Excel)",
])

# ---------------------------------------------------------
# SEKME 1: TEKLİ KAYIT
# ---------------------------------------------------------
with tab1:
    st.header("Tekli Araç / Evrak Yükleme")
    with st.form("single_vehicle_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            plate_input = (
                st.text_input("Plaka (Örn: 34AVA411)").strip().upper()
            )
            last_km = st.number_input("Son Bakım KM", min_value=0, step=1000)
        with col2:
            next_km = st.number_input(
                "Gelecek Bakım KM", min_value=0, step=1000
            )

        col_doc1, col_doc2 = st.columns(2)
        with col_doc1:
            license_file = st.file_uploader(
                "Ruhsat Görseli",
                type=["jpg", "jpeg", "png"],
                key="single_license",
            )
        with col_doc2:
            policy_file = st.file_uploader(
                "Poliçe PDF", type=["pdf"], key="single_policy"
            )

        submitted = st.form_submit_button("Kaydet / Güncelle")

        if submitted:
            if not plate_input:
                st.warning("Lütfen plaka giriniz!")
            else:
                license_url, policy_url = None, None

                # Ruhsat Yükleme
                if license_file:
                    ext = license_file.name.split(".")[-1].lower()
                    path = f"ruhsat/{plate_input}.{ext}"
                    try:
                        file_bytes = license_file.getvalue()
                        supabase.storage.from_("documents").upload(
                            path,
                            file_bytes,
                            file_options={
                                "upsert": "true",
                                "content-type": f"image/{ext}",
                            },
                        )
                        license_url = supabase.storage.from_(
                            "documents"
                        ).get_public_url(path)
                    except Exception as e:
                        st.error(f"Ruhsat yükleme hatası: {e}")

                # Poliçe PDF Yükleme
                if policy_file:
                    path = f"police/{plate_input}.pdf"
                    try:
                        file_bytes = policy_file.getvalue()
                        supabase.storage.from_("documents").upload(
                            path,
                            file_bytes,
                            file_options={
                                "upsert": "true",
                                "content-type": "application/pdf",
                            },
                        )
                        policy_url = supabase.storage.from_(
                            "documents"
                        ).get_public_url(path)
                    except Exception as e:
                        st.error(f"Poliçe yükleme hatası: {e}")

                # Veritabanı Upsert
                try:
                    payload = {
                        "plate": plate_input,
                        "last_service_km": last_km,
                        "next_service_km": next_km,
                    }
                    if license_url:
                        payload["license_img_url"] = license_url
                    if policy_url:
                        payload["policy_pdf_url"] = policy_url

                    supabase.table("vehicles").upsert(
                        payload, on_conflict="plate"
                    ).execute()
                    st.success(f"{plate_input} başarıyla kaydedildi!")
                except Exception as e:
                    st.error(f"Veritabanı kayıt hatası: {e}")

# ---------------------------------------------------------
# SEKME 2: TOPLU EVRAK YÜKLEME
# ---------------------------------------------------------
with tab2:
    st.header("Toplu Evrak Yükleme")
    doc_type = st.radio(
        "Evrak Türü", ["Ruhsat Fotoğrafı (JPG/PNG)", "Poliçe (PDF)"]
    )
    uploaded_files = st.file_uploader(
        "Dosyaları Seçin",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png"] if "Ruhsat" in doc_type else ["pdf"],
    )

    if st.button("Toplu Yüklemeyi Başlat"):
        if not uploaded_files:
            st.warning("Dosya seçilmedi!")
        else:
            success, fail = 0, 0
            for file in uploaded_files:
                try:
                    # Streamlit dosya içeriğini tam bayt olarak alıyoruz (.getvalue())
                    file_bytes = file.getvalue()

                    if "Ruhsat" in doc_type:
                        plate_name = (
                            os.path.splitext(file.name)[0].strip().upper()
                        )
                        ext = file.name.split(".")[-1].lower()
                        storage_path = f"ruhsat/{plate_name}.{ext}"
                        db_field = "license_img_url"
                        content_type = f"image/{ext}"
                    else:
                        tespit = pdf_icinden_plaka_oku(file_bytes)
                        plate_name = (
                            tespit
                            if tespit
                            else os.path.splitext(file.name)[0].strip().upper()
                        )
                        storage_path = f"police/{plate_name}.pdf"
                        db_field = "policy_pdf_url"
                        content_type = "application/pdf"

                    # Supabase Storage'a Yükle
                    supabase.storage.from_("documents").upload(
                        storage_path,
                        file_bytes,
                        file_options={
                            "upsert": "true",
                            "content-type": content_type,
                        },
                    )
                    public_url = supabase.storage.from_(
                        "documents"
                    ).get_public_url(storage_path)

                    # DB Güncelleme
                    res = (
                        supabase.table("vehicles")
                        .select("*")
                        .eq("plate", plate_name)
                        .execute()
                    )
                    if res.data:
                        supabase.table("vehicles").update(
                            {db_field: public_url}
                        ).eq("plate", plate_name).execute()
                    else:
                        supabase.table("vehicles").insert(
                            {"plate": plate_name, db_field: public_url}
                        ).execute()
                    success += 1
                except Exception as e:
                    st.error(f"{file.name} yüklenemedi: {e}")
                    fail += 1
            st.success(
                f"Tamamlandı! Başarılı: {success}, Hatalı: {fail}"
            )

# ---------------------------------------------------------
# SEKME 3: SORGULAMA
# ---------------------------------------------------------
with tab3:
    st.header("Plaka Sorgula")
    search_plate = (
        st.text_input("Aranacak Plaka", key="search_input").strip().upper()
    )
    if st.button("Sorgula"):
        if search_plate:
            res = (
                supabase.table("vehicles")
                .select("*")
                .eq("plate", search_plate)
                .execute()
            )
            if res.data:
                v = res.data[0]
                st.subheader(f"📋 {v.get('plate')}")
                c1, c2 = st.columns(2)
                c1.metric("Son Bakım KM", v.get("last_service_km", 0))
                c2.metric("Gelecek Bakım KM", v.get("next_service_km", 0))

                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    if v.get("license_img_url"):
                        st.image(
                            v["license_img_url"], use_container_width=True
                        )
                    else:
                        st.info("Ruhsat yok.")
                with col_e2:
                    if v.get("policy_pdf_url"):
                        st.markdown(
                            f"[📄 Poliçe PDF Aç / İndir]({v['policy_pdf_url']})"
                        )
                    else:
                        st.info("Poliçe yok.")
            else:
                st.warning("Kayıt bulunamadı.")

# ---------------------------------------------------------
# SEKME 4: EXCEL BAKIM
# ---------------------------------------------------------
with tab4:
    st.header("Toplu Bakım Güncelle (Excel)")
    excel_file = st.file_uploader("Excel Seç", type=["xlsx", "xls"])
    if excel_file:
        df = pd.read_excel(excel_file)
        st.dataframe(df.head())
        if st.button("Verileri Aktar"):
            for _, row in df.iterrows():
                try:
                    p = str(row["Plaka"]).strip().upper()
                    l_km = int(row["Son Bakım KM"])
                    n_km = int(row["Gelecek Bakım KM"])
                    supabase.table("vehicles").upsert(
                        {
                            "plate": p,
                            "last_service_km": l_km,
                            "next_service_km": n_km,
                        },
                        on_conflict="plate",
                    ).execute()
                except Exception:
                    pass
            st.success("Bakım verileri güncellendi.")
