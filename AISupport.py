import os
import dashscope
import math
from PIL import Image
from constants import *

MODEL = 'qwen-vl-max-latest'
#MODEL = 'qvq-max' # 准确 更贵 速度慢
PROMPT_PAGE_JUDGE = f"""
图片为浏览器访问站点的页面结果,通过页面特征判断类型; 
{' '.join(str(v) for v in TYPE_DEFINE.values())}
仅回复类型序号
"""


"""
@param text 
@param imgPath
""" 
def agent_call(token,**msg):
    msg_keys = msg.keys()
    if 'imgPath'  not in msg_keys or 'text' not in msg_keys:
        return 
    if  not os.path.exists(msg['imgPath']):
        return
        
    messages = [
        {
            "role": "user",
            "content": [
                {'image':f"file://{ msg['imgPath']}"},
                {"text": msg['text']}
            ]
        }
    ]
    return  dashscope.MultiModalConversation.call(
        api_key=token,
        model=MODEL, # 此处以qwen-vl-max为例,可按需更换模型名称。模型列表:https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=messages
        )

    # return dashscope.MultiModalConversation.call(
    #         api_key=token,
    #         model=MODEL, # 此处以qwen-vl-max为例,可按需更换模型名称。模型列表:https://help.aliyun.com/zh/model-studio/getting-started/models
    #         messages=messages,
    #         stream=True
    #         )


def agent_call_stream(response):
    # 定义完整思考过程
    reasoning_content = ""
    # 定义完整回复
    answer_content = ""
    # 判断是否结束思考过程并开始回复
    is_answering = False

    #print("=" * 20 + "思考过程" + "=" * 20)

    for chunk in response:
        # 如果思考过程与回复皆为空，则忽略
        message = chunk.output.choices[0].message
        reasoning_content_chunk = message.get("reasoning_content", None)
        if (chunk.output.choices[0].message.content == [] and
            reasoning_content_chunk == ""):
            pass
        else:
            # 如果当前为思考过程
            if reasoning_content_chunk != None and chunk.output.choices[0].message.content == []:
                #print(chunk.output.choices[0].message.reasoning_content, end="")
                reasoning_content += chunk.output.choices[0].message.reasoning_content
            # 如果当前为回复
            elif chunk.output.choices[0].message.content != []:
                if not is_answering:
                    #print("\n" + "=" * 20 + "完整回复" + "=" * 20)
                    is_answering = True
                #print(chunk.output.choices[0].message.content[0]["text"], end="")
                answer_content += chunk.output.choices[0].message.content[0]["text"]
    return answer_content

output_tokens = 0
input_tokens = 0

def getAIResponse(response:dict) -> str:
    try:
        output_tokens +=  response["usage"]["output_tokens"] 
        input_tokens += response["usage"]["input_tokens"]
        return response["output"]["choices"][0]["message"].content[0]["text"]
    except (KeyError, IndexError, AttributeError, TypeError):
        return response
    

def getTokenDeal():
    print(f"💰  本次消费Token:{output_tokens + input_tokens},非准确计费:{output_tokens * 0.009 + input_tokens * 0.003}")


def is_token_valid(token: str) -> bool:
    messages = [
        {
            "role": "user",
            "content": [
                {"text": "只回复1"}
            ]
        }
    ]
    response = dashscope.MultiModalConversation.call(
        api_key=token,
        model=MODEL, 
        messages=messages
        )
    if response["code"] == "InvalidApiKey":
        return False
    if getAIResponse(response) == "1":
        return True
    return False


def imgTokenSimplizer(imgPath,compression_ratio = 0):
    """
    压缩图像以减少 token 数，保留宽高比例，压缩强度可控
    :param image_path: 原始图片路径
    :param compression_ratio: 压缩强度,1.0=最小 token,0.5=更清晰,0=不压缩
    :return: 新文件的绝对路径
    """
    image = Image.open(imgPath)
    width, height = image.size
    aspect_ratio = width / height

    if compression_ratio <= 0:
        # 不压缩，直接保存副本
        new_width = int(math.ceil(width / 28) * 28)
        new_height = int(math.ceil(height / 28) * 28)
    else:
        # 最小token像素数为 112 x 112
        min_pixels = 28 * 28 * 4
        scale = math.sqrt(min_pixels / (width * height))

        # 使用 compression_ratio 调整缩放强度
        scale = scale * compression_ratio

        new_width = max(112, int(math.floor(width * scale / 28) * 28))
        new_height = max(112, int(math.floor(height * scale / 28) * 28))

        # 修正宽高比
        if new_width / new_height > aspect_ratio:
            new_width = int(new_height * aspect_ratio // 28 * 28)
        else:
            new_height = int(new_width / aspect_ratio // 28 * 28)

    # 调整到目标大小（如果原图已小于目标则不放大）
    new_width = min(new_width, width)
    new_height = min(new_height, height)

    resized_image = image.resize((new_width, new_height), Image.LANCZOS)

    # 保存处理后的图片
    dir_name, file_name = os.path.split(imgPath)
    name, ext = os.path.splitext(file_name)
    new_file_name = f"{name}_retoken{ext}"
    new_file_path = os.path.abspath(os.path.join(dir_name, new_file_name))

    resized_image.save(new_file_path)
    return new_file_path


def token_calculate(imgPath):
    image = Image.open(imgPath)
    height, width = image.height, image.width
    h_bar = round(height / 28) * 28
    w_bar = round(width / 28) * 28
    min_pixels = 28 * 28 * 4  # 最小像素数
    max_pixels = 1280 * 28 * 28  # 最大像素数
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = math.floor(height / beta / 28) * 28
        w_bar = math.floor(width / beta / 28) * 28
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / 28) * 28
        w_bar = math.ceil(width * beta / 28) * 28
    token = int((h_bar * w_bar) / (28 * 28))
    total_token = token + 2 
    return total_token


def getToken():
    return os.environ.get('DASHSCOPE_API_KEY')


if __name__ == "__main__":
  
    pass