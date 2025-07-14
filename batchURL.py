import os
import io
import time
import base64
import argparse
from bs4 import BeautifulSoup
import threading
import logging
from queue import Queue
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage, ImageOps
#===日志配置===
LOG_FILENAME = "./log/batchURL.log"
with open(LOG_FILENAME, "w", encoding="utf-8") as f:
    f.write('')

logging.basicConfig(
    filename=LOG_FILENAME,
    filemode="a",
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    encoding="utf-8"
)

class FirefoxRequestFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        FILTER_WORD = [".firefox.", ".mozilla.", ".google.",".ico"]
        if any(domain in msg.lower() for domain in FILTER_WORD):
            return False
        return True

# seleniumwire logger
logger = logging.getLogger("seleniumwire")
logger.setLevel(logging.INFO)
logger.addFilter(FirefoxRequestFilter())

# 给根logger的handler也添加过滤器，确保写文件的handler经过过滤
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.addFilter(FirefoxRequestFilter())
#========
from AISupport import *
from selenium.webdriver.firefox.service import Service
from seleniumwire import webdriver  
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.common.exceptions import WebDriverException, TimeoutException
# === 配置 ===
TARGET_IMG_HIGHT = 200
ROW_HEIGHT = 150
PROJ_INDEX = datetime.now().strftime("%Y%m%d%H%M%S")

def print_banner():
    banner = "Cl9fX19fXyAgICAgICBfICAgICAgIF8gICAgIF8gICBfX19fX19fIF8gICAgIAp8IF9fXyBcICAgICB8IHwgICAgIHwgfCAgIHwgfCB8IHwgX19fIHwgfCAgICAKfCB8Xy8gLyBfXyBffCB8XyBfX198IHxfXyB8IHwgfCB8IHxfLyB8IHwgICAgCnwgX19fIFwvIF9gIHwgX18vIF9ffCAnXyBcfCB8IHwgfCAgICAvfCB8ICAgIAp8IHxfLyB8IChffCB8IHx8IChfX3wgfCB8IHwgfF98IHwgfFwgXHwgfF9fX18KXF9fX18vIFxfXyxffFxfX1xfX198X3wgfF98XF9fXy9cX3wgXF9cX19fX18vCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgLS1ieSB2MW53MW4gICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAo="
    print(base64.b64decode(banner.encode('utf-8')).decode('utf-8'))


# class ArgumentParserBanner(argparse.ArgumentParser):
#     def print_help(self, *args, **kwargs):
#         print_banner()
#         super().print_help(*args, **kwargs)



def page_judge(url: str, html: str,title: str ,http_status: int, imgPath: str, token: str = None) -> str:
    res = None
    if token :
        res =  page_judge_ai(imgPath,token)
    if res is None:
        return page_judge_local(url=url,html=html,title=title,http_status=http_status)
    else:
        return res


def page_judge_ai(imgPath,token):
    imgPath = imgTokenSimplizer(imgPath)
    res = agent_call(token=token,imgPath = imgPath,text= PROMPT_PAGE_JUDGE)
    logging.info(f"AI call->{res}:{imgPath}:prompt->PROMPT_PAGE_JUDGE")
    res = getAIResponse(res)
    if res in TYPE_DEFINE.keys() :
        return TYPE_DEFINE[res]["type"]
    else:
        logging.error(f"AI 响应异常:{res}")
        print(f"AI 异常,转本地判断,详情查看日志")
    return None


def page_judge_local(url: str, html: str,title: str ,http_status: int) -> str:
    #错误页 http状态码 ；title包含关键字或者html包含关键字且简单结构
    #登录页 html包含login关键字，非简单结构
    #欢迎页 html包含关键字
    #正常系统
    
    html_lower = html.lower()
    soup = BeautifulSoup(html, 'html.parser')
    body_tags = soup.find_all(True)
    tag_count = len(body_tags)
    TAG_THRESHOLD = 30

    KEYWORDS = {
        "welcome": ["tomcat", "nginx", "openresty"],
        "error": [
            "400", "bad request",
            "401", "unauthorized", 
            "403", "forbidden",
            "404", "not found", 
            "405", "method not allowed",
            "500", "internal server error",
            "502", "bad gateway",
            "503", "service unavailable",
            
        ],
        "login": ["login"],
        "ui_error": ["error"]
    }

    if http_status is None:
        http_status = 0

    #错误页判断
    if http_status is not None and http_status >= 400:
        logging.info(f"http status code -> {http_status} : {url}")
        return TYPE_DEFINE["3"]["type"]
    if tag_count < TAG_THRESHOLD:
        for keyword in KEYWORDS["error"]:
            if keyword in html_lower:
                logging.info(f"命中关键词 -> {keyword} : 标签数 -> {tag_count} : {url} ")
                return TYPE_DEFINE["3"]["type"]
    #登录页判断
    if tag_count >= TAG_THRESHOLD:
        for keyword in KEYWORDS["login"]:
            if keyword in html_lower:
                logging.info(f"命中关键词 -> {keyword} : 标签数 -> {tag_count} : {url} ")
                return TYPE_DEFINE["2"]["type"]

    #欢迎页判断
    for keyword in KEYWORDS["welcome"]:
        if keyword in html_lower and "welcom" in title.lower():
            logging.info(f"命中关键词 -> {keyword} : title -> {title} : 标签数 -> {tag_count} : {url} ")
            return TYPE_DEFINE["4"]["type"]
    #异常系统判断
    if tag_count > TAG_THRESHOLD:
        for keyword in KEYWORDS["ui_error"]:
            if keyword in html_lower:
                logging.info(f"命中关键词 -> {keyword} : 标签数 -> {tag_count} : {url} ")
                return TYPE_DEFINE["6"]["type"]
    #默认正常系统
    return TYPE_DEFINE["1"]["type"]


SCREENSHOTS_DIR = ".\\screeshots\\"

def resize_image(image_bytes, target_height=TARGET_IMG_HIGHT,idx = None):
    img = PILImage.open(io.BytesIO(image_bytes))

    if idx is not None and isinstance(idx,int):
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        img.save(os.path.join(SCREENSHOTS_DIR, f"{PROJ_INDEX}_{idx}.png"), format="PNG", optimize=True)
    h_percent = target_height / float(img.size[1])
    w_size = int(img.size[0] * h_percent)
    img = img.resize((w_size, target_height), PILImage.LANCZOS)
    img = ImageOps.expand(img, border=2, fill='black')
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer

# === 创建浏览器实例 ===
def create_browser():
    options = FirefoxOptions()
    options.add_argument("--headless")
    options.accept_insecure_certs = True
    options.binary_location = "C:\\Program Files\\Mozilla Firefox\\firefox.exe"
    service = Service(os.environ.get('geckodriver_exe'))
    driver = webdriver.Firefox( seleniumwire_options={'disable_capture': False}, options=options,service=service )
    driver.set_page_load_timeout(15)
    return driver

# === 获取状态码 ===
def normalize_url(url: str):
    parts = urlsplit(url)
    # 丢弃 fragment
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))


def get_status_code(driver):
    STATIC_SUFFIXES = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf")
    try:
        norm_current = normalize_url(driver.current_url)
        for request in reversed(driver.requests):
            if request.response :
                norm_request = normalize_url(request.url)
                if  norm_request  == norm_current:
                    if not request.url.lower().split("?")[0].endswith(STATIC_SUFFIXES) :
                        logging.info(f"获取 HTTP 响应码: {request.response.status_code}:{ request.url}")
                    return request.response.status_code
    except Exception as e:
        logging.exception(f"获取 HTTP 响应码失败: {str(e)}:{ request.url}")
        pass
    return -1

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
            title = ""
            soup = BeautifulSoup(html, 'html.parser')
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            http_status = get_status_code(driver)
            screenshot = driver.get_screenshot_as_png()
            image = resize_image(image_bytes = screenshot,idx = idx)
            imgPath = os.path.join( os.path.abspath(SCREENSHOTS_DIR), f"{PROJ_INDEX}_{idx}.png")
            logging.info(f"imgPath->{imgPath}:{url}")
            status = page_judge(url=url, html = html,title = title, http_status = http_status, imgPath = imgPath, token = llm_token)
        except TimeoutException:
            status = "无法访问(访问超时)"
            image = None
        except WebDriverException:
            status = "无法访问(Web异常)"
            image = None
        except Exception as e:
            status = "无法访问(其他异常)"
            image = None
            logging.exception(f"处理 {url} 异常:{e} ")

        with lock:
            result_dict[idx] = {
                "id": idx,
                "url": url,
                "status": status,
                "page_title": title,
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
    ws.append(["ID", "URL", "访问状态", "标题", "截图"])
    for row_num, res in enumerate(results, start=2):
        ws.cell(row=row_num, column=1, value=res["id"])
        ws.cell(row=row_num, column=2, value=res["url"])
        ws.cell(row=row_num, column=3, value=res["status"])
        ws.cell(row=row_num, column=4, value=res.get("page_title", ""))
        if res["image"]:
            img = XLImage(res["image"])
            ws.add_image(img, f"E{row_num}") #E 插入图片的列
            ws.row_dimensions[row_num].height = ROW_HEIGHT
        else:
            ws.cell(row=row_num, column=5, value="（无截图）")
            ws.row_dimensions[row_num].height = 20

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 30
    ws.column_dimensions["E"].width = 45
    wb.save(output_path)
    print(f"\n✅ Excel 文件已保存: {output_path}")

# === 自动计算线程数 ===
def calculate_worker_count(url_count, max_limit=10):
    if url_count <= 10:
        return min(2, url_count)
    elif url_count <= 100:
        return min(4, url_count)
    elif url_count <= 300:
        return min(6, url_count)
    else:
        return min(max_limit, url_count // 20 + 2)


def main():
    print_banner()
    parser = argparse.ArgumentParser(description="批量获取目标URL访问状态")
    parser.add_argument('-i', '--input', default='urls', help='定义目标,一行一个目标(txt)')
    parser.add_argument('-o', '--output', default='url_results', help='定义输出文件名，不加后缀')
    parser.add_argument('--llm-token', help='开启AI支持,配置token')
    parser.add_argument('--friend-ui', action='store_true', help='是否启用进度条展示(默认关闭)')
    args = parser.parse_args()

    input_file = args.input
    output_excel = f"{args.output}_{PROJ_INDEX}.xlsx"
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
    llm_token_check = False
    if llm_token is not None:
        if is_token_valid(llm_token):
            output_excel = f"{args.output}_{PROJ_INDEX}_AI.xlsx"
            llm_token_check = True
            print("✅LLM TOKEN已配置")
        else :
            llm_token = None
            print("❌LLM TOKEN不可用")
        

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
            print("⚠️ 未安装 tqdm,进度条自动切换为轻量模式")
            use_progress_bar = False

    def progress_callback():
        progress_count[0] += 1
        if use_progress_bar and progress_bar:
            progress_bar.update(1)
        else:
            print(f"\r⏸️  进度: {progress_count[0]}/{url_count}", end="")

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
    if llm_token_check:
        getTokenDeal()

if __name__ == "__main__":
    main()
