import json
import os
from urllib.parse import urlparse

class CrawlerPipeline(object):
    def process_item(self, item, spider):
        # Determine filename based on spider argument or domain
        output_file = getattr(spider, 'output_file', None)
        
        if output_file:
            filename = output_file
        else:
            domain = "unknown"
            if hasattr(spider, 'allowed_domains') and spider.allowed_domains:
                domain = spider.allowed_domains[0]
            
            # Sanitize domain for filename
            safe_domain = "".join([c if c.isalnum() or c in ['.','-'] else '_' for c in domain])
            filename = f"scraped_data_{safe_domain}.jsonl"
        
        # Prepare data
        data = dict(item)
        if 'content' in data:
            data['content'] = str(data['content'])
            
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
            
        return item
