import streamlit as st
import os
from supabase import create_client

# 1. Sayfa Ayarları
st.set_page_config(page_title="Kurye Araç & Evrak Portalı", page_icon="🏍️", layout="wide")

# 2. Supabase Bağlantısı (Bilgileri secrets üzerinden alır)
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

st.title("🏍️ Kurye Araç Kontrol Portalı")

# Sekmeler
tab_search, tab_admin, tab_bulk = st.tabs([
    "🔍 Plaka Sorgula", 
    "➕ Tekli Araç / Evrak Yükle", 
    "📁 Toplu Evrak Yükle"
])

# ==========================================
# 1. PLAKA SORGULAMA SEKMESİ
# ==========================================
with tab_search:
    st.subheader("Plaka ile Evrak ve Bakım Sorgulama")
    
    # Plaka girdisini temizle (boşlukları sil, büyük harfe çevir)
    search_input = st.text_input("Plaka Giriniz:", placeholder="Örn: 34ABC123").strip().replace(" ", "").upper()
    
    if st.button("Sorgula", type="primary", use_container_width=True):
        if search_input:
            # Supabase'den plaka sorgusu
            res = supabase.table("vehicles").select("*").eq("plate", search_input).execute()
            
            if res.data:
                vehicle = res.data[0]
                st.success(f"✅ **{search_input}** plakalı araç sisteme kayıtlı.")
                
                st.divider()
                
                # Bakım Bilgileri Gösterimi
                st.markdown("### 🛠️ Bakım Bilgileri")
                col_km1, col_km2 = st.columns(2)
                
                last_km = vehicle.get('last_service_km') or 0
                next_km = vehicle.get('next_service_km') or 0
                
                col_km1.metric("Son Bakım KM", f"{last_km:,} km")
                col_km2.metric("Bir Sonraki Bakım KM", f"{next_km:,} km")
                
                st.divider()
                
                # Evrak Gösterim Alanı
                st.markdown("### 📂 Araç Evrakları")
                col_pdf, col_img = st.columns(2)
                
                with col_pdf:
                    st.subheader("📄 Sigorta Poliçesi")
                    pdf_url = vehicle.get("policy_pdf_url")
                    if pdf_url:
                        st.link_button("🌐 Poliçe PDF'ini Aç / İndir", pdf_url, use_container_width=True)
                    else:
                        st.info("Bu araca ait yüklü poliçe bulunamadı.")
                        
                with col_img:
                    st.subheader("🪪 Ruhsat Görseli")
                    img_url = vehicle.get("license_img_url")
                    if img_url:
                        st.image(img_url, caption=f"{search_input} Ruhsat Görseli", use_container_width=True)
                    else:
                        st.info("Bu araca ait yüklü ruhsat fotoğrafı bulunamadı.")
            else:
                st.error("❌ Bu plakaya ait sistemde kayıt bulunamadı.")
        else:
            st.warning("Lütfen bir plaka girin.")

# ==========================================
# 2. TEKLİ VERİ VE EVRAK YÜKLEME SEKMESİ
# ==========================================
with tab_admin:
    st.subheader("Sisteme Tekli Araç veya Evrak Tanımla")
    st.caption("Not: Aynı plakayı tekrar girerseniz mevcut bilgiler ve dosyalar güncellenir.")
    
    with st.form("vehicle_form", clear_on_submit=True):
        plate = st.text_input("Plaka (Zorunlu)").strip().replace(" ", "").upper()
        
        col_a, col_b = st.columns(2)
        with col_a:
            last_service_km = st.number_input("Son Bakım KM", min_value=0, step=500, value=0)
        with col_b:
            next_service_km = st.number_input("Gelecek Bakım KM", min_value=0, step=500, value=0)
            
        pdf_file = st.file_uploader("Sigorta Poliçesi Yükle (PDF)", type=["pdf"])
        img_file = st.file_uploader("Ruhsat Görseli Yükle (JPG, PNG)", type=["jpg", "jpeg", "png"])
        
        submit_btn = st.form_submit_button("Sisteme Kaydet", type="primary")
        
        if submit_btn:
            if not plate:
                st.error("Plaka alanı boş bırakılamaz!")
            else:
                with st.spinner("Dosyalar ve bilgiler işleniyor..."):
                    # Mevcut veriyi çek (eski URL'leri korumak için)
                    existing_res = supabase.table("vehicles").select("*").eq("plate", plate).execute()
                    existing_data = existing_res.data[0] if existing_res.data else {}
                    
                    pdf_url = existing_data.get("policy_pdf_url", "")
                    img_url = existing_data.get("license_img_url", "")
                    
                    # 1. PDF Yükleme
                    if pdf_file is not None:
                        pdf_path = f"policies/{plate}.pdf"
                        supabase.storage.from_("documents").upload(
                            path=pdf_path,
                            file=pdf_file.getvalue(),
                            file_options={"content-type": "application/pdf", "upsert": "true"}
                        )
                        pdf_url = supabase.storage.from_("documents").get_public_url(pdf_path)
                    
                    # 2. Görsel Yükleme
                    if img_file is not None:
                        file_ext = img_file.name.split(".")[-1]
                        img_path = f"licenses/{plate}.{file_ext}"
                        supabase.storage.from_("documents").upload(
                            path=img_path,
                            file=img_file.getvalue(),
                            file_options={"content-type": img_file.type, "upsert": "true"}
                        )
                        img_url = supabase.storage.from_("documents").get_public_url(img_path)
                    
                    # 3. Veritabanına Yazma/Güncelleme
                    record = {
                        "plate": plate,
                        "last_service_km": last_service_km,
                        "next_service_km": next_service_km,
                        "policy_pdf_url": pdf_url,
                        "license_img_url": img_url
                    }
                    
                    supabase.table("vehicles").upsert(record).execute()
                    st.success(f"🎉 **{plate}** plakalı aracın verileri başarıyla kaydedildi!")

# ==========================================
# 3. TOPLU EVRAK YÜKLEME SEKMESİ (YENİ)
# ==========================================
with tab_bulk:
    st.subheader("📁 Toplu Ruhsat ve Poliçe Yükleme")
    st.info("📌 **Önemli Kural:** Yükleyeceğiniz dosyaların adı tam olarak plaka olmalıdır.\n"
            "Örnek Ruhsat Fotoğrafı: `34ABC123.jpg` veya `06XYZ789.png`\n"
            "Örnek Poliçe PDF'i: `34ABC123.pdf` veya `06XYZ789.pdf`")
    
    col_bulk_img, col_bulk_pdf = st.columns(2)
    
    # 1. Toplu Ruhsat Fotoğrafı Yükleme
    with col_bulk_img:
        st.markdown("### 🪪 Toplu Ruhsat Fotoğrafları")
        bulk_imgs = st.file_uploader(
            "Birden fazla ruhsat fotoğrafı seçin", 
            type=["jpg", "jpeg", "png"], 
            accept_multiple_files=True,
            key="bulk_imgs"
        )
        
        if st.button("Ruhsatları Toplu Yükle", type="primary", use_container_width=True):
            if bulk_imgs:
                progress_bar = st.progress(0)
                success_count = 0
                
                for idx, file in enumerate(bulk_imgs):
                    # Dosya adından plakayı al (Örn: 34ABC123.jpg -> 34ABC123)
                    filename_without_ext = os.path.splitext(file.name)[0]
                    plate = filename_without_ext.strip().replace(" ", "").upper()
                    
                    if plate:
                        file_ext = file.name.split(".")[-1]
                        img_path = f"licenses/{plate}.{file_ext}"
                        
                        # Storage'a yükle
                        supabase.storage.from_("documents").upload(
                            path=img_path,
                            file=file.getvalue(),
                            file_options={"content-type": file.type, "upsert": "true"}
                        )
                        img_url = supabase.storage.from_("documents").get_public_url(img_path)
                        
                        # Veritabanında plaka varsa ruhsat URL'sini güncelle, yoksa yeni kayıt oluştur
                        existing_res = supabase.table("vehicles").select("*").eq("plate", plate).execute()
                        record = existing_res.data[0] if existing_res.data else {"plate": plate}
                        record["license_img_url"] = img_url
                        
                        supabase.table("vehicles").upsert(record).execute()
                        success_count += 1
                        
                    progress_bar.progress((idx + 1) / len(bulk_imgs))
                    
                st.success(f"🎉 Toplam {success_count} adet ruhsat görseli başarıyla yüklendi ve plakalara bağlandı!")
            else:
                st.warning("Lütfen en az bir fotoğraf dosyası seçin.")

    # 2. Toplu Poliçe PDF Yükleme
    with col_bulk_pdf:
        st.markdown("### 📄 Toplu Sigorta Poliçeleri (PDF)")
        bulk_pdfs = st.file_uploader(
            "Birden fazla poliçe PDF'i seçin", 
            type=["pdf"], 
            accept_multiple_files=True,
            key="bulk_pdfs"
        )
        
        if st.button("Poliçeleri Toplu Yükle", type="primary", use_container_width=True):
            if bulk_pdfs:
                progress_bar = st.progress(0)
                success_count = 0
                
                for idx, file in enumerate(bulk_pdfs):
                    # Dosya adından plakayı al (Örn: 34ABC123.pdf -> 34ABC123)
                    filename_without_ext = os.path.splitext(file.name)[0]
                    plate = filename_without_ext.strip().replace(" ", "").upper()
                    
                    if plate:
                        pdf_path = f"policies/{plate}.pdf"
                        
                        # Storage'a yükle
                        supabase.storage.from_("documents").upload(
                            path=pdf_path,
                            file=file.getvalue(),
                            file_options={"content-type": "application/pdf", "upsert": "true"}
                        )
                        pdf_url = supabase.storage.from_("documents").get_public_url(pdf_path)
                        
                        # Veritabanında plaka varsa poliçe URL'sini güncelle, yoksa yeni kayıt oluştur
                        existing_res = supabase.table("vehicles").select("*").eq("plate", plate).execute()
                        record = existing_res.data[0] if existing_res.data else {"plate": plate}
                        record["policy_pdf_url"] = pdf_url
                        
                        supabase.table("vehicles").upsert(record).execute()
                        success_count += 1
                        
                    progress_bar.progress((idx + 1) / len(bulk_pdfs))
                    
                st.success(f"🎉 Toplam {success_count} adet poliçe PDF'i başarıyla yüklendi ve plakalara bağlandı!")
            else:
                st.warning("Lütfen en az bir PDF dosyası seçin.")
