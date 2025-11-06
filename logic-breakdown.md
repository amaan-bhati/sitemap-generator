# Sitemap Generator - Complete Logic Breakdown

## **Overview**
The script crawls a website, discovers all URLs, generates an XML sitemap, and tracks changes over time.

---

## **1. How the Crawler Works**

### **Basic Flow (Like a Robot Walking Through a Website)**

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  START: https://keploy.io                                  │
│         ↓                                                   │
│  1. Fetch the page HTML                                    │
│  2. Extract all <a href> links                             │
│  3. Add new links to "Queue"                               │
│  4. Mark current URL as "Visited"                          │
│  5. Pick next URL from Queue                               │
│  6. Repeat until Queue is empty                            │
│         ↓                                                   │
│  DONE: Have all URLs                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### **Visual Example:**

**Iteration 1:**
```
Queue: [https://keploy.io]
Visited: []

→ Fetch https://keploy.io
→ Find links: [/docs, /blog, /pricing]
→ Queue: [/docs, /blog, /pricing]
→ Visited: [https://keploy.io]
```

**Iteration 2:**
```
Queue: [/docs, /blog, /pricing]
Visited: [https://keploy.io]

→ Fetch /docs
→ Find links: [/docs/guide, /docs/api, /docs/faq]
→ Queue: [/blog, /pricing, /docs/guide, /docs/api, /docs/faq]
→ Visited: [https://keploy.io, /docs]
```

**Iteration 3:**
```
Queue: [/blog, /pricing, /docs/guide, /docs/api, /docs/faq]
Visited: [https://keploy.io, /docs]

→ Fetch /blog
→ Find links: [/blog/post-1, /blog/post-2, /blog/post-3]
→ Queue: [/pricing, /docs/guide, /docs/api, /docs/faq, /blog/post-1, /blog/post-2, /blog/post-3]
→ Visited: [https://keploy.io, /docs, /blog]
```

...continues until Queue is empty.

---

## **2. The Code Logic Explained**

### **Part A: Initialization**

```python
class SitemapGenerator:
    def __init__(self, start_url, domain):
        self.start_url = start_url              # Where to start: https://keploy.io
        self.domain = domain                    # Domain to stay within: keploy.io
        self.visited = set()                    # URLs we've already crawled
        self.urls_data = defaultdict(...)       # Store URL + metadata (lastmod, priority)
        self.excluded_patterns = [...]          # Things to skip (.pdf, /login, etc.)
```

**Think of it as:**
- `visited` = A checklist of URLs already processed
- `urls_data` = A database storing each URL with its info
- `excluded_patterns` = Blocklist of things to ignore

---

### **Part B: Filtering URLs**

```python
def should_crawl(self, url):
    # 1. Check if URL is on the same domain
    if parsed.netloc != urlparse(self.domain).netloc:
        return False  # Skip external links
    
    # 2. Check if it matches excluded patterns
    for pattern in self.excluded_patterns:
        if pattern in url.lower():
            return False  # Skip PDFs, images, login pages, etc.
    
    # 3. Remove fragments
    if '#' in url:
        url = url.split('#')[0]
    
    # 4. Skip tracking params
    if 'utm_' in url or 'fbclid' in url:
        return False
    
    return True  # URL is safe to crawl
```

**Example:**
```
https://keploy.io/docs → ✅ Crawl
https://keploy.io/docs#section-1 → ✅ Crawl (fragment removed)
https://google.com → ❌ Skip (external)
https://keploy.io/login → ❌ Skip (excluded pattern)
https://keploy.io/file.pdf → ❌ Skip (PDF)
https://keploy.io/docs?utm_source=twitter → ❌ Skip (tracking param)
```

---

### **Part C: Async Crawling (Fast Parallel Processing)**

```python
async def crawl(self, max_concurrent=10):
    # max_concurrent = 10 means crawl 10 URLs at the same time
    
    queue = asyncio.Queue()              # Queue of URLs to crawl
    semaphore = asyncio.Semaphore(10)    # Limit to 10 simultaneous requests
    
    async def worker(session):
        while queue is not empty:
            url = queue.get()             # Get next URL
            
            if url in self.visited:
                continue                  # Already crawled, skip
            
            self.visited.add(url)         # Mark as visited
            
            html = await self.fetch_url(url)  # Fetch page (async = non-blocking)
            
            if html:
                # Extract all links and add to queue
                links = await self.extract_links(html, url)
                for link in links:
                    if link not in self.visited:
                        await queue.put(link)
```

**How Async Works:**

Normal (Slow):
```
Time: 0s  → Fetch URL 1 (takes 2s)
Time: 2s  → Fetch URL 2 (takes 2s)
Time: 4s  → Fetch URL 3 (takes 2s)
Total: 6 seconds for 3 URLs
```

Async (Fast):
```
Time: 0s  → Start fetching URL 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 (all at once!)
Time: 2s  → All 10 done, fetch next 10
Time: 4s  → Done
Total: 4 seconds for 10 URLs
```

That's why it's 10x faster! 🚀

---

### **Part D: Assigning Priority**

```python
def get_priority(self, url):
    path = urlparse(url).path.lower()
    
    if path in ['/', ''] or path == self.domain:
        return 1.0          # Homepage: highest priority
    elif '/docs' in path:
        return 0.9          # Docs: very important
    elif '/blog' in path:
        return 0.8          # Blog: important
    elif '/product' in path or '/features' in path:
        return 0.85         # Product pages: important
    else:
        return 0.7          # Everything else: normal
```

**Why?** Search engines crawl high-priority pages more frequently.

---

### **Part E: Storing URL Data**

```python
self.urls_data[url] = {
    'lastmod': '2025-11-06',      # Last modified date
    'priority': 0.9               # Priority score
}
```

Example output:
```python
{
    'https://keploy.io/': {
        'lastmod': '2025-11-06',
        'priority': 1.0
    },
    'https://keploy.io/docs': {
        'lastmod': '2025-11-06',
        'priority': 0.9
    },
    'https://keploy.io/blog': {
        'lastmod': '2025-11-06',
        'priority': 0.8
    }
}
```

---

## **3. How It Generates the Summary**

```python
def compare_with_previous(self, previous_json_path):
    # Read the OLD sitemap
    previous_urls = set(previous['urls'].keys())
    
    # Get the NEW urls
    current_urls = set(self.urls_data.keys())
    
    # Calculate differences
    new_urls = current_urls - previous_urls           # URLs in current, not in previous
    removed_urls = previous_urls - current_urls       # URLs in previous, not in current
    updated_urls = current_urls & previous_urls       # URLs in both (same URLs)
```

**Example:**

**Previous Run (Last Week):**
```
URLs: [/docs, /blog, /pricing, /features]
```

**Current Run (Today):**
```
URLs: [/docs, /blog, /pricing, /features, /blog/post-1, /blog/post-2]
```

**Differences:**
```
New URLs:      [/blog/post-1, /blog/post-2]          ← Added 2 URLs
Removed URLs:  []                                     ← Removed 0 URLs
Updated URLs:  [/docs, /blog, /pricing, /features]   ← Same 4 URLs
```

**Summary Output:**
```
📊 Changes Summary:
  New URLs: 2
  Removed URLs: 0
  URL Count Change: +2
```

---

## **4. File Output Structure**

### **sitemap.xml** (Current Sitemap)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url>
<loc>https://keploy.io/</loc>
<lastmod>2025-11-06</lastmod>
<priority>1.00</priority>
</url>
<url>
<loc>https://keploy.io/docs</loc>
<lastmod>2025-11-06</lastmod>
<priority>0.90</priority>
</url>
</urlset>
```

### **sitemap_20251106_143022.json** (Version History)
```json
{
    "generated_at": "2025-11-06T14:30:22.123456",
    "total_urls": 247,
    "urls": {
        "https://keploy.io/": {
            "lastmod": "2025-11-06",
            "priority": 1.0
        },
        "https://keploy.io/docs": {
            "lastmod": "2025-11-06",
            "priority": 0.9
        }
    }
}
```

### **changes_20251106_143022.json** (What Changed)
```json
{
    "new_urls": [
        "https://keploy.io/blog/post-1",
        "https://keploy.io/blog/post-2"
    ],
    "removed_urls": [],
    "updated_urls": [
        "https://keploy.io/",
        "https://keploy.io/docs"
    ],
    "url_count_change": 2
}
```

---

## **5. How Version Tracking Works**

**File Naming with Timestamps:**
```
sitemap_20251106_143022.json    ← Nov 6, 2025, 14:30:22
sitemap_20251113_143022.json    ← Nov 13, 2025, 14:30:22
sitemap_20251120_143022.json    ← Nov 20, 2025, 14:30:22
```

**Tracking Logic:**
```python
def save_sitemaps(self, output_dir='sitemaps'):
    # Get all previous JSON files sorted by date
    previous_json = sorted([f for f in os.listdir(output_dir) 
                           if f.startswith('sitemap_')])
    
    # Compare current with the LAST previous file
    if len(previous_json) > 1:
        previous_path = previous_json[-2]  # Second to last
        changes = self.compare_with_previous(previous_path)
        
        # Save changes to file
        changes_path = f'changes_{timestamp}.json'
        save_to_file(changes)
```

**Example Timeline:**
```
Week 1: sitemap_20251106.json (150 URLs)
Week 2: sitemap_20251113.json (155 URLs)
        changes_20251113.json (New: 5, Removed: 0, Total Change: +5)

Week 3: sitemap_20251120.json (160 URLs)
        changes_20251120.json (New: 6, Removed: 1, Total Change: +5)

Week 4: sitemap_20251127.json (162 URLs)
        changes_20251127.json (New: 3, Removed: 1, Total Change: +2)
```

---

## **Summary of Complete Flow**

```
START
  ↓
1. Initialize (visited set, urls_data dict, excluded patterns)
  ↓
2. Async Crawling (10 parallel requests)
  ├─ Fetch HTML
  ├─ Extract links
  ├─ Filter URLs (same domain, not excluded)
  ├─ Add to queue
  └─ Repeat until queue empty
  ↓
3. Process Each URL
  ├─ Assign priority (based on path)
  ├─ Set lastmod date (today)
  ├─ Store in urls_data
  ↓
4. Generate XML Sitemap
  ├─ Create XML with all URLs
  ├─ Sort alphabetically
  ├─ Save as sitemap.xml
  ↓
5. Generate JSON Snapshot
  ├─ Save urls_data as JSON
  ├─ Include timestamp
  ├─ Save as sitemap_TIMESTAMP.json
  ↓
6. Compare with Previous
  ├─ Read last sitemap JSON
  ├─ Calculate new/removed/updated URLs
  ├─ Save changes to changes_TIMESTAMP.json
  ├─ Print summary
  ↓
7. Output
  ├─ sitemap.xml (current)
  ├─ sitemap_TIMESTAMP.json (history)
  ├─ changes_TIMESTAMP.json (diff)
  ↓
END
```

---

## **Performance Notes**

- **10 concurrent requests**: 1000 URLs takes ~2-3 minutes
- **Async/await**: Non-blocking I/O, CPU stays free
- **Memory efficient**: Uses sets (O(1) lookup) and generators
- **Scalable**: Can handle 5000+ URLs easily