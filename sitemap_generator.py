import asyncio              # For concurrent/parallel task execution
import aiohttp              # For async HTTP requests (non-blocking)
from bs4 import BeautifulSoup  # For parsing HTML and extracting data
from urllib.parse import urljoin, urlparse  # For URL manipulation and parsing
from datetime import datetime  # For timestamps
import json                 # For JSON file handling
import xml.etree.ElementTree as ET  # For XML generation
from collections import defaultdict  # For automatic default values in dict
import os                   # For file/folder operations
import sys                  # For system operations


class SitemapGenerator:
    """
    Main class that handles website crawling and sitemap generation.
    
    This crawler:
    1. Fetches webpages from a website
    2. Extracts all links from each page
    3. Stores URLs with metadata (priority, last modified date)
    4. Generates XML sitemap and JSON backup
    5. Tracks changes between runs
    """
    
    def __init__(self, start_url, domain):
        """
        Initialize the crawler with configuration.
        
        Args:
            start_url (str): Starting URL (e.g., 'https://keploy.io')
            domain (str): Domain to stay within (e.g., 'https://keploy.io')
        """
        self.start_url = start_url  # The first URL to crawl (homepage)
        self.domain = domain  # Domain filter (don't crawl external sites)
        
        # Set to store all visited URLs (prevents duplicate crawling)
        # Using set for O(1) lookup time: url in self.visited (very fast)
        self.visited = set()
        
        # Dictionary to store each URL's metadata:
        # {url: {'lastmod': '2025-11-06', 'priority': 0.9}}
        # defaultdict auto-creates entries with default values if key doesn't exist
        self.urls_data = defaultdict(lambda: {'lastmod': None, 'priority': 0.5})
        
        # Patterns to EXCLUDE from crawling (images, PDFs, login pages, etc.)
        # Any URL containing these patterns will be skipped
        self.excluded_patterns = ['.pdf', '.jpg', '.png', '.gif', '.zip', '/search', '/login']
        
    def should_crawl(self, url):
        """
        Determine if a URL should be crawled or skipped.
        
        This function filters URLs based on:
        1. Domain (stay within same domain)
        2. Excluded patterns (skip PDFs, images, etc.)
        3. Fragments (remove #anchors to avoid duplicates)
        4. Tracking parameters (remove utm_ params)
        
        Args:
            url (str): URL to check (e.g., 'https://keploy.io/docs')
            
        Returns:
            bool: True if URL should be crawled, False if it should be skipped
        """
        # Parse URL into components: scheme, netloc, path, query, fragment
        # Example: https://keploy.io/docs?id=1#section
        # → scheme='https', netloc='keploy.io', path='/docs', query='id=1', fragment='section'
        parsed = urlparse(url)
        
        # ========== FILTER 1: Domain Check ==========
        # Extract domain from both the current URL and allowed domain
        # Example: 'keploy.io' from 'https://keploy.io/docs'
        # Reject if they don't match (we only want same-domain links)
        if parsed.netloc != urlparse(self.domain).netloc:
            return False  # Skip external links (e.g., google.com)
            
        # ========== FILTER 2: Excluded Patterns ==========
        # Check if URL contains any excluded patterns (PDFs, images, login, etc.)
        # Example: 'https://keploy.io/file.pdf' contains '.pdf' → skip
        for pattern in self.excluded_patterns:
            if pattern in url.lower():  # .lower() for case-insensitive comparison
                return False  # Skip this URL
                
        # ========== FILTER 3: Remove Fragments ==========
        # Fragments (the #section part) don't change page content
        # Example: /docs#section1 and /docs#section2 are the same page
        # Remove fragment to avoid crawling same page multiple times
        if '#' in url:
            url = url.split('#')[0]  # Keep only the part before #
            
        # ========== FILTER 4: Skip Tracking Parameters ==========
        # Tracking params (utm_, fbclid, gclid) create duplicate pages
        # Example: /blog?utm_source=twitter and /blog?utm_source=email are same page
        if '?' in url:  # URL has query parameters
            # Check for any tracking parameters
            if any(x in url for x in ['utm_', 'fbclid', 'gclid']):
                return False  # Skip URLs with tracking params
            
        # If all filters pass, this URL is safe to crawl
        return True
    
    def get_priority(self, url):
        """
        Assign priority score to a URL based on its path.
        
        Priority helps search engines know which pages are most important.
        - 1.0 = highest priority (homepage, most important)
        - 0.7 = normal priority (other pages)
        
        Higher priority pages get crawled more frequently by search engines.
        
        Args:
            url (str): URL to score (e.g., 'https://keploy.io/docs/guide')
            
        Returns:
            float: Priority score between 0.0 and 1.0
        """
        # Extract just the path part and convert to lowercase for comparison
        # Example: 'https://keploy.io/docs/guide' → '/docs/guide'
        path = urlparse(url).path.lower()
        
        # Homepage is MOST important (highest priority)
        # Users start here, so it's the entry point
        if path in ['/', ''] or path == self.domain:
            return 1.0
        
        # Documentation is VERY important (search engines should index it heavily)
        # Docs are the first place users go for help
        elif '/docs' in path:
            return 0.9
        
        # Blog posts are moderately important
        # Good for SEO and user engagement but less critical than docs
        elif '/blog' in path:
            return 0.8
        
        # Product/features pages are very important (marketing pages)
        # Key for conversion and user understanding
        elif '/product' in path or '/features' in path:
            return 0.85
        
        # Everything else gets normal priority
        # Pages like /about, /careers, /contact, etc.
        else:
            return 0.7
    
    async def fetch_url(self, session, url):
        """
        Fetch the HTML content of a URL asynchronously.
        
        Async means: fetch multiple URLs in parallel (10 at a time)
        instead of waiting for each one sequentially (much faster!).
        
        Args:
            session (aiohttp.ClientSession): Reusable HTTP session object
            url (str): URL to fetch
            
        Returns:
            str: HTML content of the page, or None if fetch failed
        """
        try:
            # Make async HTTP GET request with timeout
            # timeout=10: wait max 10 seconds before giving up
            # ssl=False: don't verify SSL certificates (faster, less strict)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as response:
                # Only process successful responses with HTML content
                # response.status == 200: "OK" (page found and accessible)
                # 'text/html' in content-type: confirm it's an HTML page (not JSON/image)
                if response.status == 200 and 'text/html' in response.headers.get('content-type', ''):
                    # Return HTML as text
                    # 'await' pauses here until the full response body is read
                    return await response.text()
        except:
            # Silently catch any errors (timeouts, network errors, etc.)
            # Just skip this URL and continue crawling others
            pass
        
        # Return None if fetch failed for any reason
        return None
    
    async def extract_links(self, html, current_url):
        """
        Extract all links from HTML content and convert to absolute URLs.
        
        This function:
        1. Parses HTML with BeautifulSoup
        2. Finds all <a> and <link> tags
        3. Converts relative URLs to absolute URLs
        4. Filters using should_crawl()
        5. Returns set of valid URLs to crawl next
        
        Args:
            html (str): HTML content of the page
            current_url (str): The URL we're currently on (for relative→absolute conversion)
            
        Returns:
            set: Set of absolute URLs found in the page
        """
        # Create empty set to store found links
        links = set()
        
        try:
            # Parse HTML into a BeautifulSoup object (tree structure)
            # This allows us to search for and extract HTML elements
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all <a> (links) and <link> (stylesheets, etc.) tags
            for tag in soup.find_all(['a', 'link']):
                # Get the href attribute from the tag (empty string if missing)
                # Example: <a href="/docs">Docs</a> → href="/docs"
                href = tag.get('href', '').strip()  # .strip() removes whitespace
                
                # Only process if href exists and is not empty
                if href:
                    # Convert relative URL to absolute URL
                    # Examples:
                    # Current page: https://keploy.io/blog
                    # Relative link: "/docs" → Absolute: "https://keploy.io/docs"
                    # Relative link: "../about" → Absolute: "https://keploy.io/about"
                    absolute_url = urljoin(current_url, href)
                    
                    # Check if this URL should be crawled (domain check, filters, etc.)
                    if self.should_crawl(absolute_url):
                        # Add to set (automatically prevents duplicates)
                        links.add(absolute_url)
        except:
            # If HTML parsing fails, just skip and return empty set
            pass
        
        # Return set of all valid URLs found on this page
        return links
    
    async def crawl(self, max_concurrent=5):
        """
        Main crawling function. Fetches all URLs on the website asynchronously.
        
        How it works:
        1. Create a queue with the starting URL
        2. Create 10 worker tasks that run in parallel
        3. Each worker fetches a URL from queue, extracts links, adds new links back to queue
        4. Continue until queue is empty (all URLs processed)
        
        This is much faster than sequential crawling because multiple URLs
        are fetched simultaneously (up to 10 at a time).
        
        Args:
            max_concurrent (int): Number of URLs to fetch simultaneously (default: 5, max: 20)
                                  Higher = faster but more resource usage
                                  Lower = slower but less resource usage
        """
        # Create an async queue to hold URLs that need to be crawled
        # Queue = ordered list where we add to one end, take from other end
        queue = asyncio.Queue()
        
        # Add the starting URL to the queue
        # await keyword: "wait until this operation completes" (required for async operations)
        await queue.put(self.start_url)  # Queue now has: [https://keploy.io]
        
        # Create a semaphore to limit concurrent requests
        # Semaphore acts like a bouncer at a club: only allows N people inside at once
        # max_concurrent=5 means only 5 URLs are being fetched at the same time
        # This prevents overwhelming the server or our network
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # Define a worker function that processes URLs from the queue
        # Each instance of this function will run in parallel
        async def worker(session):
            """
            Worker coroutine - processes URLs from the queue one by one.
            Multiple instances of this run simultaneously.
            """
            # Keep working until queue is empty
            while True:
                try:
                    # Try to get a URL from queue without waiting
                    # get_nowait() = "get immediately, don't wait if empty"
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    # If queue is empty, this worker has nothing to do
                    # Exit the loop (worker is done)
                    break
                
                # If URL was already processed, skip it
                # Prevents duplicate crawling of same URL
                if url in self.visited:
                    continue
                
                # Mark this URL as visited (being processed or already processed)
                # This prevents other workers from processing the same URL
                self.visited.add(url)
                
                # Print progress to console
                # Shows which URL is being crawled and how many total found so far
                print(f"Crawling: {url} ({len(self.visited)} URLs found)")
                
                # Acquire a semaphore slot before fetching
                # async with = "acquire semaphore, run code, release semaphore"
                # This ensures max 5 URLs are being fetched at any moment
                async with semaphore:
                    # Fetch the URL (this takes a few seconds)
                    # await = "wait for the fetch to complete, don't do anything else"
                    html = await self.fetch_url(session, url)
                    
                    # Only process if fetch was successful (html is not None)
                    if html:
                        # Store this URL's data in our dictionary
                        self.urls_data[url] = {
                            # Last modified = today's date (ISO format)
                            # [:10] takes only the date part: '2025-11-06T14:30:22' → '2025-11-06'
                            'lastmod': datetime.now().isoformat()[:10],
                            # Priority score based on URL path
                            'priority': self.get_priority(url)
                        }
                        
                        # Extract all links from this page
                        # Returns a set of absolute URLs
                        links = await self.extract_links(html, url)
                        
                        # Add all new URLs to the queue for processing
                        # Only add if they haven't been visited yet
                        for link in links:
                            if link not in self.visited:
                                # Add to queue (other workers will process this)
                                await queue.put(link)
        
        # ========== Set up async HTTP session and start workers ==========
        
        # Create TCP connector with connection limit
        # Limits the number of simultaneous TCP connections
        # max_concurrent=5 means max 5 simultaneous connections
        connector = aiohttp.TCPConnector(limit=max_concurrent)
        
        # Create HTTP session (like opening a browser)
        # 'async with' ensures session is properly closed when done
        async with aiohttp.ClientSession(connector=connector) as session:
            # Create 5 worker coroutines
            # Each worker will process URLs from the queue
            # All 5 workers run in parallel
            workers = [worker(session) for _ in range(max_concurrent)]
            
            # Run all workers simultaneously and wait for them to complete
            # asyncio.gather(*workers) = "run all these tasks in parallel"
            # await = "wait until all workers are done"
            await asyncio.gather(*workers)
    
    def generate_xml_sitemap(self):
        """
        Generate a valid XML sitemap from the crawled URLs.
        
        XML sitemap format is standard and supported by all search engines
        (Google, Bing, Yahoo, etc.). It tells them:
        - What pages exist on the site
        - How important each page is (priority)
        - When each page was last updated (lastmod)
        
        Returns:
            str: Complete XML sitemap as a string
        """
        # Register the xsi namespace with XML library
        # This allows us to use xsi:schemaLocation attribute
        ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        
        # Create root XML element <urlset>
        root = ET.Element('urlset')
        
        # Add standard sitemap namespace
        # This tells search engines this is a valid sitemap
        root.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        
        # Add schema location for validation
        # This is the URL where the XML schema is defined (for validation)
        root.set('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation', 
                 'http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd')
        
        # Loop through all URLs in alphabetical order
        # sorted() = puts URLs in A-Z order (better organization)
        for url in sorted(self.urls_data.keys()):
            # Create <url> element inside <urlset>
            # This represents one URL entry
            url_elem = ET.SubElement(root, 'url')
            
            # Create <loc> tag (location = the URL itself)
            # Example: <loc>https://keploy.io/docs</loc>
            loc = ET.SubElement(url_elem, 'loc')
            loc.text = url  # Set the URL as the text content
            
            # Create <lastmod> tag (last modified date)
            # Example: <lastmod>2025-11-06</lastmod>
            # Tells search engines when page was last updated
            lastmod = ET.SubElement(url_elem, 'lastmod')
            lastmod.text = self.urls_data[url]['lastmod']
            
            # Create <priority> tag (importance score)
            # Example: <priority>0.90</priority>
            # Range: 0.0 (low) to 1.0 (high)
            priority = ET.SubElement(url_elem, 'priority')
            # Format to 2 decimal places: 0.9 → "0.90", 1.0 → "1.00"
            priority.text = f"{self.urls_data[url]['priority']:.2f}"
        
        # Convert XML tree to string
        # encoding='unicode' returns a Python string (not bytes)
        xml_str = ET.tostring(root, encoding='unicode')
        
        # Add XML declaration at the top
        # Required for valid XML files
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        
        # Return complete XML as string
        return xml_declaration + xml_str
    
    def generate_json_sitemap(self):
        """
        Generate JSON version of sitemap for version tracking and history.
        
        JSON format is easier to work with programmatically than XML.
        We use it to:
        - Store metadata about the crawl (timestamp, total URLs)
        - Track changes between runs
        - Keep historical records
        
        Returns:
            str: Complete JSON sitemap as a string
        """
        # Create dictionary with sitemap data
        return json.dumps({
            # ISO timestamp: e.g., '2025-11-06T14:30:22.123456'
            # Tells us exactly when this crawl was completed
            'generated_at': datetime.now().isoformat(),
            
            # Total number of URLs found
            # Quick reference without parsing entire file
            'total_urls': len(self.urls_data),
            
            # All URL data with their metadata
            # Format: {url: {'lastmod': '...', 'priority': ...}, ...}
            'urls': self.urls_data
        }, indent=2)  # indent=2 makes JSON pretty-printed and readable
    
    def compare_with_previous(self, previous_json_path):
        """
        Compare current sitemap with previous one and identify changes.
        
        Uses set operations to find:
        - New URLs (added since last run)
        - Removed URLs (deleted since last run)
        - Updated URLs (same URLs that still exist)
        
        This helps track site growth and changes over time.
        
        Args:
            previous_json_path (str): Path to previous sitemap JSON file
            
        Returns:
            dict: Dictionary with new_urls, removed_urls, updated_urls, and url_count_change
        """
        # If no previous file exists (first run), all current URLs are "new"
        if not os.path.exists(previous_json_path):
            return {
                'new_urls': list(self.urls_data.keys()),  # All URLs are new
                'removed_urls': [],  # Nothing removed
                'updated_urls': []  # Nothing unchanged
            }
        
        # Read the previous sitemap file
        with open(previous_json_path, 'r') as f:
            previous = json.load(f)  # Parse JSON into dictionary
        
        # Extract just the URL keys from both old and new data
        # Convert to sets for fast comparison operations
        # Set: unordered collection of unique items with O(1) lookup time
        previous_urls = set(previous['urls'].keys())  # URLs from previous crawl
        current_urls = set(self.urls_data.keys())  # URLs from current crawl
        
        # Calculate differences using set operations:
        
        # NEW URLs: in current but NOT in previous
        # Set operation: current - previous = items only in current
        # Example: {A, B, C, D} - {A, B, C} = {D}
        new_urls = current_urls - previous_urls
        
        # REMOVED URLs: in previous but NOT in current
        # Set operation: previous - current = items only in previous
        # Example: {A, B, C} - {A, B, C, D} = {} (empty)
        removed_urls = previous_urls - current_urls
        
        # UPDATED URLs: in BOTH previous and current (same URLs)
        # Set operation: current & previous = items in both sets
        # Example: {A, B, C, D} & {A, B, C} = {A, B, C}
        updated_urls = current_urls & previous_urls
        
        # Calculate net change in URL count
        # Positive = site grew, Negative = site shrunk
        url_count_change = len(current_urls) - len(previous_urls)
        
        # Return all changes as dictionary
        return {
            'new_urls': list(new_urls),  # Convert set to list for JSON serialization
            'removed_urls': list(removed_urls),
            'updated_urls': list(updated_urls),
            'url_count_change': url_count_change
        }
    
    def save_sitemaps(self, output_dir='sitemaps'):
        """
        Save all generated sitemaps and changes to files.
        
        Creates three files:
        1. sitemap.xml - Current XML sitemap (always updated)
        2. sitemap_TIMESTAMP.json - JSON snapshot with timestamp (for history)
        3. changes_TIMESTAMP.json - What changed since last run (for tracking)
        
        Args:
            output_dir (str): Directory to save files in (default: 'sitemaps')
        """
        # Create output directory if it doesn't exist
        # exist_ok=True means don't error if folder already exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate timestamp for file naming
        # Format: 20251106_143022 (YYYYMMDD_HHMMSS)
        # This allows multiple runs to have different files (version history)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # ========== Save XML Sitemap ==========
        # Create path: sitemaps/sitemap.xml
        xml_path = os.path.join(output_dir, 'sitemap.xml')
        
        # Write XML sitemap to file
        # 'w' mode = write (overwrites if file exists)
        with open(xml_path, 'w') as f:
            f.write(self.generate_xml_sitemap())
        
        # ========== Save JSON Sitemap ==========
        # Create path: sitemaps/sitemap_20251106_143022.json
        # Timestamp makes each run unique (for version history)
        json_path = os.path.join(output_dir, f'sitemap_{timestamp}.json')
        
        # Write JSON sitemap to file
        with open(json_path, 'w') as f:
            f.write(self.generate_json_sitemap())
        
        # ========== Compare with Previous and Save Changes ==========
        # Get list of all JSON files in sitemaps folder
        # Sort alphabetically (oldest first, newest last)
        previous_json = sorted([f for f in os.listdir(output_dir) 
                               if f.startswith('sitemap_') and f.endswith('.json')])
        
        # If more than one file exists, we can compare
        # len(previous_json) > 1 means this is NOT the first run
        if len(previous_json) > 1:
            # Get the SECOND-TO-LAST file (the previous run's sitemap)
            # previous_json[-1] = last file (current run)
            # previous_json[-2] = second-to-last (previous run)
            previous_path = os.path.join(output_dir, previous_json[-2])
            
            # Compare current with previous and get changes
            changes = self.compare_with_previous(previous_path)
            
            # Save changes to file
            # Creates: sitemaps/changes_20251106_143022.json
            changes_path = os.path.join(output_dir, f'changes_{timestamp}.json')
            with open(changes_path, 'w') as f:
                json.dump(changes, f, indent=2)  # indent=2 makes JSON readable
            
            # ========== Print Summary ==========
            # Display changes to console
            print(f"\n📊 Changes Summary:")
            print(f"  New URLs: {len(changes['new_urls'])}")
            print(f"  Removed URLs: {len(changes['removed_urls'])}")
            # :+d format always shows + or - sign
            print(f"  URL Count Change: {changes['url_count_change']:+d}")
        
        # ========== Print Final Summary ==========
        print(f"\n✅ Sitemaps saved:")
        print(f"  XML: {xml_path}")
        print(f"  JSON: {json_path}")
        print(f"  Total URLs: {len(self.urls_data)}")
        
        return xml_path, json_path


async def main():
    """
    Main entry point for the sitemap generator.
    
    This function:
    1. Sets up configuration
    2. Creates SitemapGenerator instance
    3. Runs the crawler
    4. Saves all generated files
    """
    
    # ========== Configuration ==========
    # Customize these variables for different websites
    
    START_URL = 'https://keploy.io'  # First URL to crawl (homepage)
    DOMAIN = 'https://keploy.io'     # Only crawl this domain (don't go external)
    OUTPUT_DIR = 'sitemaps'          # Where to save generated files
    
    # Print startup message
    print("🚀 Starting Keploy Sitemap Generation...")
    print(f"Domain: {DOMAIN}")
    
    # Create crawler instance with configuration
    generator = SitemapGenerator(START_URL, DOMAIN)
    
    # Start crawling asynchronously
    # max_concurrent=10 means crawl 10 URLs simultaneously
    # await = wait for crawling to finish (may take 5-10 minutes)
    await generator.crawl(max_concurrent=10)
    
    # Save all generated files (XML, JSON, changes)
    generator.save_sitemaps(OUTPUT_DIR)
    
    # Print completion message
    print("\n✨ Sitemap generation complete!")


# ========== Script Entry Point ==========
if __name__ == '__main__':
    """
    This block only runs if the script is executed directly.
    It doesn't run if the script is imported as a module.
    
    Example:
    - Run directly: python sitemap_generator.py ✅ (runs this block)
    - Import: from sitemap_generator import SitemapGenerator ✅ (skips this block)
    """
    # asyncio.run() starts the event loop and runs the main() coroutine
    # This is required for async/await to work
    asyncio.run(main())