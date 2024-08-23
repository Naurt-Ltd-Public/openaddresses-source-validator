import os
import json
import requests
from urllib.parse import urlparse
import logging
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# Set up log directory and file
log_dir = './out'  
log_file = 'broken_links.log'
os.makedirs(log_dir, exist_ok=True)  
log_path = os.path.join(log_dir, log_file)

# Set up logging
logging.basicConfig(
    filename=log_path,
    level=logging.WARN,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)

CONSOLE_LOGGING = False

# Console Logging
if CONSOLE_LOGGING:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARN)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(console_handler)

# Flag for enabling/disabling parallel processing
PARALLEL_PROCESSING = True

def check_url(url, file_path):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.google.com'
    }
    
    def make_request_and_log(url):
        try:
            response = requests.head(url, allow_redirects=True, timeout=10, headers=headers)
            status_code =response.status_code
            if 200 <= response.status_code < 300:
                logging.info(f"{file_path} - URL is working - {url}")
                return True
            else:
                logging.warning(f" {file_path} - URL might be broken, Status code: {status_code}: {url} ")
                return False
        except requests.RequestException as e:
            logging.warning(f"{file_path} - Exception for URL in file :{url}  {e}")
            return False
    
    def make_request(url):
        try:
            response = requests.head(url, allow_redirects=True, timeout=10, headers=headers)
            if 200 <= response.status_code < 300:
                logging.info(f"{file_path} - URL is working - {url}")
                return True
            else:
                return False
        except requests.RequestException:
            return False
        
        
    # Skip URLs that end with .csv or .zip
    if url.lower().endswith(('csv', 'zip', 'polygons')):
        logging.info(f"Skipping URL (ends with .csv or .zip) in file {file_path}: {url}")
        return
    
    # Http and Https fallback
    if url.startswith("https://"):
        make_request_and_log(url)
    else:
        if url.startswith("http://"):
            if not make_request(url):
                https_url = url.replace("http://", "https://", 1)
                logging.info(f"Trying HTTPS version of the URL: {https_url}")
                make_request_and_log(https_url)
                  

def find_urls(data, file_path):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "data" and isinstance(value, str):
                parsed_url = urlparse(value)
                if parsed_url.scheme and parsed_url.netloc:
                    yield value
                else:
                    logging.error(f"Invalid URL format in 'data' in file {file_path}: {value}")
            else:
                yield from find_urls(value, file_path)  
    elif isinstance(data, list):
        for item in data:
            yield from find_urls(item, file_path)  

def process_json_file(file_path):
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON file {file_path} - {e}")
        return

    urls = list(find_urls(data, file_path))
    for url in urls:
        check_url(url, file_path)

def process_all_json_files(root_directory, parallel=False):
    json_files = [os.path.join(dirpath, filename)
                  for dirpath, _, filenames in os.walk(root_directory)
                  for filename in filenames if filename.endswith('.json')]

    if parallel:
        all_urls = []
        for file_path in json_files:
            all_urls.extend((url, file_path) for url in find_urls(json.load(open(file_path, 'r')), file_path))

        with ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(check_url, url, file_path): (url, file_path) for url, file_path in all_urls}
            for future in tqdm(as_completed(future_to_url), total=len(future_to_url), desc='Processing URLs'):
                try:
                    future.result()  
                except Exception as e:
                    logging.error(f"Exception during URL processing: {e}")
    else:
        for file_path in tqdm(json_files, desc='Processing JSON files', unit='file'):
            logging.info(f"Processing file: {file_path}")
            process_json_file(file_path)
            
def generate_badges_from_log(log_path, output_dir='./badges'):
    
    os.makedirs(output_dir, exist_ok=True)
    
    
    status_pattern = re.compile(r'WARNING -\s+(.*) - URL might be broken in file, Status code: (\d+): (https?://\S+)')
    exception_pattern = re.compile(r'WARNING -\s+(.*) - Exception for URL in file :(\S+) (.*)')
    
    with open(log_path, 'r') as log_file:
        for i, line in enumerate(log_file):
            status_match = status_pattern.search(line)
            exception_match = exception_pattern.search(line)
            
            if status_match:
                # Extract the file path and remove everything before 'sources'
                full_file_path = status_match.group(1).replace('\\', '/').lstrip('./')
                file_path = full_file_path.split('sources/', 1)[-1]  # Take only the part after 'sources'
                status_code = status_match.group(2)
                badge_md = f"[![{file_path} - Status code {status_code}](https://img.shields.io/badge/{file_path}-Failed-red)](https://github.com/openaddresses/openaddresses/tree/master/sources/{file_path})"
            
            elif exception_match:
                # Extract the file path and remove everything before 'sources'
                full_file_path = exception_match.group(1).replace('\\', '/').lstrip('./')
                file_path = full_file_path.split('sources/', 1)[-1]  # Take only the part after 'sources'
                badge_md = f"[![{file_path} - Exception](https://img.shields.io/badge/{file_path}-Exception-red)](https://github.com/openaddresses/openaddresses/tree/master/sources/{file_path})"
            
            else:
                continue
            
            # Save the markdown for each badge
            badge_file_name = f"badge_{i}.md"
            badge_file_path = os.path.join(output_dir, badge_file_name)
            with open(badge_file_path, 'w') as badge_file:
                badge_file.write(badge_md)  
                                           
if __name__ == "__main__":
    root_directory = os.getenv('ROOT_DIRECTORY', './test')
    process_all_json_files(root_directory, parallel=PARALLEL_PROCESSING)

    for handler in logging.getLogger().handlers:
        handler.flush()
        
    generate_badges_from_log(log_path)


    