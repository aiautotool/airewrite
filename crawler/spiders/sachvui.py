import scrapy
import os
from crawler.items import CrawlerItem
import re
# from bs4 import BeautifulSoup
import lxml.html.clean as clean
import json
from urllib.parse import urljoin
from readability import Document
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import Selector

# from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
from scrapy.spiders import Rule
class SachVuiSpider(scrapy.Spider):
    name = 'sachvui'
    allowed_domains = ['hopampro.com']
    start_urls = ['https://hopampro.com']
        

        
    def __init__(self):
        self.links=[]

    def parse(self, response):
        
        item = CrawlerItem()
        doc = Document(response.text)
        item['title'] = doc.title()
        item['content'] = doc.summary()
        item['content'] = item['content'].replace('<body>','').replace('</body>','').replace('<html>','').replace('</html>','')
        p = re.compile(r'<a.*?>')
        item['content'] = p.sub('', item['content']) 
        p = re.compile(r'<img.*?>')
        item['content'] = p.sub('', item['content']) 
        yield item
        self.links.append(response.url)
        for href in response.css('a::attr(href)'):
            yield response.follow(href, self.parse)
        # p = re.compile(r'<ins.*?>')
        # item['content'] = p.sub('', item['content']) 
        # html = item['content']
        # safe_attrs = set(['src', 'alt', 'href', 'title', 'data-srca'])
        # kill_tags = ['object', 'iframe','script','nav','time','svg','body','html','noscript']
        # cleaner = clean.Cleaner(safe_attrs_only=True, safe_attrs=safe_attrs, kill_tags=kill_tags)
        # item['content'] = cleaner.clean_html(html)
        
        
    # rules = (Rule(LinkExtractor(allow=('/*',),
    #                         deny=('blogs/*', 'videos/*', )),
    #           callback='parse_html'), )
    # rules = (
    #     # Extract links matching 'category.php' (but not matching 'subsection.php')
    #     # and follow links from them (since no callback means follow=True by default).
       

    #     # Extract links matching 'item.php' and parse them with the spider's method parse_item
    #     Rule(LinkExtractor(allow=('/post/*', )), callback='parse',follow=True),
    # )
   # rules = [Rule(LinkExtractor(), follow=True, callback="parse")]
    # def removeattrhtml(self,html):
    #     soup = BeautifulSoup(html)
    #     clean_soup = _remove_attrs(soup)
    #     return  clean_soup 
    # def _remove_attrs(soup):
    #     for tag in soup.findAll(True): 
    #         tag.attrs = None
    #     return soup

    # def RemoveHTMLTags(strr):
    #     strv = re.compile(r'<img[^>]+>').sub('', strr)
    #     strv = re.compile(r'<a[^>]+>').sub('', strv)
    #     strv = re.compile(r'<script[^>]+>').sub('', strv)
    #     strv = re.compile(r'<script[^>]+>').sub('', strv)
    #     return strv
         
    # def striphtml(data):
    #     p = re.compile(r'<.*?>')

    #     return p.sub('', data) 
    # def strip_tag(data):
    #     p = re.compile(r'<.*?>')
    #     p = re.compile(r'\n')
    #     return p.sub('', data) 

    # def start_requests(self):
        
    #     yield scrapy.Request(url = 'https://khobuontongnoithat.vn', callback = self.parsePage)
    #     # for url in urls:
    #     #     yield scrapy.Request(url = url, callback=self.parsePage)

    # def parsePage(self, response):
        
    #     for page in response.xpath('//a'):
    #         # print(page.xpath('./@href').extract_first())
    #         page_url =  page.xpath('./@href').extract_first()

    #         if page_url is not None:
    #             if not page_url.startswith('https://khobuontongnoithat.vn'):

    #                 page_url = ('https://khobuontongnoithat.vn' + page_url)
    #         # if page_url and page_url.startswith('/'):
    #         #     page_url = urljoin(response.request.url, page_url)
    #         print(page_url)
    #         yield scrapy.Request(url = page_url, callback=self.parse)

        

    # def parse(self, response):
    #     # for page in response.xpath('//a'):
    #     #     # print(page.xpath('./@href').extract_first())
    #     #     page_url =  page.xpath('./@href').extract_first()
    #     #     if page_url is not None:
    #     #         if not page_url.startswith('https://khobuontongnoithat.vn'):
    #     #             page_url = ('https://khobuontongnoithat.vn' + page_url)
            
    #     #     # if page_url and page_url.startswith('/'):
    #     #     #     page_url = 'https://olad.com.vn' + page_url
    #     #     yield scrapy.Request(url = page_url, callback=self.parse)
    #     self.log('crawling'.format(response.url))
    #     # item = CrawlerItem()
    #     # doc = Document(response.text)
    #     # item['title'] = doc.title()
    #     # item['title'] = item['title'].replace('\n','').replace('Olad.com.vn','').replace('    ','')
    #     # item['title'] = item['title'] + ""
    #     # # item['image'] = response.xpath('//div[@class="question-images "]/figure/img/@src').extract_first()
    #     # # item['desc'] = response.xpath('//div[@class="content"]/h2/text()').extract_first()
    #     # item['content'] = doc.summary()
    #     # item['content'] = item['content'].replace('<body>','').replace('</body>','').replace('<html>','').replace('</html>','')

    #     # p = re.compile(r'<a.*?>')
    #     # item['content'] = p.sub('', item['content']) 
    #     # # p = re.compile(r'<img.*?>')
    #     # # item['content'] = p.sub('', item['content']) 
        
    #     # p = re.compile(r'<ins.*?>')
    #     # item['content'] = p.sub('', item['content']) 
    #     # item['content'] = item['content'].replace('\n','').replace('        ','').replace(' 2564',' 2565').replace(' 2563',' 2565').replace(' 2562',' 2565').replace(' 2561',' 2565')
    #     # item['content'] = re.sub(r'<div class=\"detail\".*?>.*?</div>', '' , item['content']) 
    #     # item['content'] = re.sub(r'<div class=\"list-title\".*?>.*?</div>', '' , item['content']) 
        
    #     # html = item['content']
    #     # safe_attrs = set(['src', 'alt', 'href', 'title', 'data-srca'])
    #     # kill_tags = ['object', 'iframe','script','nav','time','svg','body','html','noscript']
    #     # cleaner = clean.Cleaner(safe_attrs_only=True, safe_attrs=safe_attrs, kill_tags=kill_tags)
    #     # item['content'] = cleaner.clean_html(html)
    #     # soup = BeautifulSoup(html, "html.parser")
    #     # tag_list = soup.findAll(lambda tag: len(tag.attrs) > 0)
    #     # for t in tag_list:
    #     #     for attr, val in t.attrs:
    #     #         del t[attr]
    #     # # for tag in soup.findAll(): 
    #     # #     tag.attrs = None
    #     # item['content'] = soup.decode('utf-8')

    #     # yield item
    #     # mobiUrl = response.xpath("//a[@class='btn btn-success']/@href").extract_first()
    #     # pdfUrl = response.xpath("//a[@class='btn btn-danger']/@href").extract_first()
        
    #     # if mobiUrl is not None:
    #     #     yield scrapy.Request(url = mobiUrl, callback=self.download)

     
    def download(self, response):
        path = response.url.split('/')[-1]
        dirf = r"../sachvui/"
        if not os.path.exists(dirf):os.makedirs(dirf)
        os.chdir(dirf)
        with open(path, 'wb') as f:
            f.write(response.body)