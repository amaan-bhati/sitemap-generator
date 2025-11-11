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
    """
    Website crawler that generates XML/JSON sitemaps with proper URL normalization
    and hierarchical priority assignment.
    """
    
    def __init__(self, start_url, domain):
        """Initialize crawler with configuration."""
        self.start_url = start_url
        self.domain = domain
        self.visited = set()
        self.urls_data = defaultdict(lambda: {'lastmod': None, 'priority': 0.5})
        
        # Updated: Added .svg and other file types
        self.excluded_patterns = [
            '.pdf', '.jpg', '.png', '.gif', '.zip',  # File types
            '.svg',                                    # SVG files
            '.webp', '.ico', '.ttf', '.woff',        # Other file types
            '.jpeg', '.mp4', '.mp3', '.mov',         # Media files
            '/search', '/login', '/admin'            # URL patterns
        ]
    
    def normalize_url(self, url):
        """
        Normalize URL by removing fragments, query parameters, and trailing slashes.
        
        Examples:
            https://keploy.io/docs/glossary#section1 → https://keploy.io/docs/glossary
            https://keploy.io/docs/glossary?utm_source=x → https://keploy.io/docs/glossary
            https://keploy.io/docs/glossary/ → https://keploy.io/docs/glossary
        """
        if '#' in url:
            url = url.split('#')[0]
        if '?' in url:
            url = url.split('?')[0]
        url = url.rstrip('/')
        return url
    
    def should_crawl(self, url):
        """
        Determine if a URL should be crawled.
        
        Filters by:
        1. Domain (stay within allowed domain)
        2. Excluded patterns (skip files, login pages, etc.)
        """
        # FIRST: Normalize the URL
        url = self.normalize_url(url)
        
        # Parse URL components
        parsed = urlparse(url)
        
        # FILTER 1: Domain Check
        if parsed.netloc != urlparse(self.domain).netloc:
            return False
        
        # FILTER 2: Excluded Patterns
        for pattern in self.excluded_patterns:
            if pattern in url.lower():
                return False
        
        return True
    
    def get_priority(self, url):
        """
        Assign priority score to URL based on hierarchical content importance.
        
        Priority Tiers:
        1.00 - Homepage, main landing pages (/, /docs/, /blog)
        0.80 - Product pages, main blog categories, core how-to guides
        0.64 - Quickstarts, installation guides, blog tags, SDK docs
        0.51 - Concept pages, deep guides, blog posts, versioned docs
        0.41 - Old versioned docs (1.0.0), deep nested glossaries
        
        Args:
            url (str): URL to score
            
        Returns:
            float: Priority between 0.0 and 1.0
        """
        path = urlparse(url).path.lower()
        
        # ========== TIER 1: HOMEPAGE & MAIN SECTIONS (1.00) ==========
        # Entry points and critical landing pages
        if path in ['/', ''] or path == self.domain:
            return 1.0
        if path in ['/docs', '/docs/', '/blog', '/blog/']:
            return 1.0
        if '/gittogether' in path:
            return 1.0
        
        # ========== TIER 2A: PRODUCT & CATEGORY PAGES (0.80) ==========
        
        # Product/Feature pages (conversion-focused)
        if any(x in path for x in ['/pricing', '/api-testing', '/integration-testing', 
                                    '/unit-test-generator', '/contract-testing', 
                                    '/ai-code-generation', '/test-case-generator',
                                    '/test-data-generator', '/code-coverage',
                                    '/continuous-integration-testing', '/devscribe']):
            return 0.80
        
        # Main blog categories (not individual posts, not tags)
        if path in ['/blog/technology', '/blog/community'] or \
           (path.startswith('/blog/') and path.count('/') == 2):
            return 0.80
        
        # Core documentation guides (how-to, running, CI/CD, dependencies)
        if any(x in path for x in ['/docs/running-keploy/', '/docs/ci-cd/', 
                                    '/docs/dependencies/', '/docs/keploy-cloud/',
                                    '/docs/security']):
            return 0.80
        
        # ========== TIER 2B: QUICKSTARTS, INSTALLATIONS, BLOG TAGS (0.64) ==========
        
        # Quickstart tutorials (high learning value)
        if '/docs/quickstart/' in path:
            return 0.64
        
        # SDK and server installation guides
        if '/docs/server/installation/' in path or \
           '/docs/server/sdk-installation/' in path:
            return 0.64
        
        # Blog tags (category pages, not individual posts)
        if '/blog/tag/' in path:
            return 0.64
        
        # ========== TIER 3: CONCEPT PAGES, DEEP GUIDES, BLOG POSTS (0.51) ==========
        
        # Core concept explanations
        if '/docs/concepts/' in path and '/docs/1.0.0' not in path:
            return 0.51
        
        # Detailed keploy explanations and guides
        if '/docs/keploy-explained/' in path and '/docs/1.0.0' not in path:
            return 0.51
        
        # Operation guides (not versioned)
        if '/docs/operation/' in path and '/docs/1.0.0' not in path:
            return 0.51
        
        # Application development guides
        if '/docs/application-development/' in path:
            return 0.51
        
        # Individual blog posts (technology or community)
        if ('/blog/technology/' in path or '/blog/community/' in path) and \
           '/blog/tag/' not in path:
            return 0.51
        
        # Current version docs (not /1.0.0/)
        if '/docs/' in path and '/docs/1.0.0' not in path and \
           not any(x in path for x in ['/blog', '/pricing', '/api-testing', 
                                       '/integration-testing', '/unit-test-generator']):
            return 0.51
        
        # ========== TIER 4: OLD VERSIONED DOCS, DEEP NESTED PAGES (0.41) ==========
        
        # Old versioned documentation (/1.0.0/ should be lower priority)
        if '/docs/1.0.0/' in path:
            # Even lower priority for glossaries and references in old docs
            if '/glossary/' in path or '/reference/' in path or '/tags/' in path:
                return 0.41
            else:
                return 0.51  # Slightly higher for old SDK docs
        
        # Documentation tag pages (collection pages)
        if '/docs/tags/' in path or '/docs/1.0.0/tags/' in path:
            return 0.41
        
        # Very deep nested pages (4+ segments after /docs)
        if path.count('/') > 5:
            return 0.41
        
        # ========== DEFAULT: STANDARD PAGES (0.51) ==========
        # Catch-all for other pages like /about, /privacy-policy, etc.
        return 0.51
    
    async def fetch_url(self, session, url):
        """
        Fetch HTML content of a URL asynchronously.
        
        Args:
            session (aiohttp.ClientSession): HTTP session
            url (str): URL to fetch
            
        Returns:
            str: HTML content or None if failed
        """
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as response:
                if response.status == 200 and 'text/html' in response.headers.get('content-type', ''):
                    return await response.text()
        except:
            pass
        
        return None
    
    async def extract_links(self, html, current_url):
        """
        Extract all links from HTML and normalize them.
        
        Args:
            html (str): HTML content
            current_url (str): Current page URL (for relative→absolute conversion)
            
        Returns:
            set: Set of normalized absolute URLs
        """
        links = set()
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            for tag in soup.find_all(['a', 'link']):
                href = tag.get('href', '').strip()
                
                if href:
                    # Convert relative URL to absolute
                    absolute_url = urljoin(current_url, href)
                    
                    # NORMALIZE BEFORE CHECKING - this is KEY!
                    normalized_url = self.normalize_url(absolute_url)
                    
                    # Check if should crawl (domain + patterns)
                    if self.should_crawl(normalized_url):
                        links.add(normalized_url)
        except:
            pass
        
        return links
    
    async def crawl(self, max_concurrent=5):
        """
        Main crawling function. Fetches all URLs asynchronously.
        
        Args:
            max_concurrent (int): Number of simultaneous requests
        """
        queue = asyncio.Queue()
        
        # Normalize starting URL
        start_url = self.normalize_url(self.start_url)
        await queue.put(start_url)
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def worker(session):
            """Worker that processes URLs from queue."""
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                # Normalize URL (defensive - should already be normalized)
                url = self.normalize_url(url)
                
                # Skip if already visited
                if url in self.visited:
                    continue
                
                # Mark as visited
                self.visited.add(url)
                
                print(f"Crawling: {url} ({len(self.visited)} URLs found)")
                
                async with semaphore:
                    html = await self.fetch_url(session, url)
                    
                    if html:
                        # Store normalized URL data with proper priority
                        self.urls_data[url] = {
                            'lastmod': datetime.now().isoformat()[:10],
                            'priority': self.get_priority(url)
                        }
                        
                        # Extract links from this page
                        links = await self.extract_links(html, url)
                        
                        # Add new links to queue (all pre-normalized)
                        for link in links:
                            if link not in self.visited:
                                await queue.put(link)
        
        # Create TCP connector with limit
        connector = aiohttp.TCPConnector(limit=max_concurrent)
        
        # Run workers
        async with aiohttp.ClientSession(connector=connector) as session:
            workers = [worker(session) for _ in range(max_concurrent)]
            await asyncio.gather(*workers)
    
    def generate_xml_sitemap(self):
        """Generate XML sitemap from crawled URLs."""
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
        
        xml_str = ET.tostring(root, encoding='unicode')
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        
        return xml_declaration + xml_str
    
    def generate_json_sitemap(self):
        """Generate JSON version of sitemap."""
        return json.dumps({
            'generated_at': datetime.now().isoformat(),
            'total_urls': len(self.urls_data),
            'urls': self.urls_data
        }, indent=2)
    
    def compare_with_previous(self, previous_json_path):
        """Compare current sitemap with previous one."""
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
        
        new_urls = current_urls - previous_urls
        removed_urls = previous_urls - current_urls
        updated_urls = current_urls & previous_urls
        url_count_change = len(current_urls) - len(previous_urls)
        
        return {
            'new_urls': list(new_urls),
            'removed_urls': list(removed_urls),
            'updated_urls': list(updated_urls),
            'url_count_change': url_count_change
        }
    
    def save_sitemaps(self, output_dir='sitemaps'):
        """Save generated sitemaps to files."""
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save XML
        xml_path = os.path.join(output_dir, 'sitemap.xml')
        with open(xml_path, 'w') as f:
            f.write(self.generate_xml_sitemap())
        
        # Save JSON
        json_path = os.path.join(output_dir, f'sitemap_{timestamp}.json')
        with open(json_path, 'w') as f:
            f.write(self.generate_json_sitemap())
        
        # Compare and save changes
        previous_json = sorted([f for f in os.listdir(output_dir) 
                               if f.startswith('sitemap_') and f.endswith('.json')])
        
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
    """Main entry point."""
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