import sys
import json
import os
import random
import io
import requests

from datetime import datetime, timedelta
from collections import Counter

# PyQt5 Modülleri
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QTableWidget, QTableWidgetItem, QMessageBox,
                             QHeaderView, QInputDialog, QDialog, QFormLayout,
                             QDateEdit, QComboBox, QFrame, QTabWidget, QGridLayout,
                             QCheckBox, QFileDialog, QGroupBox, QScrollArea, QSpinBox,
                             QListWidget, QSizePolicy, QDoubleSpinBox, QSpacerItem,QMenu, QAction)
from PyQt5.QtCore import Qt, QDate, QByteArray, QTimer,QSize
from PyQt5.QtGui import QFont, QColor, QTextDocument

# SVG Modülü
from PyQt5.QtSvg import QSvgWidget

# YAZICI DESTEĞİ
from PyQt5.QtPrintSupport import QPrinter

# WEB VE HARİTA MODÜLLERİ
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    import folium
except ImportError:
    pass

# Matplotlib
import matplotlib

matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Dosya Adı
VERI_DOSYASI = "oto_kiralama_final.json"

# --- KAPORTA PARÇA LİSTESİ ---
ARAC_PARCALARI = [
    "Ön Tampon", "Motor Kaputu", "Tavan", "Bagaj Kapağı", "Arka Tampon",
    "Sol Ön Çamurluk", "Sol Ön Kapı", "Sol Arka Kapı", "Sol Arka Çamurluk",
    "Sağ Ön Çamurluk", "Sağ Ön Kapı", "Sağ Arka Kapı", "Sağ Arka Çamurluk",
    "Sol Marşpiyel", "Sağ Marşpiyel"
]

# --- MEKANİK VE İÇ AKSAM LİSTESİ ---
MEKANIK_PARCALAR = [
    "Motor Bloğu", "Şanzıman/Vites", "Debriyaj Seti", "Fren Sistemi",
    "Ön Aks/Salıncak", "Arka Aks", "Direksiyon Kutusu", "Amortisörler",
    "Egzoz Sistemi", "Klima Kompresörü", "Radyatör/Soğutma",
    "Akü/Elektrik Tesisatı", "Araç İçi Döşeme", "Multimedya Ekran",
    "Gösterge Paneli", "Lastikler/Jantlar"
]


class LoginDialog(QDialog):
    def __init__(self, ebeveyn_veri):
        super().__init__()
        self.setWindowTitle("Kullanıcı Girişi")
        self.setFixedSize(300, 200)
        self.veri = ebeveyn_veri  # Mevcut kullanıcı verilerini buradan alacağız
        self.kullanici_rolu = None  # Giriş başarılı olursa buraya 'admin' veya 'personel' yazılacak

        layout = QVBoxLayout(self)

        # Logo veya Başlık
        lbl_baslik = QLabel("🔐 Güvenli Giriş")
        lbl_baslik.setFont(QFont("Arial", 14, QFont.Bold))
        lbl_baslik.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_baslik)

        # Form
        form_layout = QFormLayout()
        self.inp_kadi = QLineEdit()
        self.inp_kadi.setPlaceholderText("Kullanıcı Adı")
        self.inp_sifre = QLineEdit()
        self.inp_sifre.setEchoMode(QLineEdit.Password)  # Şifreyi gizle
        self.inp_sifre.setPlaceholderText("Şifre")

        form_layout.addRow("Kullanıcı:", self.inp_kadi)
        form_layout.addRow("Şifre:", self.inp_sifre)
        layout.addLayout(form_layout)

        # Buton
        self.btn_giris = QPushButton("Giriş Yap")
        self.btn_giris.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.btn_giris.clicked.connect(self.kontrol_et)
        layout.addWidget(self.btn_giris)

        # Varsayılan kullanıcılar yoksa oluştur (Geçici çözüm)
        if "kullanicilar" not in self.veri:
            self.veri["kullanicilar"] = [
                {"kadi": "admin", "sifre": "admin", "rol": "yonetici"},
                {"kadi": "personel", "sifre": "1234", "rol": "personel"}
            ]

    def kontrol_et(self):
        kadi = self.inp_kadi.text()
        sifre = self.inp_sifre.text()

        kullanici = next((u for u in self.veri["kullanicilar"] if u["kadi"] == kadi and u["sifre"] == sifre), None)

        if kullanici:
            self.kullanici_rolu = kullanici["rol"]
            self.accept()  # Pencereyi kapat ve 'Tamam' döndür
        else:
            QMessageBox.warning(self, "Hata", "Hatalı kullanıcı adı veya şifre!")

# --- GPS SEKME WIDGET'I (GÜNCELLENDİ) ---
class GpsTakipWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.secili_arac_plaka = None
        self.arac_verileri = []  # Tüm araç listesini burada tutacağız

        # Rota ve Animasyon
        self.rota_koordinatlari = []
        self.simulasyon_index = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.animasyon_adim)

        # Sabit Başlangıç Noktası (OFİS) - Sultanahmet
        self.ofis_lat = 41.0054
        self.ofis_lon = 28.9768

        # Sol Panel
        self.panel_sol = QFrame()
        self.panel_sol.setFixedWidth(320)
        self.panel_sol.setStyleSheet("background-color: #ECEFF1; border-right: 1px solid #ccc;")
        self.layout_sol = QVBoxLayout(self.panel_sol)

        lbl_baslik = QLabel("🛰️ Canlı Filo Takip")
        lbl_baslik.setFont(QFont("Arial", 16, QFont.Bold))
        lbl_baslik.setStyleSheet("color: #263238; border: none;")
        self.layout_sol.addWidget(lbl_baslik)

        self.layout_sol.addWidget(QLabel("Takip Edilecek Araç:"))
        self.cmb_araclar = QComboBox()
        self.cmb_araclar.currentIndexChanged.connect(self.arac_secildi)
        self.layout_sol.addWidget(self.cmb_araclar)

        self.info_card = QFrame()
        self.info_card.setStyleSheet(
            "background-color: white; border-radius: 8px; padding: 15px; border: 1px solid #CFD8DC;")
        self.layout_info = QVBoxLayout(self.info_card)

        self.lbl_durum = QLabel("Durum: -")
        self.lbl_durum.setFont(QFont("Arial", 11, QFont.Bold))
        self.lbl_durum.setStyleSheet("color: #546E7A; border: none;")

        self.lbl_hiz = QLabel("Hız: 0 km/s")
        self.lbl_hiz.setFont(QFont("Arial", 14, QFont.Bold))
        self.lbl_hiz.setStyleSheet("color: #1976D2; border: none;")

        self.lbl_kalan = QLabel("Kalan Mesafe: -")
        self.lbl_kalan.setStyleSheet("border: none; color: #455A64;")

        self.layout_info.addWidget(self.lbl_durum)
        self.layout_info.addWidget(self.lbl_hiz)
        self.layout_info.addWidget(self.lbl_kalan)
        self.layout_sol.addWidget(self.info_card)

        self.layout_sol.addSpacing(20)
        self.lbl_rota_bilgi = QLabel("Rota Simülasyonu:")
        self.layout_sol.addWidget(self.lbl_rota_bilgi)

        btn_layout = QHBoxLayout()
        self.btn_baslat = QPushButton("▶️ Başlat")
        self.btn_baslat.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.btn_baslat.clicked.connect(self.simulasyonu_baslat)

        self.btn_durdur = QPushButton("⏸️ Durdur")
        self.btn_durdur.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; padding: 10px;")
        self.btn_durdur.clicked.connect(self.simulasyonu_durdur)

        btn_layout.addWidget(self.btn_baslat)
        btn_layout.addWidget(self.btn_durdur)
        self.layout_sol.addLayout(btn_layout)

        self.layout_sol.addStretch()
        self.layout.addWidget(self.panel_sol)

        self.web_view = QWebEngineView()
        self.layout.addWidget(self.web_view)

        # Haritayı Ofiste Başlat
        self.haritayi_baslat(self.ofis_lat, self.ofis_lon, zoom=12)

    def arac_listesini_yukle(self, arac_listesi):
        self.arac_verileri = arac_listesi  # Listeyi kaydet
        self.cmb_araclar.blockSignals(True)
        self.cmb_araclar.clear()
        plakalar = [a.get("plaka") for a in arac_listesi]
        self.cmb_araclar.addItems(plakalar)
        self.cmb_araclar.blockSignals(False)

    def haritayi_baslat(self, lat, lon, zoom=13, markers=[], polyline=None):
        try:
            m = folium.Map(location=[lat, lon], zoom_start=zoom, control_scale=True)

            if polyline:
                folium.PolyLine(polyline, color="#2196F3", weight=5, opacity=0.8).add_to(m)

            # Marker Ekleme
            for m_lat, m_lon, m_icon, m_color, m_tip in markers:
                icon = folium.Icon(color=m_color, icon=m_icon, prefix="fa")
                folium.Marker([m_lat, m_lon], tooltip=m_tip, icon=icon).add_to(m)

            # Eğer hiç marker yoksa ofisi ekle
            if not markers:
                folium.Marker([self.ofis_lat, self.ofis_lon], tooltip="Merkez Ofis",
                              icon=folium.Icon(color="gray", icon="building", prefix="fa")).add_to(m)

            data = io.BytesIO()
            m.save(data, close_file=False)
            html_content = data.getvalue().decode()

            car_icon_url = "https://cdn-icons-png.flaticon.com/512/3202/3202926.png"
            js_code = f"""
            <script>
            var vehicleMarker = null;
            function initVehicleMarker(lat, lon) {{
                var mapInstance = null;
                for (var key in window) {{ if (key.startsWith('map_')) {{ mapInstance = window[key]; break; }} }}
                if (mapInstance) {{
                    var carIcon = L.icon({{iconUrl: '{car_icon_url}', iconSize: [40, 40], iconAnchor: [20, 20], popupAnchor: [0, -20]}});
                    vehicleMarker = L.marker([lat, lon], {{icon: carIcon}}).addTo(mapInstance);
                    vehicleMarker.bindPopup("<b>Araç Konumu</b>").openPopup();
                }}
            }}
            function moveCar(lat, lon) {{ if (vehicleMarker) {{ var newLatLng = new L.LatLng(lat, lon); vehicleMarker.setLatLng(newLatLng); }} }}
            setTimeout(function() {{ initVehicleMarker({lat}, {lon}); }}, 1000);
            </script></body>"""

            final_html = html_content.replace("</body>", js_code)
            self.web_view.setHtml(final_html)
        except Exception as e:
            print(f"Harita Hatası: {e}")

    def arac_secildi(self):
        self.simulasyonu_durdur()
        self.lbl_hiz.setText("Hız: 0 km/s")
        self.lbl_kalan.setText("Kalan Mesafe: -")

        plaka = self.cmb_araclar.currentText()
        self.secili_arac_plaka = plaka

        # Seçilen aracın bilgilerini bul
        secili_arac = next((a for a in self.arac_verileri if a.get("plaka") == plaka), None)

        if not secili_arac: return

        durum = str(secili_arac.get("durum", "")).lower()

        if durum == "kirada":
            # ARAÇ KİRADA: ROTA OLUŞTUR
            self.lbl_durum.setText(f"Durum: Kirada (Hareket Halinde)")
            self.lbl_durum.setStyleSheet("color: #4CAF50; font-weight: bold; border: none;")

            self.btn_baslat.setEnabled(True)
            self.btn_durdur.setEnabled(True)

            # Başlangıç: OFİS
            start_lat, start_lon = self.ofis_lat, self.ofis_lon

            # Bitiş: Rastgele bir lokasyon (Simülasyon için)
            destinations = [
                (41.0422, 29.0067), (40.9901, 29.0206), (40.9760, 28.8147), (41.1091, 29.0254)
            ]
            end_lat, end_lon = random.choice(destinations)

            self.rota_getir(start_lat, start_lon, end_lat, end_lon)

        else:
            # ARAÇ MÜSAİT: OFİSTE SABİT
            self.lbl_durum.setText(f"Durum: Ofiste (Müsait)")
            self.lbl_durum.setStyleSheet("color: #1976D2; font-weight: bold; border: none;")
            self.lbl_kalan.setText("Konum: Merkez Ofis Otoparkı")

            # Butonları pasif yap
            self.btn_baslat.setEnabled(False)
            self.btn_durdur.setEnabled(False)
            self.rota_koordinatlari = []  # Rota yok

            # Haritayı ofis merkezli göster, sadece ofis markeri olsun
            markers = [
                (self.ofis_lat, self.ofis_lon, "building", "blue", f"{plaka} - Park Halinde")
            ]
            self.haritayi_baslat(self.ofis_lat, self.ofis_lon, zoom=16, markers=markers, polyline=None)

    def rota_getir(self, lat1, lon1, lat2, lon2):
        try:
            url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                coords = data['routes'][0]['geometry']['coordinates']
                self.rota_koordinatlari = [[lat, lon] for lon, lat in coords]
                self.simulasyon_index = 0
                self.haritayi_sifirla_ve_goster()
            else:
                QMessageBox.warning(self, "Hata", "Rota servisine ulaşılamadı.")
        except Exception as e:
            self.lbl_durum.setText("Hata: İnternet Yok")
            print(f"Rota Hatası: {e}")

    def haritayi_sifirla_ve_goster(self):
        if not self.rota_koordinatlari: return
        curr_lat, curr_lon = self.rota_koordinatlari[0]
        start = self.rota_koordinatlari[0]
        end = self.rota_koordinatlari[-1]
        markers = [(start[0], start[1], "play", "green", "Ofis (Başlangıç)"), (end[0], end[1], "flag", "red", "Varış")]
        self.haritayi_baslat(curr_lat, curr_lon, zoom=13, markers=markers, polyline=self.rota_koordinatlari)

    def simulasyonu_baslat(self):
        if not self.rota_koordinatlari: return
        self.timer.start(500)

    def simulasyonu_durdur(self):
        self.timer.stop()
        if self.lbl_durum.text().startswith("Durum: Kirada"):
            self.lbl_hiz.setText("Anlık Hız: 0 km/s")

    def animasyon_adim(self):
        if self.simulasyon_index >= len(self.rota_koordinatlari) - 1:
            self.simulasyonu_durdur()
            self.lbl_durum.setText("Durum: Varış Noktasında 🏁")
            return
        self.simulasyon_index += 1
        lat, lon = self.rota_koordinatlari[self.simulasyon_index]
        hiz = random.randint(30, 90)
        self.lbl_hiz.setText(f"Anlık Hız: {hiz} km/s")
        kalan = len(self.rota_koordinatlari) - self.simulasyon_index
        self.lbl_kalan.setText(f"Kalan Mesafe (Nokta): {kalan}")
        self.web_view.page().runJavaScript(f"moveCar({lat}, {lon});")


# --- HGS VE CEZA DİYALOGU ---
class CezaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HGS ve Trafik Cezası Ekle")
        self.setFixedSize(400, 350)
        self.tutar = 0.0
        self.aciklama = ""
        layout = QFormLayout(self)
        lbl_info = QLabel("Ceza veya Geçiş Bilgileri")
        lbl_info.setFont(QFont("Arial", 12, QFont.Bold))
        lbl_info.setStyleSheet("color: #C62828;")
        layout.addRow(lbl_info)
        self.date_ceza = QDateEdit(QDate.currentDate())
        self.date_ceza.setCalendarPopup(True)
        layout.addRow("İşlem Tarihi:", self.date_ceza)
        self.cmb_tur = QComboBox()
        self.cmb_tur.addItems(["HGS/OGS Geçişi", "Hız Cezası (Radar)", "Park Cezası", "Trafik Kural İhlali", "Diğer"])
        layout.addRow("İşlem Türü:", self.cmb_tur)
        self.spin_tutar = QDoubleSpinBox()
        self.spin_tutar.setRange(0, 100000)
        self.spin_tutar.setDecimals(2)
        self.spin_tutar.setSuffix(" TL")
        layout.addRow("Tutar:", self.spin_tutar)
        self.txt_detay = QLineEdit()
        self.txt_detay.setPlaceholderText("Örn: Avrasya Tüneli, Kızılay Meydanı vb.")
        layout.addRow("Konum/Detay:", self.txt_detay)
        btn_kaydet = QPushButton("Kaydet ve Ekle")
        btn_kaydet.setStyleSheet("background-color: #C62828; color: white; font-weight: bold; padding: 8px;")
        btn_kaydet.clicked.connect(self.kaydet)
        layout.addRow(btn_kaydet)

    def kaydet(self):
        if self.spin_tutar.value() <= 0:
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir tutar giriniz.")
            return
        self.tutar = self.spin_tutar.value()
        tur = self.cmb_tur.currentText()
        yer = self.txt_detay.text()
        tarih = self.date_ceza.date().toString("dd.MM.yyyy")
        self.aciklama = f"{tur} ({yer}) - {tarih}"
        self.accept()


# --- SVG ŞABLONU ---
CAR_SVG_TEMPLATE = """
<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 600" width="400" height="600">
  <defs>
    <linearGradient id="glassGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#aaccff;stop-opacity:0.5" />
      <stop offset="50%" style="stop-color:#ffffff;stop-opacity:0.3" />
      <stop offset="100%" style="stop-color:#aaccff;stop-opacity:0.5" />
    </linearGradient>
    <filter id="shadow">
      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.3"/>
    </filter>
  </defs>

  <!-- Arka Plan -->
  <rect width="100%" height="100%" fill="#F5F5F5"/>

  <!-- Ana Araç Gövdesi -->
  <g transform="translate(200, 300)">

    <!-- ÖN TAMPON -->
    <rect x="-60" y="-220" width="120" height="30" fill="{renk_Ön_Tampon}" 
          stroke="#333" stroke-width="2" rx="5"/>
    <text x="0" y="-200" font-size="10" text-anchor="middle" fill="#666">ÖN</text>

    <!-- MOTOR KAPUTU -->
    <rect x="-60" y="-190" width="120" height="80" fill="{renk_Motor_Kaputu}" 
          stroke="#333" stroke-width="2" rx="3"/>

    <!-- CAM (Ön) -->
    <rect x="-50" y="-108" width="100" height="35" fill="url(#glassGrad)" 
          stroke="#333" stroke-width="1.5" rx="2"/>

    <!-- TAVAN -->
    <rect x="-60" y="-73" width="120" height="90" fill="{renk_Tavan}" 
          stroke="#333" stroke-width="2"/>

    <!-- CAM (Arka) -->
    <rect x="-50" y="17" width="100" height="30" fill="url(#glassGrad)" 
          stroke="#333" stroke-width="1.5" rx="2"/>

    <!-- BAGAJ KAPAĞI -->
    <rect x="-60" y="47" width="120" height="70" fill="{renk_Bagaj_Kapağı}" 
          stroke="#333" stroke-width="2" rx="3"/>

    <!-- ARKA TAMPON -->
    <rect x="-60" y="117" width="120" height="30" fill="{renk_Arka_Tampon}" 
          stroke="#333" stroke-width="2" rx="5"/>
    <text x="0" y="140" font-size="10" text-anchor="middle" fill="#666">ARKA</text>

    <!-- SOL TARAF -->
    <g id="sol_taraf">
      <!-- Sol Ön Çamurluk -->
      <path d="M -60,-190 L -85,-180 L -85,-110 L -60,-110 Z" 
            fill="{renk_Sol_Ön_Çamurluk}" stroke="#333" stroke-width="2"/>

      <!-- Sol Ön Kapı -->
      <rect x="-85" y="-110" width="25" height="85" fill="{renk_Sol_Ön_Kapı}" 
            stroke="#333" stroke-width="2"/>
      <circle cx="-82" cy="-67" r="3" fill="#555"/>

      <!-- Sol Arka Kapı -->
      <rect x="-85" y="-25" width="25" height="72" fill="{renk_Sol_Arka_Kapı}" 
            stroke="#333" stroke-width="2"/>
      <circle cx="-82" cy="11" r="3" fill="#555"/>

      <!-- Sol Arka Çamurluk -->
      <path d="M -60,47 L -85,47 L -85,117 L -60,107 Z" 
            fill="{renk_Sol_Arka_Çamurluk}" stroke="#333" stroke-width="2"/>

      <!-- Sol Marşpiyel -->
      <rect x="-86" y="-110" width="2" height="157" fill="{renk_Sol_Marşpiyel}" 
            stroke="#222" stroke-width="0.5"/>
    </g>

    <!-- SAĞ TARAF (Mirror) -->
    <g id="sag_taraf">
      <!-- Sağ Ön Çamurluk -->
      <path d="M 60,-190 L 85,-180 L 85,-110 L 60,-110 Z" 
            fill="{renk_Sağ_Ön_Çamurluk}" stroke="#333" stroke-width="2"/>

      <!-- Sağ Ön Kapı -->
      <rect x="60" y="-110" width="25" height="85" fill="{renk_Sağ_Ön_Kapı}" 
            stroke="#333" stroke-width="2"/>
      <circle cx="82" cy="-67" r="3" fill="#555"/>

      <!-- Sağ Arka Kapı -->
      <rect x="60" y="-25" width="25" height="72" fill="{renk_Sağ_Arka_Kapı}" 
            stroke="#333" stroke-width="2"/>
      <circle cx="82" cy="11" r="3" fill="#555"/>

      <!-- Sağ Arka Çamurluk -->
      <path d="M 60,47 L 85,47 L 85,117 L 60,107 Z" 
            fill="{renk_Sağ_Arka_Çamurluk}" stroke="#333" stroke-width="2"/>

      <!-- Sağ Marşpiyel -->
      <rect x="84" y="-110" width="2" height="157" fill="{renk_Sağ_Marşpiyel}" 
            stroke="#222" stroke-width="0.5"/>
    </g>

    <!-- Tekerlekler -->
    <g id="tekerlekler">
      <!-- Sol Ön -->
      <ellipse cx="-85" cy="-150" rx="18" ry="22" fill="#2C2C2C" stroke="#000" stroke-width="2"/>
      <ellipse cx="-85" cy="-150" rx="12" ry="16" fill="#444"/>

      <!-- Sağ Ön -->
      <ellipse cx="85" cy="-150" rx="18" ry="22" fill="#2C2C2C" stroke="#000" stroke-width="2"/>
      <ellipse cx="85" cy="-150" rx="12" ry="16" fill="#444"/>

      <!-- Sol Arka -->
      <ellipse cx="-85" cy="77" rx="18" ry="22" fill="#2C2C2C" stroke="#000" stroke-width="2"/>
      <ellipse cx="-85" cy="77" rx="12" ry="16" fill="#444"/>

      <!-- Sağ Arka -->
      <ellipse cx="85" cy="77" rx="18" ry="22" fill="#2C2C2C" stroke="#000" stroke-width="2"/>
      <ellipse cx="85" cy="77" rx="12" ry="16" fill="#444"/>
    </g>

    <!-- Aynalar -->
    <ellipse cx="-65" cy="-95" rx="8" ry="6" fill="#333" stroke="#000" stroke-width="1"/>
    <ellipse cx="65" cy="-95" rx="8" ry="6" fill="#333" stroke="#000" stroke-width="1"/>

    <!-- Far ve Stop Detayları -->
    <g id="lights">
      <!-- Ön Farlar -->
      <ellipse cx="-45" cy="-205" rx="12" ry="8" fill="#FFF9C4" stroke="#333" stroke-width="1"/>
      <ellipse cx="45" cy="-205" rx="12" ry="8" fill="#FFF9C4" stroke="#333" stroke-width="1"/>

      <!-- Arka Stop -->
      <rect x="-50" y="125" width="20" height="8" fill="#EF5350" stroke="#333" stroke-width="1" rx="2"/>
      <rect x="30" y="125" width="20" height="8" fill="#EF5350" stroke="#333" stroke-width="1" rx="2"/>
    </g>
  </g>
</svg>
"""



class CarSvgWidget(QSvgWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # YENİ ORAN (Genişlik:Yükseklik)
        # Orijinal 1:1.5 yerine 1:1.2 kullanılarak yükseklik azaltıldı.
        self.ASPECT_RATIO = 1.2
        
        # Minimum Sınır: 200 x (200 * 1.2) = 240
        self.setMinimumSize(QSize(200, 240)) 
        
        # Maksimum Sınır: 600 x (600 * 1.2) = 720
        self.setMaximumSize(QSize(600, 720)) 

        # Widget'ın boyut politikasını esnek (Expanding) olarak ayarla
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.part_status = {}
        self.render_svg()
    
    # ----------------------------------------------------
    # EN-BOY ORANI KORUMA METOTLARI
    # ----------------------------------------------------
    
    def hasHeightForWidth(self):
        """Widget'ın genişliğe göre yüksekliğe sahip olduğunu belirtir."""
        return True

    def heightForWidth(self, w):
        """Genişliğe (w) göre yüksekliği (h) hesaplar (1:1.2 oranıyla)."""
        calculated_height = int(w * self.ASPECT_RATIO)
        
        # Sınırları kontrol et
        min_h = self.minimumHeight()
        max_h = self.maximumHeight()

        if calculated_height < min_h:
            return min_h
        if calculated_height > max_h:
            return max_h
            
        return calculated_height

    def set_parts_status(self, status_dict):
        """Parça durumlarını güncelle ve SVG'yi yeniden oluştur"""
        self.part_status = status_dict
        self.render_svg()

    def render_svg(self):
        """SVG şablonunu parça durumlarına göre renklendir"""
        # svg_content'in global olarak tanımlı CAR_SVG_TEMPLATE'den geldiği varsayılır.
        svg_content = CAR_SVG_TEMPLATE 

        for parca in ARAC_PARCALARI:
            placeholder = "{renk_" + parca.replace(" ", "_") + "}"
            durum = self.part_status.get(parca, "Orijinal")

            # Duruma göre renk ata
            if "Değişen" in durum:
                color = "#EF5350"  # Kırmızı
            elif "Boyalı" in durum:
                color = "#FDD835"  # Sarı
            else:
                color = "#E0E0E0"  # Gri (Orijinal)

            svg_content = svg_content.replace(placeholder, color)

        # SVG'yi widget'a yükle
        self.load(QByteArray(svg_content.encode('utf-8')))



class HasarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detaylı Hasar Kaydı Oluştur")
        self.setFixedSize(800, 650) 
        self.setMaximumSize(1200, 900) 
        self.setSizeGripEnabled(True)
        self.toplam_hasar = 0.0
        self.hasar_detayi = ""
        self.kaporta_checkboxes = []
        self.mekanik_checkboxes = [] 
        
        main_layout = QVBoxLayout(self)

        # Fiyatlandırma Grubu (En Üste - Global)
        fiyat_group = QGroupBox("Birim Fiyatlar (TL)")
        fiyat_layout = QHBoxLayout()
        fiyat_layout.addWidget(QLabel("Boya/Onarım:"))
        self.spin_boya_fiyat = QSpinBox()
        self.spin_boya_fiyat.setRange(0, 100000)
        self.spin_boya_fiyat.setValue(2500)
        self.spin_boya_fiyat.setSingleStep(500)
        self.spin_boya_fiyat.valueChanged.connect(self.hesapla)
        fiyat_layout.addWidget(self.spin_boya_fiyat)

        fiyat_layout.addWidget(QLabel("Değişim:"))
        self.spin_degisim_fiyat = QSpinBox()
        self.spin_degisim_fiyat.setRange(0, 100000)
        self.spin_degisim_fiyat.setValue(5000)
        self.spin_degisim_fiyat.setSingleStep(500)
        self.spin_degisim_fiyat.valueChanged.connect(self.hesapla)
        fiyat_layout.addWidget(self.spin_degisim_fiyat)
        fiyat_group.setLayout(fiyat_layout)
        main_layout.addWidget(fiyat_group)

        # Sekmeler
        self.tabs = QTabWidget()

        # -----------------------------------------------------------------
        # --- SEKME 1: KAPORTA & BOYA (DÜZENLENMİŞ) ---
        # -----------------------------------------------------------------
        self.tab_kaporta = QWidget()
        layout_kaporta = QVBoxLayout(self.tab_kaporta)

        # YENİ EKLENEN: SVG ve ScrollArea'yı yan yana tutacak yatay layout
        kaporta_yan_yana_layout = QHBoxLayout()

        # 1. Parça Seçme Kısmı (SOL Taraf - Daha Geniş Alan)
        scroll_kap = QScrollArea()
        scroll_kap.setWidgetResizable(True)
        # ScrollArea'nın yatayda genişlemesini sağla (Ağırlık 2)
        scroll_kap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        content_kap = QWidget()
        grid_kap = QGridLayout(content_kap)

        grid_kap.addWidget(QLabel("Parça Adı"), 0, 0)
        lbl_b = QLabel("Boyalı")
        lbl_b.setStyleSheet("color: #FBC02D; font-weight:bold;")
        grid_kap.addWidget(lbl_b, 0, 1)
        lbl_d = QLabel("Değişen")
        lbl_d.setStyleSheet("color: #D32F2F; font-weight:bold;")
        grid_kap.addWidget(lbl_d, 0, 2)

        self.kaporta_checkboxes = []
        for idx, parca in enumerate(ARAC_PARCALARI, start=1):
            lbl = QLabel(parca)
            chk_boya = QCheckBox()
            chk_boya.stateChanged.connect(self.hesapla)
            chk_degisen = QCheckBox()
            chk_degisen.stateChanged.connect(self.hesapla)
            
            # Radyo Buton Mantığı (Değişeni veya Boyalıyı seçince diğerini kapat)
            chk_boya.stateChanged.connect(lambda state, d=chk_degisen: d.setChecked(False) if state == Qt.Checked else None)
            chk_degisen.stateChanged.connect(lambda state, b=chk_boya: b.setChecked(False) if state == Qt.Checked else None)


            if idx % 2 == 0: lbl.setStyleSheet("background-color: #f9f9f9;")
            
            grid_kap.addWidget(lbl, idx, 0)
            grid_kap.addWidget(chk_boya, idx, 1)
            grid_kap.addWidget(chk_degisen, idx, 2)
            self.kaporta_checkboxes.append((parca, chk_boya, chk_degisen))
        
        # Grid'in sağ tarafındaki boşluğu uzat
        grid_kap.setColumnStretch(3, 1)
        
        scroll_kap.setWidget(content_kap)
        
        # Sol tarafa (1. eleman) ScrollArea'yı ekle (Ağırlık 2)
        kaporta_yan_yana_layout.addWidget(scroll_kap, 2) 
        
        # 2. SVG Görseli (SAĞ Taraf - Sabit Genişlik)
        self.preview_widget = CarSvgWidget()
        self.preview_widget.setStyleSheet("border: 1px solid #CFD8DC; border-radius: 5px;")
        
        # SVG'nin genişliğini sabitle (Örn: 350px) ve sağ tarafa taşı.
        self.preview_widget.setFixedWidth(350) 
        self.preview_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # Sağ tarafa (2. eleman) SVG'yi ekle (Ağırlık 1)
        kaporta_yan_yana_layout.addWidget(self.preview_widget, 1) 

        # Yeni yatay layout'u Kaporta sekmesinin ana dikey layout'una ekle
        layout_kaporta.addLayout(kaporta_yan_yana_layout)
        
        # Alt tarafta boşluk bırakmak için stretch ekle
        layout_kaporta.addStretch(1)

        self.tabs.addTab(self.tab_kaporta, "🚗 Kaporta & Boya")

        # -----------------------------------------------------------------
        # --- SEKME 2: MEKANİK & İÇ AKSAM (DEĞİŞİKLİK YOK) ---
        # -----------------------------------------------------------------
        self.tab_mekanik = QWidget()
        layout_mekanik = QVBoxLayout(self.tab_mekanik)

        scroll_mek = QScrollArea()
        scroll_mek.setWidgetResizable(True)
        content_mek = QWidget()

        grid_mek = QGridLayout(content_mek)
        grid_mek.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        grid_mek.setHorizontalSpacing(20)

        grid_mek.addWidget(QLabel("Parça / Sistem"), 0, 0)
        lbl_onarim = QLabel("Onarım")
        lbl_onarim.setStyleSheet("color: #1976D2; font-weight:bold;")
        grid_mek.addWidget(lbl_onarim, 0, 1)
        lbl_degisim_mek = QLabel("Değişim")
        lbl_degisim_mek.setStyleSheet("color: #D32F2F; font-weight:bold;")
        grid_mek.addWidget(lbl_degisim_mek, 0, 2)

        for idx, parca in enumerate(MEKANIK_PARCALAR, start=1):
            lbl = QLabel(parca)
            chk_onarim = QCheckBox()
            chk_onarim.stateChanged.connect(self.hesapla)
            chk_degisim = QCheckBox()
            chk_degisim.stateChanged.connect(self.hesapla)
            
            # Radyo Buton Mantığı (Onarım veya Değişimi seçince diğerini kapat)
            chk_onarim.stateChanged.connect(lambda state, d=chk_degisim: d.setChecked(False) if state == Qt.Checked else None)
            chk_degisim.stateChanged.connect(lambda state, o=chk_onarim: o.setChecked(False) if state == Qt.Checked else None)


            if idx % 2 == 0: lbl.setStyleSheet("background-color: #f9f9f9;")

            grid_mek.addWidget(lbl, idx, 0)
            grid_mek.addWidget(chk_onarim, idx, 1)
            grid_mek.addWidget(chk_degisim, idx, 2)

            self.mekanik_checkboxes.append((parca, chk_onarim, chk_degisim))

        grid_mek.setColumnStretch(3, 1)

        scroll_mek.setWidget(content_mek)
        layout_mekanik.addWidget(scroll_mek)
        self.tabs.addTab(self.tab_mekanik, "⚙️ Mekanik & İç Aksam")
        main_layout.addWidget(self.tabs)

        # Sonuç Paneli (DEĞİŞİKLİK YOK)
        ozet_layout = QHBoxLayout()
        self.lbl_sonuc = QLabel("Toplam Hasar: 0.00 TL")
        self.lbl_sonuc.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_sonuc.setStyleSheet("color: #D32F2F;")
        ozet_layout.addWidget(self.lbl_sonuc)
        btn_kaydet = QPushButton("✅ Kaydet ve Çık")
        btn_kaydet.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        btn_kaydet.clicked.connect(self.accept)
        ozet_layout.addWidget(btn_kaydet)
        main_layout.addLayout(ozet_layout)
        
        # Pencereyi Ekranın Ortasına Taşıma (DEĞİŞİKLİK YOK)
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())
        
    def hesapla(self):
        # HESAPLAMA FONKSİYONU (DEĞİŞİKLİK YOK)
        toplam = 0
        detaylar = []
        durum_dict = {}
        b_fiyat = self.spin_boya_fiyat.value()
        d_fiyat = self.spin_degisim_fiyat.value()

        # Kaporta Hesabı
        for parca, cb_b, cb_d in self.kaporta_checkboxes:
            durumlar = []
            if cb_d.isChecked():
                toplam += d_fiyat
                durumlar.append("Değişen")
                durum_dict[parca] = "Değişen"
            elif cb_b.isChecked():
                toplam += b_fiyat
                durumlar.append("Boyalı")
                durum_dict[parca] = "Boyalı"
            if durumlar:
                detaylar.append(f"{parca} ({', '.join(durumlar)})")
            
            # Radyo buton mantığını manuel olarak uygula (hesaplama fonksiyonunda da yapılabilir)
            if cb_d.isChecked() and cb_b.isChecked():
                if cb_d.sender() == cb_d: # Hangi kutunun işaretlendiğini kontrol etmek gerekir, burada basitleştiriyoruz.
                    cb_b.setChecked(False)
                else:
                    cb_d.setChecked(False)


        # Mekanik Hesabı
        for parca, cb_onarim, cb_degisim in self.mekanik_checkboxes:
            durumlar = []
            if cb_degisim.isChecked():
                toplam += d_fiyat
                durumlar.append("Değişim")
            elif cb_onarim.isChecked():
                toplam += b_fiyat
                durumlar.append("Onarım")
            if durumlar:
                detaylar.append(f"{parca} ({', '.join(durumlar)})")

        self.toplam_hasar = toplam
        self.hasar_detayi = " | ".join(detaylar) if detaylar else ""
        self.lbl_sonuc.setText(f"Toplam Hasar: {toplam:,.2f} TL")
        
        # SVG widget'ını güncelle
        self.preview_widget.set_parts_status(durum_dict)

class AracKiralamaUygulamasi(QMainWindow):
    def __init__(self, rol="yonetici"):
        super().__init__()
        self.rol = rol
        self.setWindowTitle(f"Araç Kiralama - {rol.upper()} Girişi")
        self.setGeometry(100, 100, 1300, 900)

        # Çıkış yapılıp yapılmadığını kontrol edecek bayrak
        self.cikis_yapildi = False

        self.veriler = {"araclar": [], "gecmis_islemler": [], "kullanicilar": []}

        # --- ANA DÜZEN (YENİ) ---
        # Direkt sekmeleri koymak yerine, bir widget içine Header + Sekmeler koyuyoruz.
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Kenar boşluklarını sıfırla
        main_layout.setSpacing(0)

        # --- ÜST BAR (HEADER) ---
        header_frame = QFrame()
        header_frame.setFixedHeight(60)
        header_frame.setStyleSheet("background-color: #263238; border-bottom: 2px solid #37474F;")
        header_layout = QHBoxLayout(header_frame)

        # Sol Tarafta Logo/İsim
        lbl_app_name = QLabel("🚗 Filo Yönetim Sistemi")
        lbl_app_name.setFont(QFont("Arial", 14, QFont.Bold))
        lbl_app_name.setStyleSheet("color: white; border: none;")
        header_layout.addWidget(lbl_app_name)

        header_layout.addStretch()  # Arayı boşlukla doldur (Sağa yaslamak için)

        # Sağ Tarafta Profil Baloncuğu
        self.btn_profil = QPushButton(f"{self.rol[0].upper()}")  # İsmin baş harfi
        self.btn_profil.setFixedSize(40, 40)
        # Yuvarlak buton ve stil ayarları
        self.btn_profil.setStyleSheet("""
            QPushButton {
                background-color: #FF9800; 
                color: white; 
                border-radius: 20px; 
                font-weight: bold; 
                font-size: 18px;
                border: 2px solid white;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.btn_profil.setCursor(Qt.PointingHandCursor)
        self.btn_profil.setToolTip(f"Giriş yapan: {self.rol}")
        self.btn_profil.clicked.connect(self.profil_menu_ac)  # Tıklanınca menü aç

        header_layout.addWidget(self.btn_profil)

        # Sağ tarafta biraz boşluk bırak
        header_layout.addSpacing(15)

        # Header'ı ana düzene ekle
        main_layout.addWidget(header_frame)

        # --- SEKMELER ---
        self.tabs = QTabWidget()
        # Sekmelerin style'ını biraz düzeltelim ki header ile uyumlu olsun
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; }")

        main_layout.addWidget(self.tabs)

        # ... (Buradan sonrası eski kodunla aynı devam ediyor) ...
        self.tab_yonetim = QWidget()
        self.arayuz_yonetim_kur()
        self.tabs.addTab(self.tab_yonetim, "🚗 Araç Yönetimi")

        self.tab_istatistik = QWidget()
        self.arayuz_istatistik_kur()
        self.tabs.addTab(self.tab_istatistik, "📊 Raporlar ve Analiz")

        self.tab_gecmis = QWidget()
        self.arayuz_gecmis_kur()
        self.tabs.addTab(self.tab_gecmis, "📜 İşlem Geçmişi")

        self.tab_hasar = QWidget()
        self.arayuz_hasar_izleme_kur()
        self.tabs.addTab(self.tab_hasar, "🔍 Hasar Görselleştirme")

        self.tab_gps = GpsTakipWidget()
        self.tabs.addTab(self.tab_gps, "🛰️ GPS Takip")

        self.tabs.currentChanged.connect(self.sekme_degisti)
        self.verileri_yukle()
        self.yetkileri_uygula()

    # --- YENİ EKLENECEK FONKSİYONLAR ---
    def profil_menu_ac(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #ccc;
            }
            QMenu::item {
                padding: 8px 20px;
                font-size: 14px;
            }
            QMenu::item:selected {
                background-color: #ECEFF1;
                color: #263238;
            }
        """)

        # Kullanıcı Bilgisi (Tıklanamaz, sadece bilgi)
        info_action = QAction(f"👤 Rol: {self.rol.capitalize()}", self)
        info_action.setEnabled(False)
        menu.addAction(info_action)

        menu.addSeparator()

        # Çıkış Yap Butonu
        logout_action = QAction("🚪 Çıkış Yap (Log Out)", self)
        logout_action.triggered.connect(self.cikis_yap_ve_don)
        menu.addAction(logout_action)

        # Menüyü butonun hemen altında aç
        menu.exec_(self.btn_profil.mapToGlobal(self.btn_profil.rect().bottomLeft()))

    def cikis_yap_ve_don(self):
        # Kullanıcıya sor
        cevap = QMessageBox.question(self, "Çıkış", "Oturumu kapatmak istediğinize emin misiniz?",
                                     QMessageBox.Yes | QMessageBox.No)
        if cevap == QMessageBox.Yes:
            self.cikis_yapildi = True  # Main döngüsüne haber veriyoruz
            self.close()  # Pencereyi kapat

    def yetkileri_uygula(self):
        if self.rol == "personel":
            # --- 1. İstatistik ve GPS Sekmelerini Gizle ---
            # Sekmelerin sırası değişebileceği için nesne üzerinden indeks bulup siliyoruz.

            # GPS Sekmesini Kaldır
            idx_gps = self.tabs.indexOf(self.tab_gps)
            if idx_gps != -1:
                self.tabs.removeTab(idx_gps)

            # Raporlar ve Analiz (İstatistik) Sekmesini Kaldır
            idx_istatistik = self.tabs.indexOf(self.tab_istatistik)
            if idx_istatistik != -1:
                self.tabs.removeTab(idx_istatistik)

            # --- 2. Araç Silme ve Düzenleme Butonlarını Gizle ---
            # Bu butonları objectName ile buluyoruz (styles.qss veya önceki tanımlardan)
            btn_sil = self.tab_yonetim.findChild(QPushButton, "btnSil")
            if btn_sil:
                btn_sil.setVisible(False)

            btn_duzenle = self.tab_yonetim.findChild(QPushButton, "btnDuzenle")
            if btn_duzenle:
                btn_duzenle.setEnabled(False)  # Sadece pasif yap, görünür kalsın (isteğe bağlı)

            # --- 3. Araç Ekleme Butonu (Opsiyonel) ---
            # Eğer "btnEkle" adını vermediysen bu çalışmayabilir,
            # ama güvenlik için gizlemeyi deneyelim.
            btn_ekle = self.tab_yonetim.findChild(QPushButton, "btnEkle")
            if btn_ekle:
                btn_ekle.setVisible(False)

    def arayuz_yonetim_kur(self):
        layout = QVBoxLayout()

        # --- BAŞLIK ---
        baslik = QLabel("Araç ve Filo Yönetimi")
        baslik.setFont(QFont("Arial", 16, QFont.Bold))
        baslik.setAlignment(Qt.AlignCenter)
        layout.addWidget(baslik)

        # --- ARAÇ EKLEME ALANI (GÜNCELLENDİ) ---
        form_group = QGroupBox("Yeni Araç Ekle / Sigorta & Muayene Girişi")
        form_layout = QGridLayout()
        form_group.setLayout(form_layout)

        self.input_plaka = QLineEdit()
        self.input_plaka.setPlaceholderText("Plaka (Örn: 34ABC123)")

        self.input_marka = QLineEdit()
        self.input_marka.setPlaceholderText("Marka")

        self.input_model = QLineEdit()
        self.input_model.setPlaceholderText("Model")

        self.input_ucret = QLineEdit()
        self.input_ucret.setPlaceholderText("Günlük Ücret (TL)")

        # Tarih Seçiciler
        self.date_trafik = QDateEdit(QDate.currentDate().addYears(1))
        self.date_trafik.setCalendarPopup(True)
        self.date_trafik.setDisplayFormat("yyyy-MM-dd")

        self.date_kasko = QDateEdit(QDate.currentDate().addYears(1))
        self.date_kasko.setCalendarPopup(True)
        self.date_kasko.setDisplayFormat("yyyy-MM-dd")

        self.date_muayene = QDateEdit(QDate.currentDate().addYears(2))
        self.date_muayene.setCalendarPopup(True)
        self.date_muayene.setDisplayFormat("yyyy-MM-dd")

        # Grid Yerleşimi
        form_layout.addWidget(QLabel("Araç Bilgileri:"), 0, 0)
        form_layout.addWidget(self.input_plaka, 0, 1)
        form_layout.addWidget(self.input_marka, 0, 2)
        form_layout.addWidget(self.input_model, 0, 3)
        form_layout.addWidget(self.input_ucret, 0, 4)

        form_layout.addWidget(QLabel("Bitiş Tarihleri:"), 1, 0)

        l_trafik = QVBoxLayout()
        l_trafik.addWidget(QLabel("Trafik Sig."))
        l_trafik.addWidget(self.date_trafik)
        form_layout.addLayout(l_trafik, 1, 1)

        l_kasko = QVBoxLayout()
        l_kasko.addWidget(QLabel("Kasko"))
        l_kasko.addWidget(self.date_kasko)
        form_layout.addLayout(l_kasko, 1, 2)

        l_muayene = QVBoxLayout()
        l_muayene.addWidget(QLabel("Muayene"))
        l_muayene.addWidget(self.date_muayene)
        form_layout.addLayout(l_muayene, 1, 3)

        btn_ekle = QPushButton("➕ Aracı Kaydet")
        btn_ekle.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; height: 30px;")
        btn_ekle.clicked.connect(self.arac_ekle)
        form_layout.addWidget(btn_ekle, 1, 4)

        layout.addWidget(form_group)

        # --- FİLTRELEME ALANI ---
        filtre_frame = QFrame()
        filtre_frame.setFrameShape(QFrame.StyledPanel)
        filtre_layout = QHBoxLayout(filtre_frame)

        filtre_layout.addWidget(QLabel("🔍 Hızlı Ara:"))
        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("Plaka veya Model...")
        self.txt_ara.textChanged.connect(self.tabloyu_guncelle)
        filtre_layout.addWidget(self.txt_ara)

        filtre_layout.addWidget(QLabel("Durum:"))
        self.cmb_filtre_durum = QComboBox()
        self.cmb_filtre_durum.addItems(["Tümü", "Müsait", "Kirada"])
        self.cmb_filtre_durum.currentTextChanged.connect(self.tabloyu_guncelle)
        filtre_layout.addWidget(self.cmb_filtre_durum)

        # Tarih filtresini buraya da ekleyebilirsiniz, şimdilik kod karmaşasını önlemek için basitleştirdim.

        layout.addWidget(filtre_frame)

        # --- TABLO (SÜTUN SAYISI ARTTI) ---
        self.tablo = QTableWidget()
        # Sütunlar: Plaka, Marka, Model, Ücret, Durum, Trafik Sig., Kasko, Muayene, Müşteri, Dönüş
        self.tablo.setColumnCount(10)
        self.tablo.setHorizontalHeaderLabels(
            ["Plaka", "Marka", "Model", "Ücret", "Durum", "Trafik Sig.", "Kasko", "Muayene", "Müşteri", "Dönüş T."])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tablo)

        # --- BUTONLAR ---
        # --- BUTONLAR (STYLES.QSS İLE UYUMLU HALE GETİRİLDİ) ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        btn_layout.setContentsMargins(0, 10, 0, 10)

        # 1. KİRALAMA BAŞLAT
        # QSS dosyasında #btnKirala ID'si MAVİ (#2196F3) olarak tanımlı
        btn_kirala = QPushButton("✅ Kiralama Başlat")
        btn_kirala.setObjectName("btnKirala")  # QSS bu ID'yi görünce stil uygular
        btn_kirala.setCursor(Qt.PointingHandCursor)
        btn_kirala.setFixedHeight(40)  # Yükseklik tercihen kodda kalabilir
        btn_kirala.clicked.connect(self.kiralama_baslat_dialog)

        # 2. ARACI İADE AL
        # QSS dosyasında #btnIade ID'si TURUNCU (#FF9800) olarak tanımlı
        btn_iade = QPushButton("🚗 Aracı İade Al")
        btn_iade.setObjectName("btnIade")
        btn_iade.setCursor(Qt.PointingHandCursor)
        btn_iade.setFixedHeight(40)
        btn_iade.clicked.connect(self.arac_iade_et)

        # 3. DÜZENLE
        # QSS dosyasında #btnDuzenle ID'si MOR (#9C27B0) olarak tanımlı
        btn_duzenle = QPushButton("✏️ Düzenle / Tarihleri Güncelle")
        btn_duzenle.setObjectName("btnDuzenle")
        btn_duzenle.setCursor(Qt.PointingHandCursor)
        btn_duzenle.setFixedHeight(40)
        btn_duzenle.clicked.connect(self.arac_duzenle)

        # 4. SİL
        # QSS dosyasında #btnSil ID'si KIRMIZI (#F44336) olarak tanımlı
        btn_sil = QPushButton("🗑️ Sil")
        btn_sil.setObjectName("btnSil")
        btn_sil.setCursor(Qt.PointingHandCursor)
        btn_sil.setFixedHeight(40)
        btn_sil.clicked.connect(self.arac_sil)

        # Butonları yerleşime ekle
        btn_layout.addWidget(btn_kirala)
        btn_layout.addWidget(btn_iade)
        btn_layout.addWidget(btn_duzenle)
        btn_layout.addWidget(btn_sil)

        layout.addLayout(btn_layout)

        self.tab_yonetim.setLayout(layout)

    def arayuz_istatistik_kur(self):
        layout = QVBoxLayout()
        grid = QGridLayout()
        self.lbl_gelir = QLabel("0 TL")
        self.lbl_gelir.setFont(QFont("Arial", 28, QFont.Bold))
        self.lbl_gelir.setStyleSheet("color: #0D47A1;")
        self.lbl_gelir.setAlignment(Qt.AlignCenter)
        self.lbl_kirada = QLabel("0")
        self.lbl_kirada.setFont(QFont("Arial", 28, QFont.Bold))
        self.lbl_kirada.setStyleSheet("color: #01579B;")
        self.lbl_kirada.setAlignment(Qt.AlignCenter)
        self.lbl_marka = QLabel("-")
        self.lbl_marka.setFont(QFont("Arial", 28, QFont.Bold))
        self.lbl_marka.setStyleSheet("color: #1565C0;")
        self.lbl_marka.setAlignment(Qt.AlignCenter)
        for i, (lbl, baslik_metni, renk) in enumerate(
                [(self.lbl_gelir, "Toplam Gelir", "#E3F2FD"),
                 (self.lbl_kirada, "Kiradaki Araçlar", "#E1F5FE"),
                 (self.lbl_marka, "Popüler Marka", "#E8F0FE")]):
            card = QFrame()
            card.setFixedHeight(150)
            card.setStyleSheet(f"background-color: {renk}; border-radius: 15px; border: 1px solid #BBDEFB;")
            l = QVBoxLayout()
            l.setAlignment(Qt.AlignCenter)
            lbl_baslik = QLabel(baslik_metni)
            lbl_baslik.setFont(QFont("Arial", 14, QFont.Bold))
            lbl_baslik.setStyleSheet("color: #546E7A; border: none;")
            lbl_baslik.setAlignment(Qt.AlignCenter)
            l.addWidget(lbl_baslik)
            l.addWidget(lbl)
            card.setLayout(l)
            grid.addWidget(card, 0, i)
        layout.addLayout(grid)
        layout.addSpacing(20)
        self.figure = Figure(figsize=(10, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        self.tab_istatistik.setLayout(layout)

    def arayuz_gecmis_kur(self):
        layout = QVBoxLayout()
        baslik = QLabel("Geçmiş İşlem Kayıtları")
        baslik.setFont(QFont("Arial", 14, QFont.Bold))
        baslik.setAlignment(Qt.AlignCenter)
        layout.addWidget(baslik)
        filtre_frame = QFrame()
        filtre_frame.setObjectName("form_group")
        filtre_layout = QHBoxLayout()
        filtre_frame.setLayout(filtre_layout)
        filtre_layout.addWidget(QLabel("🔍 Ara:"))
        self.txt_ara_gecmis = QLineEdit()
        self.txt_ara_gecmis.setPlaceholderText("Plaka, Müşteri...")
        self.txt_ara_gecmis.textChanged.connect(self.gecmis_tablosunu_guncelle)
        filtre_layout.addWidget(self.txt_ara_gecmis)
        filtre_layout.addWidget(QLabel("Ödeme:"))
        self.cmb_filtre_odeme = QComboBox()
        self.cmb_filtre_odeme.addItems(["Tümü", "Nakit", "Kredi Kartı", "Havale/EFT", "Çek", "Senet"])
        self.cmb_filtre_odeme.currentIndexChanged.connect(self.gecmis_tablosunu_guncelle)
        filtre_layout.addWidget(self.cmb_filtre_odeme)
        filtre_layout.addWidget(QLabel("Durum:"))
        self.cmb_filtre_durum_gecmis = QComboBox()
        self.cmb_filtre_durum_gecmis.addItems(["Tümü", "Hasarlı İşlemler", "Cezalı İşlemler", "Sorunsuz İşlemler"])
        self.cmb_filtre_durum_gecmis.currentIndexChanged.connect(self.gecmis_tablosunu_guncelle)
        filtre_layout.addWidget(self.cmb_filtre_durum_gecmis)
        self.chk_tarih_gecmis = QCheckBox("Tarih:")
        self.chk_tarih_gecmis.stateChanged.connect(self.gecmis_tablosunu_guncelle)
        filtre_layout.addWidget(self.chk_tarih_gecmis)
        self.date_gecmis_bas = QDateEdit(QDate.currentDate().addMonths(-1))
        self.date_gecmis_bas.setCalendarPopup(True)
        self.date_gecmis_bas.dateChanged.connect(self.gecmis_tablosunu_guncelle)
        self.date_gecmis_bit = QDateEdit(QDate.currentDate())
        self.date_gecmis_bit.setCalendarPopup(True)
        self.date_gecmis_bit.dateChanged.connect(self.gecmis_tablosunu_guncelle)
        filtre_layout.addWidget(self.date_gecmis_bas)
        filtre_layout.addWidget(QLabel("-"))
        filtre_layout.addWidget(self.date_gecmis_bit)
        btn_pdf = QPushButton("📄 PDF İndir")
        btn_pdf.setObjectName("btnDuzenle")
        btn_pdf.clicked.connect(self.gecmis_pdf_aktar)
        filtre_layout.addWidget(btn_pdf)
        layout.addWidget(filtre_frame)
        self.tablo_gecmis = QTableWidget()
        self.tablo_gecmis.setColumnCount(8)
        self.tablo_gecmis.setHorizontalHeaderLabels(
            ["Tarih", "Plaka", "Müşteri", "Gün", "Hasar", "HGS/Ceza", "Ödeme", "Toplam"])
        self.tablo_gecmis.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tablo_gecmis)
        self.tab_gecmis.setLayout(layout)

    def arayuz_hasar_izleme_kur(self):
        # Ana Dikey Düzen (Top Frame + Yatay İçerik)
        main_v_layout = QVBoxLayout(self.tab_hasar)

        # 1. Üst Kontrol Çerçevesi
        top_frame = QFrame()
        top_layout = QHBoxLayout(top_frame)

        # Etiketi de biraz büyütelim ki uyumlu olsun
        lbl_secim = QLabel("Araç Seçiniz:")
        lbl_secim.setFont(QFont("Arial", 12))
        top_layout.addWidget(lbl_secim)

        # --- DEĞİŞİKLİK BURADA: ComboBox (Filtre Kutusu) Büyütme ---
        self.cmb_hasar_arac = QComboBox()
        self.cmb_hasar_arac.setFont(QFont("Arial", 12))  # Yazı boyutu 12 yapıldı
        self.cmb_hasar_arac.setMinimumHeight(40)  # Kutunun yüksekliği arttırıldı
        self.cmb_hasar_arac.setMinimumWidth(250)  # Kutunun genişliği arttırıldı
        self.cmb_hasar_arac.currentIndexChanged.connect(self.hasar_arac_secildi)
        top_layout.addWidget(self.cmb_hasar_arac)

        top_layout.addStretch()

        # Açıklamalar (Legend)
        for renk, aciklama in [("#FFFFFF", "Orijinal"), ("#FDD835", "Boyalı (Sarı)"), ("#EF5350", "Değişen (Kırmızı)")]:
            lbl = QLabel(f"  {aciklama}  ")
            lbl.setFont(QFont("Arial", 20, QFont.Bold))  # Açıklamaları da hafif belirginleştirdik
            lbl.setStyleSheet(
                f"background-color: {renk}; color: #333; border:1px solid #ccc; border-radius: 4px; padding: 4px; font-weight: bold;")
            top_layout.addWidget(lbl)

        main_v_layout.addWidget(top_frame)

        # ------------------------------------------------------------------
        # 2. YATAY İÇERİK DÜZENİ (Liste ve SVG)
        # ------------------------------------------------------------------
        content_h_layout = QHBoxLayout()

        # A) SOL KISIM: Hasar Detay Listesi ve Başlık
        list_v_layout = QVBoxLayout()

        lbl_liste_baslik = QLabel("Hasar Detay Listesi:")
        lbl_liste_baslik.setFont(QFont("Arial", 10, QFont.Bold))
        list_v_layout.addWidget(lbl_liste_baslik)

        self.list_hasar_detay = QListWidget()
        # --- DEĞİŞİKLİK BURADA: Liste Yazı Boyutu Büyütme ---
        self.list_hasar_detay.setFont(QFont("Arial", 50))  # Liste içeriği büyütüldü
        self.list_hasar_detay.setSpacing(10)  # Satırlar arası hafif boşluk eklendi

        # Listeye dikeyde esneme yeteneği ver
        self.list_hasar_detay.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        list_v_layout.addWidget(self.list_hasar_detay)

        # Yatay düzene listeyi ekle (Ağırlık 2: Daha fazla yatay alan)
        content_h_layout.addLayout(list_v_layout, 2)

        # B) SAĞ KISIM: SVG Görseli
        self.car_widget = CarSvgWidget()
        self.car_widget.setStyleSheet("border: 1px solid #CFD8DC; border-radius: 5px;")

        self.car_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Yatay düzene SVG'yi ekle (Ağırlık 1)
        content_h_layout.addWidget(self.car_widget, 1)

        # 3. Yatay Düzeni Ana Dikey Düzene Ekle
        main_v_layout.addLayout(content_h_layout)
        

    def hasar_arac_secildi(self):
        plaka = self.cmb_hasar_arac.currentText()
        if not plaka: return
        self.list_hasar_detay.clear()
        self.car_widget.set_parts_status({})
        son_hasar_kaydi = None
        for islem in reversed(self.veriler.get("gecmis_islemler", [])):
            if islem.get("plaka") == plaka and islem.get("hasar_detayi"):
                son_hasar_kaydi = islem.get("hasar_detayi")
                break
        if son_hasar_kaydi:
            durum_sozlugu = {}
            parcalar = son_hasar_kaydi.split(" | ")
            for p in parcalar:
                self.list_hasar_detay.addItem(p)
                if " (" in p:
                    ad = p.split(" (")[0]
                    durum = p
                    durum_sozlugu[ad] = durum
            self.car_widget.set_parts_status(durum_sozlugu)
        else:
            self.list_hasar_detay.addItem("Kayıtlı hasar bulunamadı (Orijinal).")

    def sekme_degisti(self, index):
        # Sekmeler gizlendiğinde indeks numaraları değişir (Örn: 4 numara 2 olabilir).
        # Bu yüzden indeks yerine doğrudan "Görüntülenen Widget"ı kontrol ediyoruz.

        curr_widget = self.tabs.currentWidget()

        if curr_widget == self.tab_istatistik:
            # İstatistik sekmesi
            self.istatistik_kartlari_guncelle()
            self.grafik_ciz()

        elif curr_widget == self.tab_gecmis:
            # Geçmiş İşlemler sekmesi
            self.gecmis_tablosunu_guncelle()

        elif curr_widget == self.tab_hasar:
            # Hasar Görselleştirme sekmesi
            self.cmb_hasar_arac.blockSignals(True)
            self.cmb_hasar_arac.clear()
            # Güncel araç listesini combobox'a yükle
            araclar = [a.get("plaka") for a in self.veriler.get("araclar", [])]
            self.cmb_hasar_arac.addItems(araclar)
            self.cmb_hasar_arac.blockSignals(False)
            self.hasar_arac_secildi()

        elif curr_widget == self.tab_gps:
            # GPS sekmesi (Eğer yöneticiyse çalışır)
            self.tab_gps.arac_listesini_yukle(self.veriler.get("araclar", []))

    def istatistik_kartlari_guncelle(self):
        gecmis_gelir = sum(item.get('net_kazanc', 0) for item in self.veriler.get('gecmis_islemler', []))
        aktif_gelir = sum(float(arac.get('alinan_odeme', 0) or 0) for arac in self.veriler.get('araclar', []))
        toplam_gelir = gecmis_gelir + aktif_gelir
        self.lbl_gelir.setText(f"{toplam_gelir:,.2f} TL")
        kirada_sayisi = sum(
            1 for arac in self.veriler.get('araclar', []) if str(arac.get('durum', '')).lower() == 'kirada')
        self.lbl_kirada.setText(str(kirada_sayisi))
        markalar = [self.plaka_to_marka(islem.get('plaka')) for islem in self.veriler.get('gecmis_islemler', [])]
        markalar = [m for m in markalar if m]
        if markalar:
            en_cok = Counter(markalar).most_common(1)[0]
            self.lbl_marka.setText(f"{en_cok[0]} ({en_cok[1]})")
        else:
            self.lbl_marka.setText("-")

    def gecmis_tablosunu_guncelle(self):
        self.tablo_gecmis.setRowCount(0)
        arama = (self.txt_ara_gecmis.text() or "").strip().lower()
        filtre_odeme = self.cmb_filtre_odeme.currentText()
        filtre_durum = self.cmb_filtre_durum_gecmis.currentText()
        tarih_aktif = self.chk_tarih_gecmis.isChecked()

        if tarih_aktif:
            t_bas = self.date_gecmis_bas.date().toPyDate()
            t_bit = self.date_gecmis_bit.date().toPyDate()
            if t_bas > t_bit: t_bas, t_bit = t_bit, t_bas

        for islem in reversed(self.veriler.get('gecmis_islemler', [])):
            tarih_str = islem.get("tarih", "")
            plaka = str(islem.get("plaka", "")).lower()
            musteri = str(islem.get("musteri", "")).lower()
            odeme_turu = str(islem.get("odeme_turu", "-"))
            hasar_ucreti = float(islem.get("hasar_ucreti", 0))
            ceza_ucreti = float(islem.get("ceza_ucreti", 0))

            if arama and (arama not in plaka and arama not in musteri): continue

            if tarih_aktif:
                try:
                    islem_tarih = datetime.strptime(tarih_str, "%Y-%m-%d").date()
                    if not (t_bas <= islem_tarih <= t_bit): continue
                except Exception:
                    continue

            if filtre_odeme != "Tümü" and filtre_odeme != odeme_turu:
                continue

            if filtre_durum == "Hasarlı İşlemler" and hasar_ucreti <= 0:
                continue
            elif filtre_durum == "Cezalı İşlemler" and ceza_ucreti <= 0:
                continue
            elif filtre_durum == "Sorunsuz İşlemler" and (hasar_ucreti > 0 or ceza_ucreti > 0):
                continue

            row = self.tablo_gecmis.rowCount()
            self.tablo_gecmis.insertRow(row)
            self.tablo_gecmis.setItem(row, 0, QTableWidgetItem(tarih_str))
            self.tablo_gecmis.setItem(row, 1, QTableWidgetItem(islem.get("plaka", "")))
            self.tablo_gecmis.setItem(row, 2, QTableWidgetItem(islem.get("musteri", "")))
            self.tablo_gecmis.setItem(row, 3, QTableWidgetItem(str(islem.get("kullanilan_gun", ""))))

            item_hasar = QTableWidgetItem(f"{hasar_ucreti:,.2f} TL")
            if hasar_ucreti > 0: item_hasar.setForeground(QColor("red"))
            self.tablo_gecmis.setItem(row, 4, item_hasar)

            item_ceza = QTableWidgetItem(f"{ceza_ucreti:,.2f} TL")
            if ceza_ucreti > 0: item_ceza.setForeground(QColor("red"))
            self.tablo_gecmis.setItem(row, 5, item_ceza)

            self.tablo_gecmis.setItem(row, 6, QTableWidgetItem(odeme_turu))
            self.tablo_gecmis.setItem(row, 7, QTableWidgetItem(f"{islem.get('net_kazanc', 0):,.2f} TL"))

    def gecmis_pdf_aktar(self):
        bugun = datetime.now().date()
        sinir_tarih = bugun - timedelta(days=30)
        rapor_verisi = []
        toplam_kazanc = 0
        for islem in self.veriler.get("gecmis_islemler", []):
            try:
                tarih = datetime.strptime(islem.get("tarih"), "%Y-%m-%d").date()
                if tarih >= sinir_tarih:
                    rapor_verisi.append(islem)
                    toplam_kazanc += float(islem.get("net_kazanc", 0))
            except Exception:
                continue
        if not rapor_verisi:
            QMessageBox.warning(self, "Uyarı", "Son 30 güne ait kayıt bulunamadı.")
            return
        dosya_yolu, _ = QFileDialog.getSaveFileName(self, "PDF Olarak Kaydet", "Rapor.pdf", "PDF Dosyaları (*.pdf)")
        if not dosya_yolu: return
        html = f"""<h1 style="text-align:center; color:#0D47A1;">Son 30 Günlük İşlem Raporu</h1><p style="text-align:center;">Tarih: {bugun.strftime("%d.%m.%Y")}</p><br><table border="1" cellspacing="0" cellpadding="5" width="100%" style="border-collapse:collapse; font-family:Arial;"><tr style="background-color:#E3F2FD;"><th>Tarih</th><th>Plaka</th><th>Müşteri</th><th>Gün</th><th>Hasar</th><th>HGS/Ceza</th><th>Ödeme</th><th>Toplam</th></tr>"""
        for veri in rapor_verisi:
            hasar = float(veri.get('hasar_ucreti', 0))
            ceza = float(veri.get('ceza_ucreti', 0))
            odeme = str(veri.get('odeme_turu', '-'))
            html += f"""<tr><td>{veri.get('tarih')}</td><td>{veri.get('plaka')}</td><td>{veri.get('musteri')}</td><td style="text-align:center;">{veri.get('kullanilan_gun')}</td><td style="text-align:right;">{hasar:,.2f} TL</td><td style="text-align:right;">{ceza:,.2f} TL</td><td style="text-align:center;">{odeme}</td><td style="text-align:right;">{veri.get('net_kazanc')} TL</td></tr>"""
        html += f"""</table><br><h3 style="text-align:right; color:#D32F2F;">Genel Toplam: {toplam_kazanc:,.2f} TL</h3>"""
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(dosya_yolu)
        doc = QTextDocument()
        doc.setHtml(html)
        doc.print_(printer)
        QMessageBox.information(self, "Başarılı", "PDF dosyası başarıyla oluşturuldu.")

    def grafik_ciz(self):
        self.figure.clear()
        aylik_gelir = {}
        aylik_adet = {}
        for islem in self.veriler.get("gecmis_islemler", []):
            tarih = islem.get("tarih", "")
            if len(tarih) >= 7:
                ay = tarih[:7]
                aylik_gelir[ay] = aylik_gelir.get(ay, 0) + float(islem.get("net_kazanc", 0) or 0)
                aylik_adet[ay] = aylik_adet.get(ay, 0) + 1
        butun_aylar = sorted(list(set(aylik_gelir.keys()) | set(aylik_adet.keys())))
        gelirler = [aylik_gelir.get(ay, 0) for ay in butun_aylar]
        adetler = [aylik_adet.get(ay, 0) for ay in butun_aylar]
        if not butun_aylar:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, 'Henüz Veri Yok', ha='center', va='center')
            self.canvas.draw()
            return
        ax1 = self.figure.add_subplot(121)
        bars1 = ax1.bar(butun_aylar, gelirler, color='#1976D2', width=0.5)
        ax1.set_title('Aylık Gelir (TL)')
        ax1.grid(axis='y', linestyle='--', alpha=0.6)
        for bar in bars1: ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{int(bar.get_height())}',
                                   ha='center', va='bottom', fontsize=8)
        ax2 = self.figure.add_subplot(122)
        bars2 = ax2.bar(butun_aylar, adetler, color='#64B5F6', width=0.5)
        ax2.set_title('Kiralama Adedi')
        ax2.grid(axis='y', linestyle='--', alpha=0.6)
        for bar in bars2: ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{int(bar.get_height())}',
                                   ha='center', va='bottom', fontsize=8)
        self.figure.tight_layout()
        self.canvas.draw()

    def tabloyu_guncelle(self):
        self.tablo.setRowCount(0)
        arama = (self.txt_ara.text() or "").strip().lower()
        filtre_durum = self.cmb_filtre_durum.currentText()

        bugun = datetime.now().date()

        for arac in self.veriler.get("araclar", []):
            plaka = str(arac.get("plaka", "")).strip()
            marka = str(arac.get("marka", "")).strip()
            model = str(arac.get("model", "")).strip()
            durum = str(arac.get("durum", "müsait")).strip().lower()

            # Filtreleme
            if filtre_durum != "Tümü" and filtre_durum.lower() != durum: continue
            combined = (marka + " " + model + " " + plaka).lower()
            if arama and arama not in combined: continue

            # Tarih Verileri
            trafik = arac.get("trafik_bitis", "-")
            kasko = arac.get("kasko_bitis", "-")
            muayene = arac.get("muayene_bitis", "-")

            row = self.tablo.rowCount()
            self.tablo.insertRow(row)

            # Hücreleri Oluştur
            items = [
                plaka, marka, model, f"{arac.get('ucret', 0)} TL", durum.upper(),
                trafik, kasko, muayene,
                arac.get("kiralayan", "-"), arac.get("planlanan_bitis", "-")
            ]

            for i, val in enumerate(items):
                item = QTableWidgetItem(str(val))

                # 1. DURUM RENKLENDİRMESİ
                if i == 4:
                    if durum == "kirada":
                        item.setForeground(QColor("#D32F2F"))  # Kırmızı yazı
                        item.setFont(QFont("Arial", 9, QFont.Bold))
                    else:
                        item.setForeground(QColor("#2E7D32"))  # Yeşil yazı
                        item.setFont(QFont("Arial", 9, QFont.Bold))

                # 2. TARİH KONTROLÜ VE UYARI SİSTEMİ (DÜZELTİLDİ)
                # Sütun indeksleri: 5 (Trafik), 6 (Kasko), 7 (Muayene)
                if i in [5, 6, 7] and val != "-" and val != "":
                    try:
                        # HATA BURADAYDI: %yyyy yerine %Y olmalı
                        bitis_tarihi = datetime.strptime(val, "%Y-%m-%d").date()
                        kalan_gun = (bitis_tarihi - bugun).days

                        if kalan_gun < 0:  # Tarihi Geçmiş
                            item.setBackground(QColor("#FFEBEE"))  # Arkaplan Kırmızı
                            item.setForeground(QColor("#C62828"))  # Yazı Koyu Kırmızı
                            item.setToolTip(f"⚠️ DİKKAT! Süre {abs(kalan_gun)} gün önce dolmuş!")
                        elif kalan_gun <= 30:  # 30 günden az kalmış
                            item.setBackground(QColor("#FFF3E0"))  # Arkaplan Turuncu
                            item.setForeground(QColor("#EF6C00"))  # Yazı Turuncu
                            item.setToolTip(f"⚠️ Uyarı: Bitmesine {kalan_gun} gün kaldı.")
                    except ValueError:
                        # Eğer tarih formatı bozuksa veya boşsa hata vermeden geç
                        pass
                    except Exception as e:
                        print(f"Tarih hatası: {e}")

                self.tablo.setItem(row, i, item)

    def plaka_to_marka(self, plaka):
        if not plaka: return None
        arac = next((a for a in self.veriler.get("araclar", []) if a.get("plaka") == plaka), None)
        return arac.get("marka") if arac else None

    def arac_ekle(self):
        plaka = (self.input_plaka.text() or "").strip().upper()
        marka = (self.input_marka.text() or "").strip()
        model = (self.input_model.text() or "").strip()

        try:
            ucret = float(self.input_ucret.text())
        except Exception:
            QMessageBox.warning(self, "Hata", "Günlük ücret sayı olmalı.")
            return

        if not plaka:
            QMessageBox.warning(self, "Hata", "Plaka boş olamaz.")
            return

        if any(a.get("plaka") == plaka for a in self.veriler.get("araclar", [])):
            QMessageBox.warning(self, "Hata", "Bu plakaya sahip araç zaten mevcut.")
            return

        # Tarihleri string olarak al
        trafik_tar = self.date_trafik.date().toString("yyyy-MM-dd")
        kasko_tar = self.date_kasko.date().toString("yyyy-MM-dd")
        muayene_tar = self.date_muayene.date().toString("yyyy-MM-dd")

        yeni_arac = {
            "plaka": plaka,
            "marka": marka,
            "model": model,
            "ucret": ucret,
            "durum": "müsait",
            "kiralayan": "-",
            "baslangic": "-",
            "planlanan_bitis": "-",
            "alinan_odeme": 0,
            # YENİ ALANLAR
            "trafik_bitis": trafik_tar,
            "kasko_bitis": kasko_tar,
            "muayene_bitis": muayene_tar
        }

        self.veriler.setdefault("araclar", []).append(yeni_arac)
        self.verileri_kaydet()
        self.tabloyu_guncelle()

        # Formu temizle
        self.input_plaka.clear()
        self.input_marka.clear()
        self.input_model.clear()
        self.input_ucret.clear()
        QMessageBox.information(self, "Bilgi", "Araç ve tarih bilgileri eklendi.")

    def arac_duzenle(self):
        row = self.tablo.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Hata", "Lütfen düzenlemek için bir araç seçin.")
            return

        plaka_item = self.tablo.item(row, 0)
        if not plaka_item: return
        plaka = plaka_item.text()

        arac = next((a for a in self.veriler.get("araclar", []) if a.get("plaka") == plaka), None)
        if not arac: return

        d = QDialog(self)
        d.setWindowTitle(f"Araç Düzenle - {plaka}")
        d.setFixedSize(400, 350)
        l = QFormLayout(d)

        # Mevcut verileri çek
        txt_marka = QLineEdit(str(arac.get("marka", "")))
        txt_model = QLineEdit(str(arac.get("model", "")))
        txt_ucret = QLineEdit(str(arac.get("ucret", 0)))

        # Tarihleri çek (Eğer yoksa bugünü koy)
        def str_to_qdate(t_str):
            if not t_str or t_str == "-": return QDate.currentDate()
            try:
                dt = datetime.strptime(t_str, "%Y-%m-%d")
                return QDate(dt.year, dt.month, dt.day)
            except:
                return QDate.currentDate()

        dt_trafik = QDateEdit(str_to_qdate(arac.get("trafik_bitis")))
        dt_trafik.setCalendarPopup(True)
        dt_trafik.setDisplayFormat("yyyy-MM-dd")

        dt_kasko = QDateEdit(str_to_qdate(arac.get("kasko_bitis")))
        dt_kasko.setCalendarPopup(True)
        dt_kasko.setDisplayFormat("yyyy-MM-dd")

        dt_muayene = QDateEdit(str_to_qdate(arac.get("muayene_bitis")))
        dt_muayene.setCalendarPopup(True)
        dt_muayene.setDisplayFormat("yyyy-MM-dd")

        l.addRow("Marka:", txt_marka)
        l.addRow("Model:", txt_model)
        l.addRow("Günlük Ücret:", txt_ucret)
        l.addRow(QLabel("--- Tarih Bilgileri ---"))
        l.addRow("Trafik Sig. Bitiş:", dt_trafik)
        l.addRow("Kasko Bitiş:", dt_kasko)
        l.addRow("Muayene Bitiş:", dt_muayene)

        btn_kaydet = QPushButton("Değişiklikleri Kaydet")
        btn_kaydet.clicked.connect(d.accept)
        btn_kaydet.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        l.addRow(btn_kaydet)

        if d.exec_() == QDialog.Accepted:
            try:
                arac["marka"] = txt_marka.text()
                arac["model"] = txt_model.text()
                arac["ucret"] = float(txt_ucret.text())

                # Tarihleri Güncelle
                arac["trafik_bitis"] = dt_trafik.date().toString("yyyy-MM-dd")
                arac["kasko_bitis"] = dt_kasko.date().toString("yyyy-MM-dd")
                arac["muayene_bitis"] = dt_muayene.date().toString("yyyy-MM-dd")

                self.verileri_kaydet()
                self.tabloyu_guncelle()
                QMessageBox.information(self, "Bilgi", "Araç bilgileri güncellendi.")
            except ValueError:
                QMessageBox.warning(self, "Hata", "Ücret sayısal bir değer olmalıdır.")

    def kiralama_baslat_dialog(self):
        row = self.tablo.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Hata", "Lütfen bir araç seçin.")
            return
        plaka_item = self.tablo.item(row, 0)
        if not plaka_item: return
        plaka = plaka_item.text()
        arac = next((a for a in self.veriler.get("araclar", []) if a.get("plaka") == plaka), None)
        if not arac:
            QMessageBox.warning(self, "Hata", "Araç bulunamadı.")
            return
        if str(arac.get("durum", "")).lower() == "kirada":
            QMessageBox.warning(self, "Hata", "Bu araç zaten kirada!")
            return
        d = QDialog(self)
        d.setWindowTitle("Kiralama Başlat")
        l = QFormLayout(d)
        input_musteri = QLineEdit()
        input_musteri.setPlaceholderText("Müşteri Adı")
        input_baslangic = QDateEdit(QDate.currentDate())
        input_baslangic.setCalendarPopup(True)
        input_bitis = QDateEdit(QDate.currentDate().addDays(1))
        input_bitis.setCalendarPopup(True)
        input_odeme = QLineEdit()
        input_odeme.setPlaceholderText("Peşin alınan ödeme (opsiyonel)")
        l.addRow("Müşteri:", input_musteri)
        l.addRow("Başlangıç Tarihi:", input_baslangic)
        l.addRow("Planlanan Bitiş:", input_bitis)
        l.addRow("Alınan Ödeme:", input_odeme)
        btn = QPushButton("Kiralama Başlat")
        btn.clicked.connect(d.accept)
        l.addRow(btn)
        if d.exec_() == QDialog.Accepted:
            musteri = input_musteri.text().strip()
            if musteri == "":
                QMessageBox.warning(self, "Hata", "Müşteri adı boş olamaz.")
                return
            bas_date = input_baslangic.date().toPyDate()
            bit_date = input_bitis.date().toPyDate()
            if bas_date > bit_date: bas_date, bit_date = bit_date, bas_date
            bas_tarih = bas_date.strftime("%Y-%m-%d")
            bit_tarih = bit_date.strftime("%Y-%m-%d")
            try:
                odeme = float(input_odeme.text()) if input_odeme.text() else 0.0
            except Exception:
                QMessageBox.warning(self, "Hata", "Ödeme kısmına sayı girin.")
                return
            try:
                gun = (bit_date - bas_date).days
            except Exception:
                gun = 1
            gun = 1 if gun < 1 else gun
            toplam_tutar = gun * float(arac.get("ucret", 0) or 0)
            if QMessageBox.question(self, "Onay",
                                    f"{musteri} - {plaka}\nGün: {gun}\nTutar: {toplam_tutar} TL\nDevam edilsin mi?") != QMessageBox.Yes:
                return
            arac["durum"] = "kirada"
            arac["kiralayan"] = musteri
            arac["baslangic"] = bas_tarih
            arac["planlanan_bitis"] = bit_tarih
            arac["alinan_odeme"] = odeme
            self.verileri_kaydet()
            self.tabloyu_guncelle()
            QMessageBox.information(self, "Başarılı", "Kiralama başlatıldı!")

    def arac_iade_et(self):
        row = self.tablo.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Hata", "Lütfen bir araç seçin.")
            return
        plaka_item = self.tablo.item(row, 0)
        if not plaka_item: return
        plaka = plaka_item.text()
        arac = next((a for a in self.veriler.get("araclar", []) if a.get("plaka") == plaka), None)
        if not arac or str(arac.get("durum", "")).lower() != "kirada":
            QMessageBox.warning(self, "Hata", "Seçilen araç şu an kirada değil.")
            return
        d = QDialog(self)
        d.setWindowTitle("Araç İade & Hasar & Ceza Kontrol")
        d.setFixedSize(350, 450)
        layout = QVBoxLayout(d)
        layout.addWidget(QLabel("Gerçek Dönüş Tarihi:"))
        date_input = QDateEdit(QDate.currentDate())
        date_input.setCalendarPopup(True)
        date_input.setDisplayFormat("yyyy-MM-dd")
        layout.addWidget(date_input)
        layout.addSpacing(10)

        self.eklenen_hasar_ucreti = 0.0
        self.eklenen_hasar_detayi = ""
        self.eklenen_ceza_ucreti = 0.0
        self.eklenen_ceza_detayi = ""

        self.lbl_hasar_bilgi = QLabel("Hasar Kaydı Yok")
        self.lbl_hasar_bilgi.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.lbl_hasar_bilgi)

        self.lbl_ceza_bilgi = QLabel("Ceza/HGS Yok")
        self.lbl_ceza_bilgi.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.lbl_ceza_bilgi)

        btn_hasar_ekle = QPushButton("🛠️ Hasar Kaydı Oluştur")
        btn_hasar_ekle.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")

        def ac_hasar_formu():
            hd = HasarDialog(d)
            if hd.exec_() == QDialog.Accepted:
                self.eklenen_hasar_ucreti = hd.toplam_hasar
                self.eklenen_hasar_detayi = hd.hasar_detayi
                if self.eklenen_hasar_ucreti > 0:
                    self.lbl_hasar_bilgi.setText(f"Eklenen Hasar: {self.eklenen_hasar_ucreti:,.2f} TL")
                    self.lbl_hasar_bilgi.setStyleSheet("color: red; font-weight: bold;")
                else:
                    self.lbl_hasar_bilgi.setText("Hasar Kaydı Yok")
                    self.lbl_hasar_bilgi.setStyleSheet("color: green; font-weight: bold;")

        btn_hasar_ekle.clicked.connect(ac_hasar_formu)
        layout.addWidget(btn_hasar_ekle)

        btn_ceza_ekle = QPushButton("🚨 HGS & Ceza Ekle")
        btn_ceza_ekle.setStyleSheet("background-color: #C62828; color: white; font-weight: bold;")

        def ac_ceza_formu():
            cd = CezaDialog(d)
            if cd.exec_() == QDialog.Accepted:
                self.eklenen_ceza_ucreti += cd.tutar
                if self.eklenen_ceza_detayi:
                    self.eklenen_ceza_detayi += " | " + cd.aciklama
                else:
                    self.eklenen_ceza_detayi = cd.aciklama
                if self.eklenen_ceza_ucreti > 0:
                    self.lbl_ceza_bilgi.setText(f"Eklenen Ceza: {self.eklenen_ceza_ucreti:,.2f} TL")
                    self.lbl_ceza_bilgi.setStyleSheet("color: red; font-weight: bold;")

        btn_ceza_ekle.clicked.connect(ac_ceza_formu)
        layout.addWidget(btn_ceza_ekle)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Tahsilat Yöntemi:"))
        self.cmb_odeme_turu = QComboBox()
        self.cmb_odeme_turu.addItems(["Nakit", "Kredi Kartı", "Havale/EFT", "Çek", "Senet"])
        layout.addWidget(self.cmb_odeme_turu)

        layout.addSpacing(20)
        btn_onay = QPushButton("İadeyi Tamamla")
        btn_onay.clicked.connect(d.accept)
        layout.addWidget(btn_onay)

        if d.exec_() == QDialog.Accepted:
            bit_date = date_input.date().toPyDate()
            try:
                bas = datetime.strptime(arac.get("baslangic", "-"), "%Y-%m-%d").date()
            except Exception:
                QMessageBox.warning(self, "Hata", "Araç başlangıç verisi bozuk.")
                return
            gun = (bit_date - bas).days
            gun = 1 if gun < 1 else gun
            kira_bedeli = gun * float(arac.get("ucret", 0) or 0)

            toplam_tutar = kira_bedeli + self.eklenen_hasar_ucreti + self.eklenen_ceza_ucreti
            odeme_yontemi = self.cmb_odeme_turu.currentText()

            ozet = f"""
            Müşteri: {arac.get("kiralayan")}
            Plaka: {plaka}
            -------------------------
            Kullanım Süresi: {gun} Gün
            Kira Bedeli: {kira_bedeli:,.2f} TL
            Hasar Ücreti: {self.eklenen_hasar_ucreti:,.2f} TL
            HGS/Ceza: {self.eklenen_ceza_ucreti:,.2f} TL
            -------------------------
            TOPLAM TAHSİLAT: {toplam_tutar:,.2f} TL
            Ödeme Yöntemi: {odeme_yontemi}
            """
            if QMessageBox.question(self, "İade Özeti", ozet) == QMessageBox.Yes:
                self.veriler.setdefault("gecmis_islemler", []).append({
                    "tarih": datetime.now().strftime("%Y-%m-%d"),
                    "plaka": arac.get("plaka"),
                    "musteri": arac.get("kiralayan"),
                    "kullanilan_gun": gun,
                    "hasar_ucreti": self.eklenen_hasar_ucreti,
                    "hasar_detayi": self.eklenen_hasar_detayi,
                    "ceza_ucreti": self.eklenen_ceza_ucreti,
                    "ceza_detayi": self.eklenen_ceza_detayi,
                    "odeme_turu": odeme_yontemi,
                    "net_kazanc": toplam_tutar
                })
                arac.update(
                    {"durum": "müsait", "kiralayan": "-", "baslangic": "-", "planlanan_bitis": "-", "alinan_odeme": 0})
                self.verileri_kaydet()
                self.tabloyu_guncelle()
                QMessageBox.information(self, "Bilgi", "Araç başarıyla iade alındı.")

    def arac_sil(self):
        row = self.tablo.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Hata", "Lütfen bir araç seçin.")
            return
        plaka_item = self.tablo.item(row, 0)
        if not plaka_item: return
        plaka = plaka_item.text()
        if QMessageBox.question(self, "Sil",
                                f"{plaka} plakalı aracı silmek istediğinize emin misiniz?") == QMessageBox.Yes:
            self.veriler["araclar"] = [a for a in self.veriler.get("araclar", []) if a.get("plaka") != plaka]
            self.verileri_kaydet()
            self.tabloyu_guncelle()
            QMessageBox.information(self, "Bilgi", "Araç silindi.")

    def verileri_kaydet(self):
        try:
            with open(VERI_DOSYASI, "w", encoding="utf-8") as f:
                json.dump(self.veriler, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Veri kaydedilemedi: {e}")

    def verileri_yukle(self):
        if os.path.exists(VERI_DOSYASI):
            try:
                with open(VERI_DOSYASI, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.veriler["araclar"] = data.get("araclar", [])
                        self.veriler["gecmis_islemler"] = data.get("gecmis_islemler", [])
                        self.veriler["kullanicilar"] = data.get("kullanicilar", [
                            {"kadi": "admin", "sifre": "admin", "rol": "yonetici"},
                            {"kadi": "personel", "sifre": "1234", "rol": "personel"}
                        ])
            except Exception:
                # ... hata yönetimi ...
                pass

        # Eğer dosya yoksa veya kullanıcılar listesi boşsa varsayılanları ata
        if not self.veriler.get("kullanicilar"):
            self.veriler["kullanicilar"] = [
                {"kadi": "admin", "sifre": "admin", "rol": "yonetici"},
                {"kadi": "personel", "sifre": "1234", "rol": "personel"}
            ]

        self.tabloyu_guncelle()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Stil dosyasını yükleme
    try:
        with open("styles.qss", "r", encoding="utf-8") as f:
            _style = f.read()
            app.setStyleSheet(_style)
    except:
        pass

    # --- SÜREKLİ DÖNGÜ ---
    while True:
        # 1. Verileri Oku
        gecici_veri = {}
        if os.path.exists(VERI_DOSYASI):
            try:
                with open(VERI_DOSYASI, "r", encoding="utf-8") as f:
                    gecici_veri = json.load(f)
            except:
                gecici_veri = {}

        # 2. Login Ekranını Aç
        login = LoginDialog(gecici_veri)
        sonuc = login.exec_()

        if sonuc == QDialog.Accepted:
            # Giriş Başarılı -> Ana Pencereyi Aç
            rol = login.kullanici_rolu
            pencere = AracKiralamaUygulamasi(rol=rol)
            pencere.show()

            # Ana pencere kapanana kadar bekle
            app.exec_()

            # Pencere kapandı. Neden kapandı?
            if pencere.cikis_yapildi:
                # Eğer kullanıcı "Log Out" dediyse döngü başa döner (While True)
                continue
            else:
                # Eğer kullanıcı "X"e basıp kapattıysa program tamamen biter
                break
        else:
            # Login ekranında "İptal" veya "Kapat" denirse döngüyü kır
            break

    sys.exit()