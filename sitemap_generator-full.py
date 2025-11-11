import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
import os
import sys

class SitemapGenerator:
    def __init__(self, start_url, domain):
        self.start_url = start_url
        self.domain = domain
        self.visited = set()
        self.urls_data = defaultdict(lambda: {'lastmod': None, 'priority': 0.5})
        self.excluded_patterns = ['.pdf', '.jpg', '.png', '.gif', '.zip', '/search', '/login']
        
    def should_crawl(self, url):
        """Check if URL should be crawled"""
        parsed = urlparse(url)
        
        # Skip if not same domain
        if parsed.netloc != urlparse(self.domain).netloc:
            return False
            
        # Skip excluded patterns
        for pattern in self.excluded_patterns:
            if pattern in url.lower():
                return False
                
        # Skip fragments but allow query params if necessary
        if '#' in url:
            url = url.split('#')[0]  # Remove fragment
            
        # Optional: Skip certain query params (like tracking params)
        if '?' in url:
            # Remove tracking params but keep structural ones
            if any(x in url for x in ['utm_', 'fbclid', 'gclid']):
                return False
            
        return True
    
    def get_priority(self, url):
        """Determine priority based on URL structure"""
        path = urlparse(url).path.lower()
        
        if path in ['/', ''] or path == self.domain:
            return 1.0
        elif '/docs' in path:
            return 0.9
        elif '/blog' in path:
            return 0.8
        elif '/product' in path or '/features' in path:
            return 0.85
        else:
            return 0.7
    
    async def fetch_url(self, session, url):
        """Fetch URL with timeout"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as response:
                if response.status == 200 and 'text/html' in response.headers.get('content-type', ''):
                    return await response.text()
        except:
            pass
        return None
    
    async def extract_links(self, html, current_url):
        """Extract all links from HTML"""
        links = set()
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            for tag in soup.find_all(['a', 'link']):
                href = tag.get('href', '').strip()
                if href:
                    absolute_url = urljoin(current_url, href)
                    if self.should_crawl(absolute_url):
                        links.add(absolute_url)
        except:
            pass
        
        return links
    
    async def crawl(self, max_concurrent=5): 
        """Crawl website asynchronousl"""
        queue = asyncio.Queue()
        await queue.put(self.start_url)
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def worker(session):
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                if url in self.visited:
                    continue
                
                self.visited.add(url)
                print(f"Crawling: {url} ({len(self.visited)} URLs found)")
                
                async with semaphore:
                    html = await self.fetch_url(session, url)
                    
                    if html:
                        self.urls_data[url] = {
                            'lastmod': datetime.now().isoformat()[:10],
                            'priority': self.get_priority(url)
                        }
                        
                        links = await self.extract_links(html, url)
                        for link in links:
                            if link not in self.visited:
                                await queue.put(link)
        
        connector = aiohttp.TCPConnector(limit=max_concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            workers = [worker(session) for _ in range(max_concurrent)]
            await asyncio.gather(*workers)
    
    def generate_xml_sitemap(self):
        """Generate XML sitemap with proper formatting"""
        # Register namespaces
        ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        
        root = ET.Element('urlset')
        root.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        root.set('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation', 
                 'http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd')
        
        for url in sorted(self.urls_data.keys()):
            url_elem = ET.SubElement(root, 'url')
            
            loc = ET.SubElement(url_elem, 'loc')
            loc.text = url
            
            lastmod = ET.SubElement(url_elem, 'lastmod')
            lastmod.text = self.urls_data[url]['lastmod']
            
            priority = ET.SubElement(url_elem, 'priority')
            priority.text = f"{self.urls_data[url]['priority']:.2f}"
        
        # Build XML string with declaration
        xml_str = ET.tostring(root, encoding='unicode')
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        return xml_declaration + xml_str
    
    def generate_json_sitemap(self):
        """Generate JSON sitemap for tracking"""
        return json.dumps({
            'generated_at': datetime.now().isoformat(),
            'total_urls': len(self.urls_data),
            'urls': self.urls_data
        }, indent=2)
    
    def compare_with_previous(self, previous_json_path):
        """Compare with previous sitemap and return changes"""
        if not os.path.exists(previous_json_path):
            return {
                'new_urls': list(self.urls_data.keys()),
                'removed_urls': [],
                'updated_urls': []
            }
        
        with open(previous_json_path, 'r') as f:
            previous = json.load(f)
        
        previous_urls = set(previous['urls'].keys())
        current_urls = set(self.urls_data.keys())
        
        return {
            'new_urls': list(current_urls - previous_urls),
            'removed_urls': list(previous_urls - current_urls),
            'updated_urls': list(current_urls & previous_urls),
            'url_count_change': len(current_urls) - len(previous_urls)
        }
    
    def save_sitemaps(self, output_dir='sitemaps'):
        """Save XML and JSON sitemaps"""
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save XML sitemap
        xml_path = os.path.join(output_dir, 'sitemap.xml')
        with open(xml_path, 'w') as f:
            f.write(self.generate_xml_sitemap())
        
        # Save JSON sitemap
        json_path = os.path.join(output_dir, f'sitemap_{timestamp}.json')
        with open(json_path, 'w') as f:
            f.write(self.generate_json_sitemap())
        
        # Compare with previous and save changes
        previous_json = sorted([f for f in os.listdir(output_dir) if f.startswith('sitemap_') and f.endswith('.json')])
        if len(previous_json) > 1:
            previous_path = os.path.join(output_dir, previous_json[-2])
            changes = self.compare_with_previous(previous_path)
            
            changes_path = os.path.join(output_dir, f'changes_{timestamp}.json')
            with open(changes_path, 'w') as f:
                json.dump(changes, f, indent=2)
            
            print(f"\n📊 Changes Summary:")
            print(f"  New URLs: {len(changes['new_urls'])}")
            print(f"  Removed URLs: {len(changes['removed_urls'])}")
            print(f"  URL Count Change: {changes['url_count_change']:+d}")
        
        print(f"\n✅ Sitemaps saved:")
        print(f"  XML: {xml_path}")
        print(f"  JSON: {json_path}")
        print(f"  Total URLs: {len(self.urls_data)}")
        
        return xml_path, json_path


async def main():
    # Configuration
    START_URL = 'https://keploy.io'
    DOMAIN = 'https://keploy.io'
    OUTPUT_DIR = 'sitemaps'
    
    print("🚀 Starting Keploy Sitemap Generation...")
    print(f"Domain: {DOMAIN}")
    
    generator = SitemapGenerator(START_URL, DOMAIN)
    await generator.crawl(max_concurrent=10)
    
    generator.save_sitemaps(OUTPUT_DIR)
    
    print("\n✨ Sitemap generation complete!")


if __name__ == '__main__':
    asyncio.run(main())