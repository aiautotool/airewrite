import scrapy
from urllib.parse import urlparse
from readability import Document
import re
from crawler.items import CrawlerItem

class DynamicSpider(scrapy.Spider):
    name = 'dynamic'
    
    def __init__(self, url=None, title_selector=None, content_selector=None, pagination_selector=None, article_selector=None, *args, **kwargs):
        super(DynamicSpider, self).__init__(*args, **kwargs)
        if not url:
            raise ValueError("URL argument is required")
        
        self.start_urls = [url]
        parsed = urlparse(url)
        self.allowed_domains = [parsed.netloc]
        self.base_domain = parsed.netloc
        self.title_selector = title_selector
        self.content_selector = content_selector
        self.pagination_selector = pagination_selector
        self.article_selector = article_selector

    def parse(self, response):
        # If article_selector is provided, we assume this is a LISTING page.
        # We find article links to follow (to parse_item) and pagination links to follow (to parse).
        
        if self.article_selector:
            # 1. Find Articles -> parse_item
            articles = []
            if self.article_selector.startswith('//') or self.article_selector.startswith('xpath:'):
                 sel = self.article_selector.replace('xpath:', '')
                 articles = response.xpath(sel).getall()
                 # Try to find href if selector was element
                 if not any('http' in l or '/' in l for l in articles):
                      articles = response.xpath(f"{sel}/@href").getall()
            else:
                 articles = response.css(f"{self.article_selector}::attr(href)").getall()
            
            for link in articles:
                if any(link.startswith(s) for s in ['http://', 'https://', '/']):
                    yield response.follow(link, self.parse_item)
                
            # 2. Find Next Page -> parse
            if self.pagination_selector:
                 pages = []
                 if self.pagination_selector.startswith('//') or self.pagination_selector.startswith('xpath:'):
                      sel = self.pagination_selector.replace('xpath:', '')
                      pages = response.xpath(sel).getall()
                      if not any('http' in l or '/' in l for l in pages):
                           pages = response.xpath(f"{sel}/@href").getall()
                 else:
                      pages = response.css(f"{self.pagination_selector}::attr(href)").getall()
                 
                 for link in pages:
                      if any(link.startswith(s) for s in ['http://', 'https://', '/']):
                           yield response.follow(link, self.parse)
        else:
            # Fallback: Treat every page as potential item AND source of links
            # This is the "dumb" mode where we just traverse everything.
            yield from self.parse_item(response)
            
            # Follow all links if no specific structure defined
            for href in response.css('a::attr(href)').getall():
                if any(href.startswith(s) for s in ['http://', 'https://', '/']):
                    yield response.follow(href, self.parse)

    def parse_item(self, response):
        title = None
        content = None

        # 1. Title Extraction
        if self.title_selector:
            if self.title_selector.startswith('//') or self.title_selector.startswith('xpath:'):
                sel = self.title_selector.replace('xpath:', '')
                title = response.xpath(sel).get()
            else:
                try: title = response.css(self.title_selector + '::text').get()
                except: title = response.css(self.title_selector).get()
        
        # Fallback to Readability for Title
        if not title:
             doc = Document(response.text)
             title = doc.title()

        # 2. Content Extraction
        if self.content_selector:
            # Check if likely XPath (starts with //) or CSS
            if self.content_selector.startswith('//') or self.content_selector.startswith('xpath:'):
                 sel = self.content_selector.replace('xpath:', '')
                 # Join multiple elements if selector matches multiple
                 content = "".join(response.xpath(sel).getall())
            else:
                 content = "".join(response.css(self.content_selector).getall())
        
        # Fallback to Readability for Content
        if not content or (len(content) < 100): # Simple check for failure
             doc = Document(response.text)
             content = doc.summary()
             # Clean content
             content = re.sub(r'<script.*?>.*?</script>', '', content, flags=re.DOTALL)
             content = re.sub(r'<style.*?>.*?</style>', '', content, flags=re.DOTALL)
             content = content.replace('<html>', '').replace('</html>', '').replace('<body>', '').replace('</body>', '')
        
        # Clean title
        if title:
             title = re.sub(r'\s+', ' ', title).strip()
        
        if title and content:
            # Create Item
            item = CrawlerItem()
            item['title'] = title
            item['content'] = content
    
            # You might want to store more fields if CrawlerItem allows, e.g. url
            # item['url'] = response.url 
            
            yield item
