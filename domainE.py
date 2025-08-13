from urllib.parse import urlparse
import tldextract

def extract_main_domain(url):
    try:
        ext = tldextract.extract(url)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
    except:
        return None
    return None

def extract_domains_from_file(file_path):
    domains = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if not url:
                    continue
                domain = extract_main_domain(url)
                if domain is not None:
                    domains.add(domain)
    except FileNotFoundError:
        print(f"[ERROR] 文件不存在: {file_path}")
    return sorted(domains)

if __name__ == "__main__":
    input_file = "target_p.txt"  # 你要读取的文件名
    main_domains = extract_domains_from_file(input_file)

    print("[*] 提取的主域名：\n")
    print(main_domains)
