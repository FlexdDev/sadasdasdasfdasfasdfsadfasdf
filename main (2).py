import json
import time
import logging
import threading
import os
import signal
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# API sunucusu için Flask import
from flask import Flask, request, jsonify

# Rich imports for beautiful console GUI
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.align import Align
from rich.columns import Columns
from rich import box
from rich.rule import Rule
import keyboard
import asyncio

# Logging yapılandırması
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/betterkick_tool_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("BetterKickTool")

class BetterKickTool:
    def __init__(self):
        self.drivers = []
        self.profiles = []
        self.links = {}
        self.active_links = []  # [(link_id, profile_id), ...] formatında
        self.running = True
        self.check_interval = 300  # 5 dakika
        self.last_status_check = 0
        self.discord_webhook_url = None
        
        # GUI için console ve state
        self.console = Console()
        self.gui_enabled = True
        self.gui_thread = None
        self.show_help_panel = False
        self.last_errors = []  # Son hataları sakla
        self.last_logs = []    # Son logları sakla
        
        # Veri dizinleri kontrolü
        if not os.path.exists('data'):
            os.makedirs('data')
        
        # Yapılandırma yükleme
        self.load_config()
        
        # Pencere konumları dinamik olarak hesaplanacak
        self.window_positions = []
        
        # Ctrl+C yakalama
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Status check thread
        self.status_thread = None
        
    def signal_handler(self, sig, frame):
        """Ctrl+C ile programı güvenli şekilde sonlandır"""
        logger.info("Program sonlandırılıyor...")
        self.running = False
        self.gui_enabled = False
        self.cleanup()
        sys.exit(0)
        
    def add_error(self, error_msg):
        """Hata mesajını listeye ekle"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.last_errors.append(f"[{timestamp}] {error_msg}")
        if len(self.last_errors) > 10:  # Son 10 hatayı sakla
            self.last_errors.pop(0)
            
    def add_log(self, log_msg):
        """Log mesajını listeye ekle"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.last_logs.append(f"[{timestamp}] {log_msg}")
        if len(self.last_logs) > 15:  # Son 15 logu sakla
            self.last_logs.pop(0)
        
    def load_config(self):
        """Yapılandırma dosyasını yükle"""
        try:
            if os.path.exists('data/config.json'):
                with open('data/config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.check_interval = config.get('check_interval', 300)
                    self.discord_webhook_url = config.get('discord_webhook_url', None)
                    logger.info(f"Yapılandırma yüklendi: Kontrol aralığı {self.check_interval} saniye")
                    self.add_log(f"Yapılandırma yüklendi: {self.check_interval}s aralık")
            else:
                # Varsayılan yapılandırma oluştur
                self.save_config()
        except Exception as e:
            logger.error(f"Yapılandırma yüklenirken hata: {str(e)}")
            self.add_error(f"Yapılandırma hatası: {str(e)}")
            self.save_config()
    
    def save_config(self):
        """Yapılandırma dosyasını kaydet"""
        try:
            config = {
                'check_interval': self.check_interval,
                'discord_webhook_url': self.discord_webhook_url
            }
            with open('data/config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info("Yapılandırma kaydedildi")
            self.add_log("Yapılandırma kaydedildi")
        except Exception as e:
            logger.error(f"Yapılandırma kaydedilirken hata: {str(e)}")
            self.add_error(f"Yapılandırma kaydetme hatası: {str(e)}")
            
    def load_profiles(self):
        """Edge profillerini JSON dosyasından yükle"""
        try:
            if os.path.exists('data/profiles.json'):
                with open('data/profiles.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.profiles = data.get('profiles', [])
                    logger.info(f"{len(self.profiles)} profil yüklendi")
                    self.add_log(f"{len(self.profiles)} profil yüklendi")
                    return True
            else:
                logger.warning("profiles.json dosyası bulunamadı, örnek dosya oluşturuluyor")
                self.add_log("Profil dosyası bulunamadı, örnek oluşturuluyor")
                self.create_sample_profiles()
                return False
        except Exception as e:
            logger.error(f"Profiller yüklenirken hata: {str(e)}")
            self.add_error(f"Profil yükleme hatası: {str(e)}")
            self.create_sample_profiles()
            return False
            
    def load_links(self):
        """Yayın linklerini JSON dosyasından yükle"""
        try:
            if os.path.exists('data/links.json'):
                with open('data/links.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    links_list = data.get('links', [])
                    
                    # Linkleri sözlük yapısına dönüştür
                    self.links = {}
                    for i, link_data in enumerate(links_list):
                        link_id = str(i + 1)
                        self.links[link_id] = {
                            'name': link_data.get('name', f'Yayın {link_id}'),
                            'url': link_data.get('url', ''),
                            'status': 'inactive'
                        }
                    
                    logger.info(f"{len(self.links)} link yüklendi")
                    self.add_log(f"{len(self.links)} link yüklendi")
                    return True
            else:
                logger.warning("links.json dosyası bulunamadı, örnek dosya oluşturuluyor")
                self.add_log("Link dosyası bulunamadı, örnek oluşturuluyor")
                self.create_sample_links()
                return False
        except Exception as e:
            logger.error(f"Linkler yüklenirken hata: {str(e)}")
            self.add_error(f"Link yükleme hatası: {str(e)}")
            self.create_sample_links()
            return False
    
    def save_links(self):
        """Linkleri JSON dosyasına kaydet"""
        try:
            links_list = []
            for link_id, link_data in self.links.items():
                links_list.append({
                    'name': link_data['name'],
                    'url': link_data['url']
                })
                
            data = {'links': links_list}
            
            with open('data/links.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"{len(self.links)} link kaydedildi")
            self.add_log(f"{len(self.links)} link kaydedildi")
            return True
        except Exception as e:
            logger.error(f"Linkler kaydedilirken hata: {str(e)}")
            self.add_error(f"Link kaydetme hatası: {str(e)}")
            return False
            
    def create_sample_profiles(self):
        """Örnek profil dosyası oluştur"""
        import os
        username = os.getenv('USERNAME', 'YourUsername')
        base_path = f"C:\\Users\\{username}\\AppData\\Local\\Microsoft\\Edge\\User Data"
        
        sample_profiles = {
            "profiles": [
                {
                    "name": "Varsayılan Profil",
                    "path": f"{base_path}\\Default"
                },
                {
                    "name": "Profil 1", 
                    "path": f"{base_path}\\Profile 1"
                },
                {
                    "name": "Profil 2",
                    "path": f"{base_path}\\Profile 2"
                },
                {
                    "name": "Profil 3",
                    "path": f"{base_path}\\Profile 3"
                }
            ]
        }
        
        with open('data/profiles.json', 'w', encoding='utf-8') as f:
            json.dump(sample_profiles, f, indent=2, ensure_ascii=False)
        logger.info("Örnek profiles.json dosyası oluşturuldu")
        logger.info(f"Profil yolları {username} kullanıcısı için ayarlandı")
        logger.info("Lütfen Edge'de profilleri oluşturun ve giriş yapın")
        self.add_log(f"Örnek profiller oluşturuldu ({username})")
        
    def create_sample_links(self):
        """Örnek link dosyası oluştur"""
        sample_links = {
            "links": [
                {
                    "name": "Twitch Just Chatting",
                    "url": "https://www.twitch.tv/directory/game/Just%20Chatting"
                },
                {
                    "name": "YouTube Trending",
                    "url": "https://www.youtube.com/feed/trending"
                },
                {
                    "name": "Kick Just Chatting",
                    "url": "https://kick.com/categories/just-chatting"
                },
                {
                    "name": "Twitch IRL",
                    "url": "https://www.twitch.tv/directory/game/IRL"
                }
            ]
        }
        
        with open('data/links.json', 'w', encoding='utf-8') as f:
            json.dump(sample_links, f, indent=2, ensure_ascii=False)
        logger.info("Örnek links.json dosyası oluşturuldu")
        self.add_log("Örnek linkler oluşturuldu")
        
    def calculate_window_positions(self, count):
        """Pencere konumlarını dinamik olarak hesapla"""
        # Ekran boyutlarını dinamik olarak al
        try:
            import tkinter as tk
            root = tk.Tk()
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            root.destroy()
        except:
            screen_width = 1920  # Varsayılan
            screen_height = 1080
        
        # Taskbar ve window decorations için alan bırak
        usable_width = screen_width - 20
        usable_height = screen_height - 80
        start_x = 10
        start_y = 10
        
        positions = []
        
        if count == 1:
            # Tek pencere: Tam ekran
            positions.append({
                "x": start_x, "y": start_y, 
                "width": usable_width, "height": usable_height
            })
        elif count == 2:
            # İki pencere: Yan yana
            width = usable_width // 2 - 10
            positions.append({"x": start_x, "y": start_y, "width": width, "height": usable_height})
            positions.append({"x": start_x + width + 20, "y": start_y, "width": width, "height": usable_height})
        elif count == 3:
            # 3 pencere: 2 üstte, 1 altta ortalı
            width = usable_width // 2 - 10
            height = usable_height // 2 - 10
            positions.append({"x": start_x, "y": start_y, "width": width, "height": height})
            positions.append({"x": start_x + width + 20, "y": start_y, "width": width, "height": height})
            positions.append({"x": start_x + width//2 + 10, "y": start_y + height + 20, "width": width, "height": height})
        elif count == 4:
            # 4 pencere: 2x2 grid
            width = usable_width // 2 - 10
            height = usable_height // 2 - 10
            positions.append({"x": start_x, "y": start_y, "width": width, "height": height})
            positions.append({"x": start_x + width + 20, "y": start_y, "width": width, "height": height})
            positions.append({"x": start_x, "y": start_y + height + 20, "width": width, "height": height})
            positions.append({"x": start_x + width + 20, "y": start_y + height + 20, "width": width, "height": height})
        elif count <= 6:
            # 5-6 pencere: 3x2 grid
            width = usable_width // 3 - 15
            height = usable_height // 2 - 10
            for i in range(count):
                row = i // 3
                col = i % 3
                x = start_x + col * (width + 20)
                y = start_y + row * (height + 20)
                positions.append({"x": x, "y": y, "width": width, "height": height})
        elif count <= 9:
            # 7-9 pencere: 3x3 grid
            width = usable_width // 3 - 15
            height = usable_height // 3 - 15
            for i in range(count):
                row = i // 3
                col = i % 3
                x = start_x + col * (width + 20)
                y = start_y + row * (height + 20)
                positions.append({"x": x, "y": y, "width": width, "height": height})
        else:
            # 10+ pencere: 4x3 grid (maksimum 12 pencere)
            width = usable_width // 4 - 20
            height = usable_height // 3 - 15
            for i in range(min(count, 12)):
                row = i // 4
                col = i % 4
                x = start_x + col * (width + 25)
                y = start_y + row * (height + 20)
                positions.append({"x": x, "y": y, "width": width, "height": height})
        
        return positions
        
    def create_edge_driver(self, profile_path, profile_name):
        """Belirtilen profil ile Edge driver oluştur"""
        try:
            edge_options = Options()
            
            # Edge profil yapısını doğru şekilde ayarla
            user_data_dir = os.path.dirname(profile_path)
            profile_directory = os.path.basename(profile_path)
            
            # Profil dizininin var olduğunu kontrol et
            if not os.path.exists(profile_path):
                logger.error(f"Profil dizini bulunamadı: {profile_path}")
                self.add_error(f"Profil bulunamadı: {profile_name}")
                return None
            
            edge_options.add_argument(f"--user-data-dir={user_data_dir}")
            edge_options.add_argument(f"--profile-directory={profile_directory}")
            edge_options.add_argument("--no-first-run")
            edge_options.add_argument("--no-default-browser-check")
            edge_options.add_argument("--disable-extensions")
            edge_options.add_argument("--disable-plugins")
            edge_options.add_argument("--mute-audio")
            edge_options.add_argument("--disable-web-security")
            edge_options.add_argument("--disable-features=VizDisplayCompositor")
            edge_options.add_argument("--disable-blink-features=AutomationControlled")
            edge_options.add_argument("--disable-dev-shm-usage")
            edge_options.add_argument("--no-sandbox")
            edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            edge_options.add_experimental_option('useAutomationExtension', False)
            
            # Edge Driver servisini başlat
            try:
                service = Service()
                driver = webdriver.Edge(service=service, options=edge_options)
            except Exception as e:
                logger.error(f"EdgeDriver bulunamadı: {str(e)}")
                self.add_error("EdgeDriver bulunamadı - PATH'e ekleyin")
                return None
            
            # Pencere boyutunu başlangıçta ayarla
            driver.set_window_rect(0, 0, 800, 600)
            
            # User agent ayarla
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info(f"Edge driver başlatıldı: {profile_name}")
            self.add_log(f"Driver başlatıldı: {profile_name}")
            
            return driver
            
        except Exception as e:
            logger.error(f"Edge driver başlatılamadı ({profile_name}): {str(e)}")
            self.add_error(f"Driver hatası ({profile_name}): {str(e)}")
            return None
            
    def open_link_in_driver(self, driver, link_id, link_data, profile_name):
        """Belirtilen driver'da linki aç"""
        try:
            url = link_data['url']
            name = link_data['name']
            
            if not url or not url.startswith(('http://', 'https://')):
                logger.warning(f"Geçersiz URL: {url}")
                self.add_error(f"Geçersiz URL: {url}")
                return False
            
            # Sayfayı yükle
            driver.get(url)
            
            # Sayfanın yüklendiğini kontrol et
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception as e:
                logger.warning(f"Sayfa yüklenemedi: {url}")
                self.add_error(f"Sayfa yüklenemedi: {name}")
                return False
                
            logger.info(f"{profile_name}: {name} (ID: {link_id}) açıldı")
            self.add_log(f"{profile_name}: {name} açıldı")
            
            # Linki aktif olarak işaretle
            self.links[link_id]['status'] = 'active'
            
            return True
                
        except Exception as e:
            logger.error(f"Link açılırken hata ({profile_name}): {str(e)}")
            self.add_error(f"Link açma hatası ({profile_name}): {str(e)}")
            return False
            
    def position_window(self, driver, position_index):
        """Edge penceresini belirtilen konuma yerleştir"""
        try:
            if position_index >= len(self.window_positions):
                logger.warning(f"Konum indeksi geçersiz: {position_index}")
                return False
                
            pos = self.window_positions[position_index]
            
            # Selenium ile pencereyi konumlandır
            driver.set_window_rect(pos["x"], pos["y"], pos["width"], pos["height"])
            
            # Kısa bir bekleme
            time.sleep(0.5)
            
            logger.info(f"Pencere konumlandırıldı: {pos['x']},{pos['y']} ({pos['width']}x{pos['height']})")
            self.add_log(f"Pencere konumlandırıldı: {position_index + 1}")
            return True
        
        except Exception as e:
            logger.error(f"Pencere konumlandırılamadı: {str(e)}")
            self.add_error(f"Pencere konumlandırma hatası: {str(e)}")
            return False
    
    def start_link(self, link_id_or_url, profile_id=None, all_profiles=False):
        """Belirtilen linki başlat"""
        # Profilleri yükle
        if not self.profiles:
            self.load_profiles()
            
        if not self.profiles:
            logger.error("Hiç profil bulunamadı")
            self.add_error("Hiç profil bulunamadı")
            return {
                "success": False,
                "message": "Hiç profil bulunamadı"
            }
        
        # Link ID veya URL'den link bilgisini bul
        link_id = None
        link_data = None
        
        # Doğrudan link ID ise
        if link_id_or_url in self.links:
            link_id = link_id_or_url
            link_data = self.links[link_id]
        else:
            # URL ise eşleşen linki bul
            for lid, data in self.links.items():
                if data['url'] == link_id_or_url:
                    link_id = lid
                    link_data = data
                    break
                    
            # Eşleşme bulunamadıysa ve URL formatındaysa yeni link olarak ekle
            if not link_id and link_id_or_url.startswith(('http://', 'https://')):
                new_id = str(len(self.links) + 1)
                self.links[new_id] = {
                    'name': f'Yayın {new_id}',
                    'url': link_id_or_url,
                    'status': 'inactive'
                }
                self.save_links()
                link_id = new_id
                link_data = self.links[new_id]
                logger.info(f"Yeni link eklendi: {link_id_or_url} (ID: {new_id})")
                self.add_log(f"Yeni link eklendi: ID {new_id}")
        
        if not link_id or not link_data:
            logger.error(f"Link bulunamadı: {link_id_or_url}")
            self.add_error(f"Link bulunamadı: {link_id_or_url}")
            return {
                "success": False,
                "message": f"Link bulunamadı: {link_id_or_url}"
            }
        
        # Profil seçimi
        profiles_to_use = []
        
        if all_profiles:
            # Tüm profillerde aç
            for i, profile in enumerate(self.profiles):
                profile_id_str = str(i)
                # Bu profilde bu link zaten açık mı kontrol et
                if not any(al[0] == link_id and al[1] == profile_id_str for al in self.active_links):
                    profiles_to_use.append((profile, profile_id_str))
        elif profile_id is not None:
            # Belirli profilde aç
            try:
                profile_index = int(profile_id)
                if 0 <= profile_index < len(self.profiles):
                    profile_id_str = str(profile_index)
                    # Bu profilde bu link zaten açık mı kontrol et
                    if not any(al[0] == link_id and al[1] == profile_id_str for al in self.active_links):
                        profiles_to_use.append((self.profiles[profile_index], profile_id_str))
                    else:
                        error_msg = f"Link bu profilde zaten aktif: {self.profiles[profile_index]['name']}"
                        self.add_error(error_msg)
                        return {
                            "success": False,
                            "message": error_msg
                        }
                else:
                    error_msg = f"Geçersiz profil ID: {profile_id}"
                    self.add_error(error_msg)
                    return {
                        "success": False,
                        "message": error_msg
                    }
            except ValueError:
                error_msg = f"Geçersiz profil ID formatı: {profile_id}"
                self.add_error(error_msg)
                return {
                    "success": False,
                    "message": error_msg
                }
        else:
            # Varsayılan davranış: tüm profillerde aç
            for i, profile in enumerate(self.profiles):
                profile_id_str = str(i)
                # Bu profilde bu link zaten açık mı kontrol et
                if not any(al[0] == link_id and al[1] == profile_id_str for al in self.active_links):
                    profiles_to_use.append((profile, profile_id_str))
        
        if not profiles_to_use:
            error_msg = "Kullanılabilir profil bulunamadı veya link tüm profillerde zaten aktif"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
        
        success_count = 0
        failed_profiles = []
        
        for profile, profile_id_str in profiles_to_use:
            # Edge driver oluştur
            driver = self.create_edge_driver(profile['path'], profile['name'])
            if not driver:
                failed_profiles.append(profile['name'])
                continue
                
            # Linki aç
            if self.open_link_in_driver(driver, link_id, link_data, profile['name']):
                # Pencere konumlarını hesapla
                active_count = len(self.drivers) + 1
                self.window_positions = self.calculate_window_positions(active_count)
                
                # Mevcut pencereleri yeniden konumlandır
                for i, driver_info in enumerate(self.drivers):
                    self.position_window(driver_info['driver'], i)
                    
                # Yeni pencereyi konumlandır
                self.position_window(driver, len(self.drivers))
                
                # Driver'ı kaydet
                self.drivers.append({
                    'driver': driver,
                    'profile_name': profile['name'],
                    'profile_id': profile_id_str,
                    'link_id': link_id
                })
                
                # Active links'e ekle
                self.active_links.append((link_id, profile_id_str))
                success_count += 1
            else:
                # Başarısız olursa driver'ı kapat
                try:
                    driver.quit()
                except:
                    pass
                failed_profiles.append(profile['name'])
        
        # Status thread'i başlat
        if self.drivers and (not self.status_thread or not self.status_thread.is_alive()):
            self.start_status_thread()
        
        # Sonuç mesajı
        if success_count > 0:
            message = f"Link {success_count} profilde başlatıldı: {link_data['name']} (ID: {link_id})"
            if failed_profiles:
                message += f". Başarısız profiller: {', '.join(failed_profiles)}"
            self.add_log(f"Link başlatıldı: {link_data['name']} ({success_count} profil)")
            return {
                "success": True,
                "message": message
            }
        else:
            error_msg = f"Link hiçbir profilde başlatılamadı: {link_data['name']} (ID: {link_id})"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def stop_all(self):
        """Tüm aktif linkleri durdur"""
        if not self.drivers:
            logger.info("Aktif link yok")
            self.add_log("Aktif link yok")
            return {
                "success": True,
                "message": "Aktif link yok"
            }
            
        count = len(self.drivers)
        self.cleanup_drivers()
        self.add_log(f"{count} aktif link durduruldu")
        
        return {
            "success": True,
            "message": f"{count} aktif link durduruldu"
        }
        
    def stop_link(self, link_id_or_url, profile_id=None):
        """Belirtilen linki durdur"""
        # Link ID veya URL'den link bilgisini bul
        link_id = None
        
        # Doğrudan link ID ise
        if link_id_or_url in self.links:
            link_id = link_id_or_url
        else:
            # URL ise eşleşen linki bul
            for lid, data in self.links.items():
                if data['url'] == link_id_or_url:
                    link_id = lid
                    break
        
        if not link_id:
            error_msg = f"Link bulunamadı: {link_id_or_url}"
            logger.error(error_msg)
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
        
        # Aktif link kontrolü ve profil filtreleme
        active_entries = [(lid, pid) for lid, pid in self.active_links if lid == link_id]
        
        if not active_entries:
            error_msg = f"Link aktif değil: {link_id}"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
        
        # Profil ID belirtilmişse filtrele
        if profile_id is not None:
            active_entries = [(lid, pid) for lid, pid in active_entries if pid == str(profile_id)]
            if not active_entries:
                error_msg = f"Link belirtilen profilde aktif değil: {link_id} (Profil: {profile_id})"
                self.add_error(error_msg)
                return {
                    "success": False,
                    "message": error_msg
                }
        
        # Driver'ları bul ve kapat
        stopped_count = 0
        for link_id_to_stop, profile_id_to_stop in active_entries:
            for i, driver_info in enumerate(list(self.drivers)):
                if driver_info['link_id'] == link_id_to_stop and driver_info['profile_id'] == profile_id_to_stop:
                    try:
                        driver_info['driver'].quit()
                    except:
                        pass
                        
                    self.drivers.remove(driver_info)
                    self.active_links.remove((link_id_to_stop, profile_id_to_stop))
                    stopped_count += 1
                    break
        
        # Pencere konumlarını güncelle
        if self.drivers:
            self.window_positions = self.calculate_window_positions(len(self.drivers))
            for j, d_info in enumerate(self.drivers):
                self.position_window(d_info['driver'], j)
        
        # Link durumunu güncelle
        if not any(al[0] == link_id for al in self.active_links):
            self.links[link_id]['status'] = 'inactive'
        
        success_msg = f"Link {stopped_count} profilde durduruldu: {self.links[link_id]['name']} (ID: {link_id})"
        self.add_log(f"Link durduruldu: {self.links[link_id]['name']} ({stopped_count} profil)")
        
        return {
            "success": True,
            "message": success_msg
        }
    
    def add_link(self, url, name=None):
        """Yeni link ekle"""
        # URL kontrolü
        if not url.startswith(('http://', 'https://')):
            error_msg = "Geçersiz URL formatı"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
            
        # Mevcut link kontrolü
        for link_id, link_data in self.links.items():
            if link_data['url'] == url:
                error_msg = f"Bu URL zaten kayıtlı (ID: {link_id})"
                self.add_error(error_msg)
                return {
                    "success": False,
                    "message": error_msg
                }
                
        # Yeni link ID'si
        new_id = str(len(self.links) + 1)
        
        # İsim belirtilmemişse varsayılan isim
        if not name:
            name = f"Yayın {new_id}"
            
        # Linki ekle
        self.links[new_id] = {
            'name': name,
            'url': url,
            'status': 'inactive'
        }
        
        # Linkleri kaydet
        if self.save_links():
            success_msg = f"Link eklendi: {name} (ID: {new_id})"
            self.add_log(success_msg)
            return {
                "success": True,
                "message": success_msg,
                "link_id": new_id
            }
        else:
            # Kaydetme başarısız olursa linki kaldır
            del self.links[new_id]
            error_msg = "Link eklenemedi: Kaydetme hatası"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def remove_link(self, link_id_or_url):
        """Link sil"""
        # Link ID veya URL'den link bilgisini bul
        link_id = None
        
        # Doğrudan link ID ise
        if link_id_or_url in self.links:
            link_id = link_id_or_url
        else:
            # URL ise eşleşen linki bul
            for lid, data in self.links.items():
                if data['url'] == link_id_or_url:
                    link_id = lid
                    break
        
        if not link_id:
            error_msg = f"Link bulunamadı: {link_id_or_url}"
            logger.error(error_msg)
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
            
        # Link aktifse önce durdur
        if any(al[0] == link_id for al in self.active_links):
            self.stop_link(link_id)
            
        # Linki sil
        link_name = self.links[link_id]['name']
        del self.links[link_id]
        
        # Linkleri kaydet
        if self.save_links():
            success_msg = f"Link silindi: {link_name} (ID: {link_id})"
            self.add_log(success_msg)
            return {
                "success": True,
                "message": success_msg
            }
        else:
            # Kaydetme başarısız olursa linki geri ekle
            self.links[link_id] = {
                'name': link_name,
                'url': link_id_or_url,
                'status': 'inactive'
            }
            error_msg = "Link silinemedi: Kaydetme hatası"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def set_check_interval(self, minutes):
        """Kontrol aralığını değiştir"""
        try:
            minutes = int(minutes)
            if minutes < 1:
                error_msg = "Kontrol aralığı en az 1 dakika olmalıdır"
                self.add_error(error_msg)
                return {
                    "success": False,
                    "message": error_msg
                }
                
            self.check_interval = minutes * 60
            self.save_config()
            
            success_msg = f"Kontrol aralığı {minutes} dakika olarak ayarlandı"
            self.add_log(success_msg)
            return {
                "success": True,
                "message": success_msg
            }
        except ValueError:
            error_msg = "Geçersiz değer: Dakika sayısal olmalıdır"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def get_status(self):
        """Program durumunu döndür"""
        active_links = []
        for link_id, profile_id in self.active_links:
            if link_id in self.links:
                profile_name = "Bilinmeyen"
                try:
                    profile_index = int(profile_id)
                    if 0 <= profile_index < len(self.profiles):
                        profile_name = self.profiles[profile_index]['name']
                except:
                    pass
                    
                active_links.append({
                    'id': link_id,
                    'name': self.links[link_id]['name'],
                    'url': self.links[link_id]['url'],
                    'status': self.links[link_id]['status'],
                    'profile_id': profile_id,
                    'profile_name': profile_name
                })
                
        return {
            "success": True,
            "active_count": len(self.active_links),
            "total_count": len(self.links),
            "check_interval": self.check_interval // 60,  # Dakika cinsinden
            "active_links": active_links,
            "last_status_check": self.last_status_check
        }
    
    def get_all_links(self):
        """Tüm linkleri döndür"""
        links_list = []
        for link_id, link_data in self.links.items():
            links_list.append({
                'id': link_id,
                'name': link_data['name'],
                'url': link_data['url'],
                'status': link_data['status']
            })
            
        return {
            "success": True,
            "links": links_list
        }
    
    def restart_all(self):
        """Tüm aktif linkleri yeniden başlat"""
        if not self.active_links:
            msg = "Yeniden başlatılacak aktif link yok"
            self.add_log(msg)
            return {
                "success": True,
                "message": msg
            }
            
        # Mevcut aktif linkleri kaydet
        links_to_restart = list(self.active_links)
        
        # Tüm linkleri durdur
        self.cleanup_drivers()
        
        # Linkleri yeniden başlat
        success_count = 0
        failed_count = 0
        
        for link_id, profile_id in links_to_restart:
            result = self.start_link(link_id, profile_id)
            if result['success']:
                success_count += 1
            else:
                failed_count += 1
                
        success_msg = f"Yeniden başlatma tamamlandı. Başarılı: {success_count}, Başarısız: {failed_count}"
        self.add_log(success_msg)
        return {
            "success": True,
            "message": success_msg
        }
    
    def reposition_windows(self):
        """Tüm açık pencereleri yeniden konumlandır"""
        if not self.drivers:
            error_msg = "Konumlandırılacak açık pencere yok"
            self.add_error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
            
        # Pencere konumlarını yeniden hesapla
        self.window_positions = self.calculate_window_positions(len(self.drivers))
        
        # Tüm pencereleri yeniden konumlandır
        repositioned_count = 0
        for i, driver_info in enumerate(self.drivers):
            if self.position_window(driver_info['driver'], i):
                repositioned_count += 1
                
        success_msg = f"{repositioned_count} pencere yeniden konumlandırıldı"
        self.add_log(success_msg)
        return {
            "success": True,
            "message": success_msg
        }
    
    def get_profiles(self):
        """Tüm profilleri döndür"""
        profiles_list = []
        for i, profile in enumerate(self.profiles):
            profiles_list.append({
                'id': str(i),
                'name': profile['name'],
                'path': profile['path']
            })
            
        return {
            "success": True,
            "profiles": profiles_list
        }
    
    def get_logs(self, lines=10):
        """Son log kayıtlarını döndür"""
        try:
            log_file = f"logs/betterkick_tool_{datetime.now().strftime('%Y%m%d')}.log"
            if not os.path.exists(log_file):
                return {
                    "success": False,
                    "message": "Log dosyası bulunamadı"
                }
                
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                
            # Son N satırı al
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            return {
                "success": True,
                "logs": [line.strip() for line in recent_lines]
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Log dosyası okunurken hata: {str(e)}"
            }
    
    def cleanup_drivers(self):
        """Sadece driver'ları temizle, programı kapatma"""
        logger.info("Edge driver'lar kapatılıyor...")
        self.add_log("Tüm driver'lar kapatılıyor")
        for driver_info in self.drivers:
            try:
                driver_info['driver'].quit()
            except:
                pass
                
        self.drivers.clear()
        self.active_links.clear()
        
        # Tüm linkleri inaktif olarak işaretle
        for link_id in self.links:
            self.links[link_id]['status'] = 'inactive'
    
    def check_link_status(self):
        """Aktif linklerin durumunu kontrol et"""
        logger.info("Link durumları kontrol ediliyor...")
        self.add_log("Link durumları kontrol ediliyor")
        self.last_status_check = int(time.time())
        
        for driver_info in list(self.drivers):  # Kopyasını al çünkü içeriği değişebilir
            driver = driver_info['driver']
            link_id = driver_info['link_id']
            profile_id = driver_info['profile_id']
            profile_name = driver_info['profile_name']
            
            try:
                # Tarayıcı hala açık mı kontrol et
                driver.current_url
                
                # Sayfa yüklenmiş mi kontrol et
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    logger.info(f"Link aktif: {self.links[link_id]['name']} (ID: {link_id}, Profil: {profile_name})")
                except:
                    logger.warning(f"Sayfa yüklenemedi: {self.links[link_id]['name']} (ID: {link_id}, Profil: {profile_name})")
                    # Sayfayı yenile
                    driver.refresh()
                    
            except Exception as e:
                logger.error(f"Tarayıcı kapanmış veya hata vermiş: {str(e)}")
                self.add_error(f"Tarayıcı hatası: {profile_name}")
                
                # Driver'ı listeden kaldır
                self.drivers.remove(driver_info)
                
                if (link_id, profile_id) in self.active_links:
                    self.active_links.remove((link_id, profile_id))
                    
                if link_id in self.links:
                    # Eğer bu link başka profillerde de açık değilse error olarak işaretle
                    if not any(al[0] == link_id for al in self.active_links):
                        self.links[link_id]['status'] = 'error'
                
                # Yeniden başlat
                logger.info(f"Link yeniden başlatılıyor: {self.links[link_id]['name']} (ID: {link_id}, Profil: {profile_name})")
                self.add_log(f"Link yeniden başlatılıyor: {profile_name}")
                self.start_link(link_id, profile_id)
    
    def start_status_thread(self):
        """Durum kontrol thread'ini başlat"""
        def status_worker():
            while self.running and self.drivers:
                time.sleep(self.check_interval)
                if self.running and self.drivers:
                    self.check_link_status()
        
        self.status_thread = threading.Thread(target=status_worker, daemon=True)
        self.status_thread.start()
        logger.info(f"Durum kontrol thread'i başlatıldı (kontrol aralığı: {self.check_interval//60} dakika)")
        self.add_log(f"Status thread başlatıldı ({self.check_interval//60}dk)")
    
    def cleanup(self):
        """Tüm Edge driver'ları kapat ve programı sonlandır"""
        self.cleanup_drivers()
        self.running = False

    def validate_profiles(self):
        """Profillerin var olup olmadığını kontrol et"""
        valid_profiles = []
        
        for profile in self.profiles:
            profile_path = profile['path']
            
            # Profil dizininin var olup olmadığını kontrol et
            if os.path.exists(profile_path):
                # Preferences dosyasının var olup olmadığını kontrol et
                prefs_file = os.path.join(profile_path, 'Preferences')
                if os.path.exists(prefs_file):
                    valid_profiles.append(profile)
                    logger.info(f"✅ Geçerli profil: {profile['name']} - {profile_path}")
                    self.add_log(f"✅ Geçerli profil: {profile['name']}")
                else:
                    logger.warning(f"⚠️ Profil mevcut ama kullanılmamış: {profile['name']} - {profile_path}")
                    self.add_error(f"Profil kullanılmamış: {profile['name']}")
                    logger.warning("Bu profilde Edge'i en az bir kez açıp ayarları tamamlayın")
            else:
                logger.error(f"❌ Profil bulunamadı: {profile['name']} - {profile_path}")
                self.add_error(f"Profil bulunamadı: {profile['name']}")
                logger.error("Bu profili Edge'de oluşturun veya yolu düzeltin")
        
        if not valid_profiles:
            logger.error("Hiç geçerli profil bulunamadı!")
            self.add_error("Hiç geçerli profil bulunamadı!")
            logger.error("Lütfen Edge'de profilleri oluşturun ve data/profiles.json dosyasını güncelleyin")
            return False
        
        self.profiles = valid_profiles
        logger.info(f"Toplam {len(valid_profiles)} geçerli profil yüklendi")
        self.add_log(f"Toplam {len(valid_profiles)} geçerli profil yüklendi")
        return True

    def create_dashboard(self):
        """Ana dashboard oluştur"""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="left", ratio=3),
            Layout(name="right", ratio=2)
        )
        
        layout["left"].split_column(
            Layout(name="status", size=8),
            Layout(name="links")
        )
        
        layout["right"].split_column(
            Layout(name="profiles", size=8),
            Layout(name="bottom")
        )
        
        layout["bottom"].split_column(
            Layout(name="errors", size=8),
            Layout(name="logs")
        )
        
        return layout

    def update_header(self):
        """Header panelini güncelle"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = int(time.time() - self.last_status_check) if self.last_status_check else 0
        
        header_text = Text()
        header_text.append("🚀 BetterKick Tool", style="bold magenta")
        header_text.append(f" | {current_time}", style="dim")
        header_text.append(f" | Uptime: {uptime}s", style="dim")
        header_text.append(f" | API: Port 5000", style="bright_green")
        
        return Panel(
            Align.center(header_text),
            box=box.ROUNDED,
            style="bright_blue"
        )

    def update_status(self):
        """Status panelini güncelle"""
        table = Table(title="📊 Sistem Durumu", box=box.ROUNDED)
        table.add_column("Metrik", style="cyan", no_wrap=True)
        table.add_column("Değer", style="magenta")
        table.add_column("Durum", justify="center")
        
        # Aktif link sayısı
        active_count = len(self.active_links)
        status_icon = "🟢" if active_count > 0 else "⚪"
        table.add_row("Aktif Linkler", str(active_count), status_icon)
        
        # Toplam link sayısı
        table.add_row("Toplam Linkler", str(len(self.links)), "📋")
        
        # Profil sayısı
        table.add_row("Profiller", str(len(self.profiles)), "👤")
        
        # Kontrol aralığı
        table.add_row("Kontrol Aralığı", f"{self.check_interval // 60} dakika", "⏰")
        
        # API durumu
        api_status = "🟢 Aktif" if self.running else "🔴 Pasif"
        table.add_row("API Sunucusu", "Port 5000", api_status)
        
        # Hata sayısı
        error_count = len(self.last_errors)
        error_icon = "🔴" if error_count > 0 else "🟢"
        table.add_row("Son Hatalar", str(error_count), error_icon)
        
        return table

    def update_links(self):
        """Links panelini güncelle"""
        table = Table(title="🔗 Linkler", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("İsim", style="white", width=20)
        table.add_column("Durum", justify="center", width=8)
        table.add_column("Profiller", style="dim", width=15)
        
        for link_id, link_data in self.links.items():
            # Status icon
            if link_data['status'] == 'active':
                status = "🟢 Aktif"
            elif link_data['status'] == 'error':
                status = "🔴 Hata"
            else:
                status = "⚪ Pasif"
            
            # Bu linkin hangi profillerde açık olduğunu bul
            active_profiles = []
            for al_link_id, al_profile_id in self.active_links:
                if al_link_id == link_id:
                    try:
                        profile_index = int(al_profile_id)
                        if 0 <= profile_index < len(self.profiles):
                            active_profiles.append(self.profiles[profile_index]['name'][:8])
                    except:
                        pass
            
            profiles_text = ", ".join(active_profiles) if active_profiles else "-"
            
            table.add_row(
                link_id,
                link_data['name'][:18] + "..." if len(link_data['name']) > 18 else link_data['name'],
                status,
                profiles_text
            )
        
        return table

    def update_profiles(self):
        """Profiles panelini güncelle"""
        table = Table(title="👤 Profiller", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("İsim", style="white", width=15)
        table.add_column("Durum", justify="center", width=8)
        
        for i, profile in enumerate(self.profiles):
            # Bu profilde aktif link var mı kontrol et
            has_active = any(al[1] == str(i) for al in self.active_links)
            status = "🟢 Aktif" if has_active else "⚪ Boş"
            
            table.add_row(
                str(i),
                profile['name'][:13] + "..." if len(profile['name']) > 13 else profile['name'],
                status
            )
        
        return table

    def update_errors(self):
        """Errors panelini güncelle"""
        if not self.last_errors:
            error_text = "Henüz hata yok 🎉"
        else:
            error_text = "\n".join(self.last_errors[-5:])  # Son 5 hata
        
        return Panel(
            error_text,
            title="🔴 Son Hatalar",
            box=box.ROUNDED,
            style="red"
        )

    def update_logs(self):
        """Logs panelini güncelle"""
        if not self.last_logs:
            log_text = "Henüz log yok"
        else:
            log_text = "\n".join(self.last_logs[-5:])  # Son 5 log
        
        return Panel(
            log_text,
            title="📝 Son Loglar",
            box=box.ROUNDED,
            style="dim"
        )

    def update_footer(self):
        """Footer panelini güncelle"""
        if self.show_help_panel:
            help_text = Text()
            help_text.append("🆘 YARDIM MENÜSÜ", style="bold yellow")
            help_text.append("\n[Q] Çıkış | [R] Yenile | [S] Durdur | [P] Yeniden Konumlandır | [ESC] Yardımı Kapat", style="dim")
            help_text.append("\nDiscord Bot: !start, !stop, !restart, !status, !profiles, !links", style="cyan")
            help_text.append("\nAPI: GET /status, POST /start, POST /stop, GET /profiles", style="green")
            
            return Panel(
                help_text,
                title="🆘 Yardım",
                box=box.DOUBLE,
                style="yellow"
            )
        else:
            footer_text = Text()
            footer_text.append("Kısayollar: ", style="bold")
            footer_text.append("[Q]", style="bold red")
            footer_text.append(" Çıkış | ", style="dim")
            footer_text.append("[R]", style="bold green")
            footer_text.append(" Yenile | ", style="dim")
            footer_text.append("[S]", style="bold yellow")
            footer_text.append(" Durdur | ", style="dim")
            footer_text.append("[P]", style="bold blue")
            footer_text.append(" Yeniden Konumlandır | ", style="dim")
            footer_text.append("[H]", style="bold magenta")
            footer_text.append(" Yardım", style="dim")
            
            return Panel(
                Align.center(footer_text),
                box=box.ROUNDED,
                style="bright_black"
            )

    def start_gui(self):
        """GUI'yi başlat"""
        def gui_worker():
            layout = self.create_dashboard()
            
            with Live(layout, refresh_per_second=2, screen=True) as live:
                while self.gui_enabled and self.running:
                    try:
                        # Layout'u güncelle
                        layout["header"].update(self.update_header())
                        layout["status"].update(self.update_status())
                        layout["links"].update(self.update_links())
                        layout["profiles"].update(self.update_profiles())
                        layout["errors"].update(self.update_errors())
                        layout["logs"].update(self.update_logs())
                        layout["footer"].update(self.update_footer())
                        
                        # Keyboard input kontrolü
                        if keyboard.is_pressed('q'):
                            self.console.print("\n[bold red]Çıkış yapılıyor...[/bold red]")
                            self.running = False
                            self.gui_enabled = False
                            break
                        elif keyboard.is_pressed('r'):
                            self.console.print("\n[bold green]Yenileniyor...[/bold green]")
                            time.sleep(0.5)
                        elif keyboard.is_pressed('s'):
                            self.console.print("\n[bold yellow]Tüm linkler durduruluyor...[/bold yellow]")
                            self.stop_all()
                            time.sleep(0.5)
                        elif keyboard.is_pressed('p'):
                            self.console.print("\n[bold blue]Pencereler yeniden konumlandırılıyor...[/bold blue]")
                            self.reposition_windows()
                            time.sleep(0.5)
                        elif keyboard.is_pressed('h'):
                            self.show_help_panel = True
                            time.sleep(0.5)
                        elif keyboard.is_pressed('esc'):
                            self.show_help_panel = False
                            time.sleep(0.5)
                        
                        time.sleep(0.1)
                        
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        logger.error(f"GUI hatası: {str(e)}")
                        self.add_error(f"GUI hatası: {str(e)}")
                        break
        
        self.gui_thread = threading.Thread(target=gui_worker, daemon=True)
        self.gui_thread.start()
    
    def run(self):
        """Ana program döngüsü"""
        # Başlangıç mesajı
        self.console.print(Panel(
            "[bold cyan]🚀 BetterKick Tool Başlatılıyor...[/bold cyan]\n[dim]Mükemmel Stream Management Sistemi[/dim]",
            box=box.DOUBLE
        ))
        
        # Dosyaları yükle
        with self.console.status("[bold green]Yapılandırma dosyaları yükleniyor..."):
            self.load_profiles()
            self.load_links()
        
        # Profilleri doğrula
        with self.console.status("[bold green]Profiller doğrulanıyor..."):
            if not self.validate_profiles():
                self.console.print("[bold red]❌ Program durduruluyor: Geçerli profil bulunamadı[/bold red]")
                return
        
        # GUI'yi başlat
        self.console.print("[bold green]✅ GUI başlatılıyor...[/bold green]")
        self.start_gui()
        
        # Ana döngü
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

# Flask API sunucusu
app = Flask(__name__)
manager = BetterKickTool()

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(manager.get_status())

@app.route('/links', methods=['GET'])
def get_links():
    return jsonify(manager.get_all_links())

@app.route('/start', methods=['POST'])
def start_link():
    data = request.json
    link_id_or_url = data.get('link')
    profile_id = data.get('profile_id')
    all_profiles = data.get('all_profiles', False)
    if not link_id_or_url:
        return jsonify({"success": False, "message": "Link belirtilmedi"})
    return jsonify(manager.start_link(link_id_or_url, profile_id, all_profiles))

@app.route('/stop', methods=['POST'])
def stop_link():
    data = request.json
    link_id_or_url = data.get('link')
    profile_id = data.get('profile_id')
    if link_id_or_url:
        return jsonify(manager.stop_link(link_id_or_url, profile_id))
    else:
        return jsonify(manager.stop_all())

@app.route('/links', methods=['POST'])
def add_link():
    data = request.json
    url = data.get('url')
    name = data.get('name')
    if not url:
        return jsonify({"success": False, "message": "URL belirtilmedi"})
    return jsonify(manager.add_link(url, name))

@app.route('/links', methods=['DELETE'])
def remove_link():
    data = request.json
    link_id_or_url = data.get('link')
    if not link_id_or_url:
        return jsonify({"success": False, "message": "Link belirtilmedi"})
    return jsonify(manager.remove_link(link_id_or_url))

@app.route('/interval', methods=['PUT'])
def set_interval():
    data = request.json
    minutes = data.get('minutes')
    if not minutes:
        return jsonify({"success": False, "message": "Dakika belirtilmedi"})
    return jsonify(manager.set_check_interval(minutes))

@app.route('/restart', methods=['POST'])
def restart_all():
    return jsonify(manager.restart_all())

@app.route('/reposition', methods=['POST'])
def reposition_windows():
    return jsonify(manager.reposition_windows())

@app.route('/profiles', methods=['GET'])
def get_profiles():
    return jsonify(manager.get_profiles())

@app.route('/logs', methods=['GET'])
def get_logs():
    lines = request.args.get('lines', 10, type=int)
    return jsonify(manager.get_logs(lines))

@app.route('/open', methods=['POST'])
def open_link():
    data = request.json
    link_id_or_url = data.get('link')
    profile_id = data.get('profile_id')
    if not link_id_or_url:
        return jsonify({"success": False, "message": "Link belirtilmedi"})
    if profile_id is None:
        return jsonify({"success": False, "message": "Profil ID belirtilmedi"})
    return jsonify(manager.start_link(link_id_or_url, profile_id))

def start_api_server():
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == "__main__":
    # API sunucusunu ayrı bir thread'de başlat
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    
    # BetterKick Tool'u başlat
    manager.run()
