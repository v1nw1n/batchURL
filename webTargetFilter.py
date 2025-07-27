# 用于通过ip:port检查目标是否是web服务
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INPUT_FILE = "ip_port.txt"
OUTPUT_FILE = "url-prod.txt"
MAX_THREADS = 50
TIMEOUT = 3  # 秒

# 尝试连接是否为 http/https 服务
def check_url(ip_port: str):
    ip_port = ip_port.strip()
    results = []

    for scheme in ["http", "https"]:
        url = f"{scheme}://{ip_port}"
        try:
            response = requests.get(url, timeout=TIMEOUT, verify=False)
            if response.status_code < 500:
                return url  # 只返回第一个成功的协议
        except requests.RequestException:
            continue
    return None

def main():
    with open(INPUT_FILE, "r") as f:
        targets = [line.strip() for line in f if line.strip()]

    valid_urls = []

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_url = {executor.submit(check_url, ip_port): ip_port for ip_port in targets}

        for future in as_completed(future_to_url):
            result = future.result()
            if result:
                print(f"[+] Found Web Service: {result}")
                valid_urls.append(result)

    # 写入结果
    with open(OUTPUT_FILE, "w") as f:
        for url in valid_urls:
            f.write(url + "\n")

    print(f"\n[✔] 检测完成，共发现 {len(valid_urls)} 个 Web 服务，结果保存到 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
