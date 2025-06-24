import os
import io
import time
import argparse
from bs4 import BeautifulSoup
import threading
import logging
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from seleniumwire import webdriver  
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.common.exceptions import WebDriverException, TimeoutException

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage, ImageOps

# === 配置 ===
TARGET_IMG_WIDTH = 300
ROW_HEIGHT = 150

# === 日志设置 ===
LOG_FILENAME = "batchURL.log"
# 启动时清空日志文件内容
with open(LOG_FILENAME, 'w', encoding='utf-8') as f:
    f.write('')
logging.basicConfig(
    filename=LOG_FILENAME,
    filemode="a",
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    encoding='utf-8'
)

def print_banner():
    try:
        with open("banner.txt", "r", encoding="utf-8") as f:
            banner = f.read()
            print(banner)
    except FileNotFoundError:
        pass

class ArgumentParserBanner(argparse.ArgumentParser):
    def print_help(self, *args, **kwargs):
        print_banner()
        super().print_help(*args, **kwargs)

# ===TODO: Token 检查（预留实现） ===
def is_token_valid(token: str) -> bool:
    return False

# ===TODO: AI 判断逻辑（预留实现） ===
def ai_judge_status(url: str, html: str, http_status: int, token: str) -> str:
    return ""

# === 本地/AI 判断页面状态 ===
def judge_page_status(url: str, html: str, http_status: int, token: str = None) -> str:
    if token and is_token_valid(token):
        return ai_judge_status(url, html, http_status, token)

    #状态码-》title-》结构复杂度（标签数量）
    if http_status is None or http_status >= 500:
        return "无法访问(5xx)"
    elif http_status >= 400:
        return "页面异常(4xx)"

    lowered = html.lower()
    soup = BeautifulSoup(html, 'html.parser')
    

    # 简单结构页判断: title 为空或含错误关键词 + 页面标签少
    title = soup.title.string.strip().lower() if soup.title and soup.title.string else ""
    body_tags = soup.find_all(True)
    tag_count = len(body_tags)

    error_keywords = ["404", "not found", "403", "forbidden", "502", "bad gateway", "error"]
    keyword_hit = [kw for kw in error_keywords if  kw in title]

    if keyword_hit:
        logging.info(f"URL 命中关键词 {keyword_hit}: {url}")
        if tag_count < 30:
            return "页面异常(结构简单)"
        return "页面异常(目标存活)"

    return "正常"

# === 缩放图像并加边框 ===
def resize_image(image_bytes, target_width=TARGET_IMG_WIDTH):
    img = PILImage.open(io.BytesIO(image_bytes))
    w_percent = target_width / float(img.size[0])
    h_size = int((float(img.size[1]) * float(w_percent)))
    img = img.resize((target_width, h_size))
    img = ImageOps.expand(img, border=2, fill='black')
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# === 创建浏览器实例 ===
def create_browser():
    options = FirefoxOptions()
    options.add_argument('--headless')
    options.accept_insecure_certs = True
    driver = webdriver.Firefox(seleniumwire_options={}, options=options)
    driver.set_page_load_timeout(15)
    return driver

# === 获取状态码 ===
def get_status_code(driver):
    try:
        for request in reversed(driver.requests):
            if request.response and request.url == driver.current_url:
                return request.response.status_code
    except Exception:
        pass
    return None

# === 浏览器池工作线程 ===
def worker(thread_id, task_queue, result_dict, lock, llm_token, progress_callback, status_dict):
    driver = create_browser()
    while True:
        try:
            task = task_queue.get(timeout=3)
        except:
            break

        idx, url = task
        try:
            status_dict["current"] = f"线程-{thread_id} 正在处理: {idx} - {url}"
            driver.get(url)
            time.sleep(2)
            html = driver.page_source
            http_status = get_status_code(driver)
            screenshot = driver.get_screenshot_as_png()
            image = resize_image(screenshot)
            status = judge_page_status(url, html, http_status, token=llm_token)
        except TimeoutException:
            status = "无法访问（访问超时）"
            image = None
        except WebDriverException:
            status = "无法访问（Web异常）"
            image = None
        except Exception:
            status = "无法访问（其他异常）"
            image = None
            logging.exception(f"处理 URL 异常: {url}")

        with lock:
            result_dict[idx] = {
                "id": idx,
                "url": url,
                "status": status,
                "image": image
            }
            if progress_callback:
                progress_callback()

        task_queue.task_done()

    driver.quit()

# === 写入 Excel 文件 ===
def write_excel(results: list, output_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "访问结果"
    ws.append(["ID", "URL", "访问状态", "截图"])

    for row_num, res in enumerate(results, start=2):
        ws.cell(row=row_num, column=1, value=res["id"])
        ws.cell(row=row_num, column=2, value=res["url"])
        ws.cell(row=row_num, column=3, value=res["status"])
        if res["image"]:
            img = XLImage(res["image"])
            ws.add_image(img, f"D{row_num}")
            ws.row_dimensions[row_num].height = ROW_HEIGHT
        else:
            ws.cell(row=row_num, column=4, value="（无截图）")
            ws.row_dimensions[row_num].height = 20

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 45
    wb.save(output_path)
    print(f"\n✅ Excel 文件已保存: {output_path}")

# === 自动计算线程数 ===
def calculate_worker_count(url_count, max_limit=8):
    if url_count <= 10:
        return min(2, url_count)
    elif url_count <= 100:
        return min(4, url_count)
    elif url_count <= 300:
        return min(6, url_count)
    else:
        return min(max_limit, url_count // 20 + 2)

# === 主函数 ===
def main():
   
    parser = ArgumentParserBanner(description="批量获取目标URL访问状态")
    parser.add_argument('-i', '--input', default='urls', help='定义目标，一行一个目标（txt）')
    parser.add_argument('-o', '--output', default='url_results', help='定义输出文件名，不加后缀')
    parser.add_argument('--llm-token', help='开启AI支持，配置token')
    parser.add_argument('--friend-ui', action='store_true', help='是否启用进度条展示（默认关闭）')
    args = parser.parse_args()

    input_file = args.input
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_excel = f"{args.output}_{timestamp}.xlsx"
    llm_token = args.llm_token
    use_progress_bar = args.friend_ui

    if not os.path.exists(input_file):
        print(f"❌ 未找到输入文件：{input_file}")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    url_count = len(urls)
    if url_count == 0:
        print("❗ 输入 URL 为空")
        return

    worker_count = calculate_worker_count(url_count)
    print(f"📊 总计 URL: {url_count}，浏览器池线程数: {worker_count}")

    start_time = time.time()

    task_queue = Queue()
    for idx, url in enumerate(urls, start=1):
        task_queue.put((idx, url))

    results_dict = {}
    lock = threading.Lock()
    threads = []
    status_dict = {"current": ""}

    progress_count = [0]
    progress_bar = None
    if use_progress_bar:
        try:
            from tqdm import tqdm
            progress_bar = tqdm(total=url_count, desc="处理进度", ncols=80)
        except ImportError:
            print("⚠️ 未安装 tqdm，进度条自动切换为轻量模式")
            use_progress_bar = False

    def progress_callback():
        progress_count[0] += 1
        if use_progress_bar and progress_bar:
            progress_bar.update(1)
        else:
            print(f"\r进度: {progress_count[0]}/{url_count}", end="")

    for i in range(worker_count):
        t = threading.Thread(target=worker, args=(i + 1, task_queue, results_dict, lock, llm_token, progress_callback, status_dict))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    if progress_bar:
        progress_bar.close()

    results = [results_dict[i] for i in sorted(results_dict.keys())]
    write_excel(results, output_excel)

    end_time = time.time()
    duration = end_time - start_time
    print(f"\n⏱️ 处理完毕，总耗时：{duration:.2f} 秒（约 {duration / 60:.2f} 分钟）")

if __name__ == "__main__":
    main()
