from flask import Flask, render_template, request, jsonify
import threading
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import sys
import re
import json
import random
from urllib.parse import urlencode

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

class EbayRSSMonitor:
    def __init__(self):
        self.is_running = False
        self.found_auctions = set()
        self.logs = []
        self.auctions = []
        self.monitor_thread = None
        self.ending_time = 1

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 100:
            self.logs.pop(0)

    def add_auction(self, title, price, bids, url, time_left):
        auction = {
            'title': title,
            'price': price,
            'bids': bids,
            'url': url,
            'time_left': time_left,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
        self.auctions.insert(0, auction)
        if len(self.auctions) > 50:
            self.auctions.pop()

    def build_rss_url(self, keywords, min_price, max_price, min_bids):
        """Строит RSS URL для eBay поиска"""
        # Используем прямой URL поиска eBay с RSS параметром
        base_url = "https://www.ebay.com/sch/i.html"

        params = {}

        # Ключевые слова
        if keywords:
            params['_nkw'] = keywords

        # Цена
        if min_price > 0:
            params['_udlo'] = str(int(min_price))
        if max_price < 999999:
            params['_udhi'] = str(int(max_price))

        # Только аукционы
        params['LH_Auction'] = '1'

        # Сортировка по времени завершения
        params['_sop'] = '10'

        # RSS формат
        params['_rss'] = '1'

        url = f"{base_url}?{urlencode(params)}"
        return url

    def start_monitoring(self, keywords, min_price, max_price, min_bids, ending_time, interval):
        if self.is_running:
            return False

        self.is_running = True
        self.logs = []
        self.auctions = []
        self.ending_time = ending_time

        self.log("="*80)
        self.log("🚀 МОНИТОРИНГ eBay RSS ЗАПУЩЕН")
        self.log("="*80)

        if keywords:
            self.log(f"🔍 Ключевые слова: {keywords}")
        else:
            self.log(f"🔍 Поиск: ВСЕ аукционы")

        self.log(f"💰 Цена: ${min_price} - ${max_price}")
        self.log(f"📊 Минимум ставок: {min_bids}")
        self.log(f"⏱️  Время завершения: {ending_time} мин")
        self.log(f"⏱️  Интервал: {interval} сек")
        self.log("="*80 + "\n")

        self.monitor_thread = threading.Thread(
            target=self.monitor_loop,
            args=(keywords, min_price, max_price, min_bids, interval),
            daemon=True
        )
        self.monitor_thread.start()
        return True

    def stop_monitoring(self):
        self.is_running = False
        self.log("\n⏹️  Мониторинг остановлен.\n")

    def monitor_loop(self, keywords, min_price, max_price, min_bids, interval):
        while self.is_running:
            try:
                self.search_ebay_rss(keywords, min_price, max_price, min_bids)
                self.log(f"⏳ Следующая проверка через {interval} сек...\n")
                time.sleep(interval)
            except Exception as e:
                self.log(f"❌ Ошибка: {str(e)}")
                time.sleep(5)

    def search_ebay_rss(self, keywords, min_price, max_price, min_bids):
        try:
            if keywords:
                self.log(f"🔍 Поиск: '{keywords}'...")
            else:
                self.log(f"🔍 Поиск: ВСЕ аукционы...")

            # Строим URL поиска eBay
            if keywords:
                url = f"https://www.ebay.com/sch/i.html?_nkw={keywords}&LH_Auction=1&_sop=10"
            else:
                url = "https://www.ebay.com/sch/i.html?LH_Auction=1&_sop=10"

            if min_price > 0:
                url += f"&_udlo={int(min_price)}"
            if max_price < 999999:
                url += f"&_udhi={int(max_price)}"

            self.log(f"   📡 Загрузка страницы eBay...")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.ebay.com/',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                'DNT': '1',
            }

            response = None
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    self.log(f"   🔄 Попытка {attempt + 1}/{max_retries}...")

                    session = requests.Session()
                    session.verify = False

                    response = session.get(url, headers=headers, timeout=20)

                    if response.status_code == 403:
                        self.log(f"   ⚠️ 403 Forbidden - eBay блокирует запрос")
                        time.sleep(2)
                        continue

                    response.raise_for_status()
                    self.log(f"   ✓ Страница загружена ({len(response.content)} байт)")
                    break

                except Exception as e:
                    self.log(f"   ⚠️ Попытка {attempt + 1} ошибка: {str(e)[:60]}")
                    time.sleep(2)
                    continue

            if not response or response.status_code != 200:
                self.log(f"   ❌ Не удалось загрузить страницу после {max_retries} попыток")
                self.log(f"   💡 Совет: используйте прокси или попробуйте позже")
                return

            try:
                soup = BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                self.log(f"   ⚠️ Ошибка парсинга HTML: {str(e)}")
                return

            # Ищем карточки товаров (div с классом s-item)
            items = soup.find_all('div', {'class': 's-item'})

            if not items:
                self.log(f"   ⚠️ Результаты не найдены")
                return

            self.log(f"   ✓ Найдено {len(items)} аукционов")
            found_count = 0

            for item in items:
                try:
                    # Название
                    title_elem = item.find('span', {'role': 'heading'})
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)

                    # Цена
                    price_elem = item.find('span', {'class': 's-item__price'})
                    if not price_elem:
                        continue
                    price_text = price_elem.get_text(strip=True)
                    try:
                        price = float(re.sub(r'[^\d.]', '', price_text.split()[0]))
                    except:
                        continue

                    # Ставки
                    bids_elem = item.find('span', {'class': 's-item__bids'})
                    bids = 0
                    if bids_elem:
                        try:
                            bids_text = bids_elem.get_text(strip=True)
                            bids = int(re.sub(r'[^\d]', '', bids_text.split()[0]))
                        except:
                            bids = 0

                    # Ссылка
                    link_elem = item.find('a', {'class': 's-item__link'})
                    item_url = link_elem['href'] if link_elem else ''

                    # Время завершения
                    time_left = "N/A"

                    # Проверяем фильтры
                    if price >= min_price and price <= max_price and bids >= min_bids:
                        auction_id = f"{title}_{item_url}"
                        if auction_id not in self.found_auctions:
                            self.found_auctions.add(auction_id)
                            self.log(f"✅ НАЙДЕН: {title[:60]}... | ${price} | Ставок: {bids}")
                            self.add_auction(title, f"${price}", bids, item_url, time_left)
                            found_count += 1

                except Exception as e:
                    continue

            if found_count == 0:
                self.log(f"   Подходящих аукционов не найдено")

        except Exception as e:
            self.log(f"❌ Ошибка: {str(e)}")

    def check_ending_time(self, time_str):
        """Проверяет, заканчивается ли аукцион в течение ending_time минут"""
        try:
            # Для RSS обычно это дата публикации, поэтому просто возвращаем True
            # В реальности нужно парсить дату и сравнивать с текущим временем
            return True
        except:
            return False

monitor = EbayRSSMonitor()

@app.route('/')
def index():
    response = render_template('ebay_rss.html')
    response = app.make_response(response)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

@app.route('/api/start', methods=['POST'])
def start():
    try:
        data = request.json
        keywords = data.get('keywords', '')
        min_price = float(data.get('min_price', 0))
        max_price = float(data.get('max_price', 999999))
        min_bids = int(data.get('min_bids', 1))
        ending_time = int(data.get('ending_time', 1))
        interval = int(data.get('interval', 60))

        print(f"DEBUG: Starting eBay RSS monitoring with: keywords={keywords}, min_price={min_price}, max_price={max_price}, min_bids={min_bids}, ending_time={ending_time}, interval={interval}")
        success = monitor.start_monitoring(keywords, min_price, max_price, min_bids, ending_time, interval)
        return json.dumps({'success': success}, ensure_ascii=False)
    except Exception as e:
        print(f"DEBUG: Error in start(): {str(e)}")
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)

@app.route('/api/stop', methods=['POST'])
def stop():
    try:
        monitor.stop_monitoring()
        return json.dumps({'success': True}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)

@app.route('/api/status')
def status():
    try:
        return json.dumps({
            'running': monitor.is_running,
            'logs': monitor.logs[-20:],
            'auctions': monitor.auctions[:10]
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'error': str(e)}, ensure_ascii=False)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5002)
