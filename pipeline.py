import sqlite3
import logging
import hashlib
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
DB_PATH = "concursos.db"

WA_URL = os.getenv("WHATSAPP_API_URL", "")
WA_KEY = os.getenv("WHATSAPP_API_KEY", "")
WA_PHONE = os.getenv("WHATSAPP_PHONE", "")
AREAS_INTERESSE = ["administração", "logística", "gestão", "marketing"]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS concursos (
            id_unico TEXT PRIMARY KEY,
            fonte TEXT NOT NULL,
            campus TEXT,
            area_conhecimento TEXT,
            tipo_edital TEXT,
            data_limite_inscricao TEXT,
            url_edital TEXT,
            data_captura TEXT,
            notificado INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def compute_id(url, title):
    raw = url + "|" + title
    return hashlib.md5(raw.encode('utf-8')).hexdigest()

def save_records(records):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    added = 0
    for r in records:
        uid = compute_id(r['url'], r['title'])
        cursor.execute("SELECT id_unico FROM concursos WHERE id_unico=?", (uid,))
        if cursor.fetchone():
            continue
        cursor.execute("""
            INSERT INTO concursos (id_unico, fonte, campus, area_conhecimento, tipo_edital,
                                   data_limite_inscricao, url_edital, data_captura, notificado)
            VALUES (?,?,?,?,?,?,?,?,0)
        """, (uid, r['fonte'], r['campus'], r['area'], r['tipo'], r.get('data'), r['url'], timestamp))
        added += 1
    conn.commit()
    conn.close()
    logging.info("💾 %d novos editais salvos no banco.", added)

def send_whatsapp_alerts():
    if not WA_URL or not WA_KEY or not WA_PHONE:
        logging.warning("⚠️ WhatsApp não configurado. Preencha o arquivo .env.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM concursos WHERE notificado=0")
    rows = cursor.fetchall()
    
    enviados = 0
    for row in rows:
        area = row[3] or ""
        fonte = row[1] or ""
        
        match_area = any(a in area.lower() for a in AREAS_INTERESSE)
        match_private = "particular" in fonte.lower()
        
        if not (match_area or match_private):
            continue
        
        dias = None
        if row[5]:
            try:
                dias = (datetime.strptime(row[5], '%Y-%m-%d') - datetime.now()).days
            except:
                pass
        
        urgencia = "🔥 URGENTE (48h!)" if dias is not None and dias <= 2 else "📅 Novo Edital"
        msg = (urgencia + "\n" +
               "🏛️ " + fonte + " | 📍 " + str(row[2]) + "\n" +
               "📖 " + area + " (" + str(row[4]) + ")\n" +
               "⏰ Encerra: " + (row[5] or "A definir") + "\n" +
               "🔗 " + str(row[6]))
        
        payload = {"phone": WA_PHONE, "message": msg}
        headers = {"Authorization": "Bearer " + WA_KEY, "Content-Type": "application/json"}
        
        try:
            resp = requests.post(WA_URL, json=payload, headers=headers, timeout=10)
            if resp.status_code in [200, 201, 202]:
                cursor.execute("UPDATE concursos SET notificado=1 WHERE id_unico=?", (row[0],))
                enviados += 1
                logging.info("✅ WhatsApp enviado: %s", fonte)
            else:
                logging.warning("⚠️ API erro %d: %s", resp.status_code, resp.text[:100])
        except Exception as e:
            logging.error("❌ Erro HTTP: %s", str(e))
    
    conn.commit()
    conn.close()
    logging.info("📡 %d alertas processados.", enviados)

def scrape_cps():
    try:
        url = "https://www.cps.sp.gov.br/vagas/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True).lower()
            if any(k in txt for k in ['administração', 'logística', 'gestão']):
                results.append({'fonte':'Centro Paula Souza','campus':'Diversos','area':'Administração/Gestão',
                                'tipo':'Temporário/Efetivo','url':a['href'],'title':a.get_text(strip=True)})
        logging.info("[CPS] %d itens encontrados.", len(results))
        return results
    except Exception as e:
        logging.warning("[CPS] Erro: %s", str(e))
        return []

def scrape_ifsp():
    try:
        url = "https://portal.ifsp.edu.br/concursos-e-processos-seletivos"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True).lower()
            if 'administração' in txt or 'docente' in txt:
                if a['href'].startswith('http'):
                    full_url = a['href']
                else:
                    full_url = "https://portal.ifsp.edu.br" + a['href']
                results.append({'fonte':'IFSP','campus':'Vários','area':'Administração',
                                'tipo':'Efetivo','url':full_url,'title':a.get_text(strip=True)})
        logging.info("[IFSP] %d itens encontrados.", len(results))
        return results
    except Exception as e:
        logging.warning("[IFSP] Erro: %s", str(e))
        return []

def scrape_unifesp():
    try:
        url = "https://www.unifesp.br/concursos"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True).lower()
            if 'administração' in txt:
                if a['href'].startswith('http'):
                    full_url = a['href']
                else:
                    full_url = "https://www.unifesp.br" + a['href']
                results.append({'fonte':'UNIFESP','campus':'SP','area':'Administração',
                                'tipo':'Efetivo','url':full_url,'title':a.get_text(strip=True)})
        logging.info("[UNIFESP] %d itens encontrados.", len(results))
        return results
    except Exception as e:
        logging.warning("[UNIFESP] Erro: %s", str(e))
        return []

if __name__ == "__main__":
    logging.info("🚀 Iniciando pipeline...")
    init_db()
    
    all_edits = []
    all_edits += scrape_cps()
    all_edits += scrape_ifsp()
    all_edits += scrape_unifesp()
    
    if all_edits:
        save_records(all_edits)
    
    send_whatsapp_alerts()
    logging.info("✅ Pipeline concluído!")