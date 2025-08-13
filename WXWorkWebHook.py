import requests
import os
import logging



def getKey(type):
   
    """
    获取企业微信机器人key
    :param type: 机器人类型
    :return: key
    """
    if type == "test":
        return os.environ.get('WXWORK_ROBOT_KEY_TEST')
    elif type == "prod":
        return  os.environ.get('WXWORK_ROBOT_KEY_PROD')
    else:
        raise ValueError("未知的机器人类型")


key = getKey("test")


def fetch_req(url,data):
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            logging.info(f"{data['msgtype']}类型消息发送成功")
        else:
            logging.error(f"{data['msgtype']}消息发送失败: {response.status_code}, {response.text}")
    except requests.RequestException as e:
        logging.error(f"请求异常: {e}")


def pushMessage(msg,mentioned_mobile_list):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    data = {
        "msgtype": "text",
        "text": {
            "content": "",
            "mentioned_mobile_list": mentioned_mobile_list
        }
    }
    fetch_req(url, data=data)
    data = {
	"msgtype": "markdown_v2",
	"markdown_v2": {
         "content": f"您的扫描任务【{msg['projectName']}】已完成，统计信息如下：\n| 资产状态 | 统计 |\n| :--- | :- |\n| 正常访问 |  {msg['normal_count']}  |\n| 异常资产 |  {msg['abnormal_count']}  |\n| 无法访问 |  {msg['unreachable_count']}  |   \n\n扫描详情请查收附件👇"
	   }
    }
    fetch_req(url, data=data)
    

    


def pushFileMsg(media_id):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    data={
        "msgtype": "file",
        "file": {
            "media_id": media_id
        }
    }
    fetch_req(url, data)


"""
    向企业微信机器人上传媒体文件（文件/语音）
    参数：
        key: webhook 的 key 值
        file_path: 本地文件路径
        file_type: 文件类型，可为 "file" 或 "voice"
    
    返回:
        media_id: 用于后续发送消息
    """
def upload_wechat_webhook_media( file_path: str, type: str = "file"):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type={type}"

    files = {'media': open(file_path, 'rb')}
    response = requests.post(url, files=files)

    if response.status_code == 200:
        data = response.json()
        if data.get("errcode") == 0:
            logging.info(f"上传成功,media_id: {data['media_id']}")
            return data["media_id"]
        else:
            logging.error(f"上传失败: {data}")
    else:
        logging.error(f"请求失败: {response.status_code}, {response.text}")
    return None

def getUserByCreator(creator):
    userDict = {
        "1": ["15588545526"]
    }
    return userDict.get(creator, [])
    

def taskFinishNotify(msg:dict,fileP,creator):
    mentioned_mobile_list = getUserByCreator(creator)
    pushMessage(msg, mentioned_mobile_list)
    if fileP:
        media_id = upload_wechat_webhook_media(fileP, type="file")
        pushFileMsg(media_id)
    else:
        media_id = None


if __name__ == "__main__":
    file_path = "./上海长宁_20250726113024.xlsx" 
    taskFinishNotify({"projectName": "ces","normal_count":1,"abnormal_count":2,"unreachable_count":3}, file_path, "1")
