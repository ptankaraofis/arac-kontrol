import os
import re
import pandas as pd
import pdfplumber
import streamlit as st
from supabase import create_client

# 1. Sayfa Ayarları
st.set_page_config(
    page_title="Kurye Araç & Evrak Portalı", page_icon="🏍️", layout="wide"
)


# 2. Supabase Bağlantısı
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


# Yardımcı Fonksiyon: PDF İçinden Plaka Ayıklama
def pdf_icinden_plaka_oku(pdf_file) -> str | None:
    try:
        with pdfplumber.open(pdf_file) as pdf:
            tam_metin = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    tam_metin += text + "\n"

            # Türkiye plaka formatı regex (Örn: 06ABC123, 34 AB 1234 vb.)
            plaka_pattern = r"\b\d{2}\s?[A-Z]{1,3}\s?\d{2,4}\b"
            eslesmeler = re.findall(plaka_pattern, tam_metin)
            if eslesmeler:
                # İlk bulunan plakayı boşluksuz ve büyük harfle döndürür
                return eslesmeler[0].replace(" ", "").upper()
    except Exception:
        pass
    return None


st.title("🏍️ Kurye Araç Kontrol & Evrak Portalı")

# Sekmeler
tab1, tab2, tab3, tab4 = st.tabs([
    "📝 Tekli Araç / Evrak Kaydı",
    "📁 Toplu Evrak Yükle",
    "🔍 Plaka Sorgula",
    "📊 Toplu Bakım (Excel)",
])

# ---------------------------------------------------------
# SEKME 1: TEKLİ ARAÇ & EVRAK KAYDI
# ---------------------------------------------------------
with tab1:
    st.header("Tekli Araç / Evrak Yükleme")

    with st.form("single_vehicle_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            plate_input = (
                st.text_input("Plaka (Örn: 06ABC123)").strip().upper()
            )
            last_km = st.number_input("Son Bakım KM", min_value=0, step=1000)
        with col2:
            next_km = st.number_input(
                "Gelecek Bakım KM", min_value=0, step=1000
            )

        st.subheader("Evrak Yükleme (Opsiyonel)")
        col_doc1, col_doc2 = st.columns(2)
        with col_doc1:
            license_file = st.file_uploader(
                "Ruhsat Fotoğrafı (JPG/PNG)",
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
                license_url = None
                policy_url = None

                # Ruhsat Yükleme
                if license_file:
                    file_ext = license_file.name.split(".")[-1]
                    file_path = f"ruhsat/{plate_input}.{file_ext}"
                    try:
                        file_bytes = license_file.read()
                        supabase.storage.from_("documents").upload(
                            file_path,
                            file_bytes,
                            file_options={"upsert": "true"},
                        )
                        license_url = supabase.storage.from_(
                            "documents"
                        ).get_public_url(file_path)
                    except Exception as e:
                        st.error(f"Ruhsat yükleme hatası: {e}")

                # Poliçe Yükleme
                if policy_file:
                    file_path = f"police/{plate_input}.pdf"
                    try:
                        file_bytes = policy_file.read()
                        supabase.storage.from_("documents").upload(
                            file_path,
                            file_bytes,
                            file_options={"upsert": "true"},
                        )
                        policy_url = supabase.storage.from_(
                            "documents"
                        ).get_public_url(file_path)
                    except Exception as e:
                        st.error(f"Poliçe yükleme hatası: {e}")

                # Veritabanı Kaydı / Güncellemesi
                try:
                    data_to_upsert = {
                        "plate": plate_input,
                        "last_service_km": last_km,
                        "next_service_km": next_km,
                    }
                    if license_url:
                        data_to_upsert["license_img_url"] = license_url
                    if policy_url:
                        data_to_upsert["policy_pdf_url"] = policy_url

                    supabase.table("vehicles").upsert(
                        data_to_upsert, on_conflict="plate"
                    ).execute()
                    st.success(
                        f"{plate_input} plakalı araç bilgileri başarıyla"
                        " kaydedildi!"
                    )
                except Exception as e:
                    st.error(f"Veritabanı kayıt hatası: {e}")

# ---------------------------------------------------------
# SEKME 2: TOPLU EVRAK YÜKLEME (pdfplumber Entegre Edildi)
# ---------------------------------------------------------
with tab2:
    st.header("Toplu Evrak Yükleme")
    st.info(
        "💡 Poliçe PDF'lerinde plaka içeriğinden otomatik okunur. Ruhsat"
        " görsellerinin isimleri **Plaka** olmalıdır (Örn: `06ABC123.jpg`)."
    )

    doc_type = st.radio(
        "Yüklenecek Evrak Türü", ["Ruhsat Fotoğrafı (JPG/PNG)", "Poliçe (PDF)"]
    )
    uploaded_files = st.file_uploader(
        "Dosyaları Seçin veya Sürükleyin",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png"] if "Ruhsat" in doc_type else ["pdf"],
    )

    if st.button("Toplu Yüklemeyi Başlat"):
        if not uploaded_files:
            st.warning("Lütfen dosya seçiniz.")
        else:
            success_count = 0
            fail_count = 0

            for file in uploaded_files:
                try:
                    file_bytes = file.read()

                    if "Ruhsat" in doc_type:
                        plate_name = (
                            os.path.splitext(file.name)[0].strip().upper()
                        )
                        file_ext = file.name.split(".")[-1]
                        storage_path = f"ruhsat/{plate_name}.{file_ext}"

                        supabase.storage.from_("documents").upload(
                            storage_path,
                            file_bytes,
                            file_options={"upsert": "true"},
                        )
                        public_url = supabase.storage.from_(
                            "documents"
                        ).get_public_url(storage_path)
                        db_field = "license_img_url"

                    else:  # Poliçe PDF yüklemesi
                        # 1. pdfplumber ile PDF metnini okuyup plakayı arıyoruz
                        tespit_edilen_plaka = pdf_icinden_plaka_oku(file)

                        # İçerikte bulunamazsa dosya adına başvuruyoruz
                        if tespit_edilen_plaka:
                            plate_name = tespit_edilen_plaka
                        else:
                            plate_name = (
                                os.path.splitext(file.name)[0].strip().upper()
                            )

                        storage_path = f"police/{plate_name}.pdf"
                        supabase.storage.from_("documents").upload(
                            storage_path,
                            file_bytes,
                            file_options={"upsert": "true"},
                        )
                        public_url = supabase.storage.from_(
                            "documents"
                        ).get_public_url(storage_path)
                        db_field = "policy_pdf_url"

                    # Veritabanında güncelle veya oluştur
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

                    success_count += 1
                except Exception as e:
                    st.error(f"{file.name} yüklenirken hata oluştu: {e}")
                    fail_count += 1

            st.success(
                "İşlem Tamamlandı! Başarılı:"
                f" {success_count}, Hatalı: {fail_count}"
            )

# ---------------------------------------------------------
# SEKME 3: PLAKA SORGULAMA
# ---------------------------------------------------------
with tab3:
    st.header("Plaka ile Araç / Evrak Sorgula")
    search_plate = (
        st.text_input("Aranacak Plaka", key="search_input").strip().upper()
    )

    if st.button("Sorgula"):
        if not search_plate:
            st.warning("Lütfen bir plaka giriniz.")
        else:
            try:
                res = (
                    supabase.table("vehicles")
                    .select("*")
                    .eq("plate", search_plate)
                    .execute()
                )
                if res.data:
                    vehicle = res.data[0]
                    st.subheader(f"📋 Araç Detayları: {vehicle.get('plate')}")

                    col_info1, col_info2 = st.columns(2)
                    with col_info1:
                        st.metric(
                            "Son Bakım KM", vehicle.get("last_service_km", 0)
                        )
                    with col_info2:
                        st.metric(
                            "Gelecek Bakım KM", vehicle.get("next_service_km", 0)
                        )

                    st.markdown("---")
                    st.subheader("📄 Evraklar")

                    col_evrak1, col_evrak2 = st.columns(2)
                    with col_evrak1:
                        st.write("**Ruhsat Görseli:**")
                        if vehicle.get("license_img_url"):
                            st.image(
                                vehicle["license_img_url"],
                                use_container_width=True,
                            )
                            st.markdown(
                                "[📷 Ruhsatı Büyük Boyut"
                                f" Aç]({vehicle['license_img_url']})"
                            )
                        else:
                            st.info("Ruhsat görseli yüklenmemiş.")

                    with col_evrak2:
                        st.write("**Sigorta / Poliçe PDF:**")
                        if vehicle.get("policy_pdf_url"):
                            st.markdown(
                                "🔗 [📄 Poliçe PDF İndir /"
                                f" Görüntüle]({vehicle['policy_pdf_url']})"
                            )
                        else:
                            st.info("Poliçe PDF yüklenmemiş.")
                else:
                    st.warning(
                        f"'{search_plate}' plakasına ait kayıt bulunamadı."
                    )
            except Exception as e:
                st.error(f"Sorgulama sırasında hata oluştu: {e}")

# ---------------------------------------------------------
# SEKME 4: TOPLU BAKIM GÜNCELLEME (EXCEL)
# ---------------------------------------------------------
with tab4:
    st.header("Excel ile Toplu Bakım KM Güncelleme")
    st.info(
        "💡 Yükleyeceğiniz Excel dosyasında **Plaka**, **Son Bakım KM** ve"
        " **Gelecek Bakım KM** sütunları bulunmalıdır."
    )

    sample_data = {
        "Plaka": ["06ABC123", "34XYZ987"],
        "Son Bakım KM": [15000, 22000],
        "Gelecek Bakım KM": [20000, 27000],
    }
    df_sample = pd.DataFrame(sample_data)

    st.download_button(
        label="📥 Örnek Excel Şablonunu İndir (CSV)",
        data=df_sample.to_csv(index=False).encode("utf-8-sig"),
        file_name="ornek_bakim_tablosu.csv",
        mime="text/csv",
    )

    excel_file = st.file_uploader(
        "Excel Dosyası Yükleyin (.xlsx, .xls)", type=["xlsx", "xls"]
    )

    if excel_file:
        try:
            df = pd.read_excel(excel_file)
            st.write("📋 **Yüklenen Veri Önizlemesi:**")
            st.dataframe(df.head())

            col1, col2, col3 = st.columns(3)
            with col1:
                plate_col = st.selectbox(
                    "Plaka Sütunu",
                    df.columns,
                    index=0 if "Plaka" in df.columns else 0,
                )
            with col2:
                last_km_col = st.selectbox(
                    "Son Bakım KM Sütunu",
                    df.columns,
                    index=1 if "Son Bakım KM" in df.columns else 0,
                )
            with col3:
                next_km_col = st.selectbox(
                    "Gelecek Bakım KM Sütunu",
                    df.columns,
                    index=2 if "Gelecek Bakım KM" in df.columns else 0,
                )

            if st.button("Verileri Supabase'e Aktar"):
                success_count = 0
                fail_count = 0

                for _, row in df.iterrows():
                    plate = str(row[plate_col]).strip().upper()

                    if not plate or plate == "NAN":
                        continue

                    try:
                        last_km = (
                            int(row[last_km_col])
                            if pd.notnull(row[last_km_col])
                            else 0
                        )
                        next_km = (
                            int(row[next_km_col])
                            if pd.notnull(row[next_km_col])
                            else 0
                        )
                    except ValueError:
                        last_km = 0
                        next_km = 0

                    data_to_upsert = {
                        "plate": plate,
                        "last_service_km": last_km,
                        "next_service_km": next_km,
                    }

                    try:
                        supabase.table("vehicles").upsert(
                            data_to_upsert, on_conflict="plate"
                        ).execute()
                        success_count += 1
                    except Exception as e:
                        st.error(f"{plate} güncellenirken hata: {e}")
                        fail_count += 1

                st.success(
                    "İşlem Tamamlandı! Başarılı Güncellenen:"
                    f" {success_count}, Hatalı: {fail_count}"
                )

        except Exception as e:
            st.error(f"Excel okunurken hata oluştu: {e}")
