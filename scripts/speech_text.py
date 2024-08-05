import argparse
import json
import os
import re
import emoji
import pendulum
from retrying import retry
import requests
from notion_helper import NotionHelper
import utils
from dotenv import load_dotenv
import urllib.parse

load_dotenv()


headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://tongyi.aliyun.com",
    "priority": "u=1, i",
    "referer": "https://tongyi.aliyun.com/efficiency/doc/transcripts/g2y8qeaoogbxnbeo?source=2",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "x-b3-sampled": "1",
    "x-b3-spanid": "540e0d18e52cdf0d",
    "x-b3-traceid": "75a25320c048cde87ea3b710a65d196b",
    "x-tw-canary": "",
    "x-tw-from": "tongyi",
}


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_dir():
    """获取文件夹"""
    results = []
    url = (
        "https://qianwen.biz.aliyun.com/assistant/api/record/dir/list/get?c=tongyi-web"
    )
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        r = response.json()
        success = r.get("success")
        errorMsg = r.get("errorMsg")
        if success:
            data = r.get("data")
            for i in data:
                results.extend(dir_list(i.get("dir").get("id")))
        else:
            print(f"请求失败：{errorMsg}")
    else:
        print("请求失败：", response.status_code)
    return results


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def dir_list(dir_id):
    """获取文件夹内所有的item"""
    result = []
    pageNo = 1
    pageSize = 48
    while True:
        payload = {"dirIdStr": dir_id, "pageNo": pageNo, "pageSize": pageSize}
        url = "https://qianwen.biz.aliyun.com/assistant/api/record/list?c=tongyi-web"
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            batchRecord = response.json().get("data").get("batchRecord")
            if len(batchRecord) == 0:
                break
            for i in batchRecord:
                result.extend(i.get("recordList"))
            pageNo += 1
        else:
            print("请求失败：", response.status_code)
            break
    return result


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_note(transId):
    """暂时不支持子list和表格"""
    url = "https://tw-efficiency.biz.aliyun.com/api/doc/getTransDocEdit?c=tongyi-web"
    payload = {"action": "getTransDocEdit", "version": "1.0", "transId": transId}
    response = requests.post(url, headers=headers, json=payload)
    if response.ok:
        note = response.json().get("data").get("content")
        if note:
            data = json.loads(content)
            children = []
            for paragraph in data:
                type = "paragraph"
                skip_outer = False
                is_checked = False
                rich_text = []
                if isinstance(paragraph, list):
                    for span in paragraph:
                        if isinstance(span, dict):
                            if "list" in span:
                                type = "bulleted_list_item"
                                isOrdered = span.get("list").get("isOrdered")
                                isTaskList = span.get("list").get("isTaskList")
                                if isOrdered:
                                    type = "numbered_list_item"
                                if isTaskList:
                                    type = "to_do"
                                    is_checked = span.get("list").get("isChecked")
                        if isinstance(span, list):
                            if span[0] == "span":
                                for i in range(2, len(span)):
                                    bold = False
                                    highlight = False
                                    content = span[i][2]
                                    if "bold" in span[i][1]:
                                        bold = span[i][1].get("bold")
                                    if "highlight" in span[i][1]:
                                        highlight = True
                                    rich_text.append(get_text(content, bold, highlight))
                            if span[0] == "tag":
                                time = utils.format_milliseconds(
                                    span[1].get("metadata").get("time")
                                )
                                rich_text.append(
                                    {
                                        "type": "text",
                                        "text": {"content": time},
                                        "annotations": {
                                            "underline": True,
                                            "color": "blue",
                                        },
                                    }
                                )
                            if span[0] == "img":
                                skip_outer = True
                                url = span[1].get("src")
                                children.append(
                                    {
                                        "type": "image",
                                        "image": {
                                            "type": "external",
                                            "external": {"url": url},
                                        },
                                    }
                                )
                if skip_outer:
                    continue
                child = {
                    "type": type,
                    type: {"rich_text": rich_text, "color": "default"},
                }
                if type == "to_do":
                    child[type]["checked"] = is_checked
                children.append(child)
            return children
    else:
        print("请求失败")


def get_text(content, bold=False, highlight=False):
    text = {"type": "text", "text": {"content": content}, "annotations": {"bold": bold}}
    if highlight:
        text["annotations"]["color"] = "red_background"
    return text


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_all_lab_info(transId):
    url = "https://tw-efficiency.biz.aliyun.com/api/lab/getAllLabInfo?c=tongyi-web"
    payload = {
        "action": "getAllLabInfo",
        "content": ["labInfo", "labSummaryInfo"],
        "transId": transId,
    }
    response = requests.post(url, headers=headers, json=payload)
    mindmap = None
    children = []
    if response.status_code == 200:
        data = response.json().get("data")
        labInfo = data.get("labCardsMap").get("labSummaryInfo")
        labInfo.extend(data.get("labCardsMap").get("labInfo"))
        for i in labInfo:
            name = i.get("basicInfo").get("name")
            if name == "qa问答":
                children.append(utils.get_heading(2, "问题回顾"))
            if name == "议程":
                children.append(utils.get_heading(2, "章节速览"))
            for content in i.get("contents", []):
                for contentValue in content.get("contentValues"):
                    if name == "全文摘要":
                        value = contentValue.get("value")
                        children.append(utils.get_heading(3, "全文摘要"))
                        children.append(utils.get_callout(value, {"emoji": "💡"}))
                    if name == "思维导图":
                        mindmap = contentValue.get("json")
                    if name == "议程":
                        title = f"{utils.format_milliseconds(contentValue.get('time'))} {contentValue.get('value')}"
                        children.append(utils.get_heading(3, title))
                        summary = contentValue.get("summary")
                        if summary:
                            children.append(utils.get_callout(summary, {"emoji": "💡"}))
                    if name == "qa问答":
                        title = contentValue.get("title")
                        value = contentValue.get("value")
                        beginTime = (
                            contentValue.get("extensions")[0]
                            .get("sentenceInfoOfAnswer")[0]
                            .get("beginTime")
                        )
                        beginTime = utils.format_milliseconds(beginTime)
                        title = f"{beginTime} {title}"
                        children.append(utils.get_heading(3, title))
                        children.append(utils.get_callout(value, {"emoji": "💡"}))
        return (children, mindmap)
    else:
        print("请求脑图失败：", response.status_code)


def insert_mindmap(block_id, mindmap):
    """插入思维导图"""
    id = (
        notion_helper.append_blocks(
            block_id=block_id,
            children=[utils.get_bulleted_list_item(mindmap.get("content"))],
        )
        .get("results")[0]
        .get("id")
    )
    if mindmap.get("children"):
        for child in mindmap.get("children"):
            insert_mindmap(id, child)


def check_mindmap(title):
    """检查是否已经插入过"""
    filter = {"property": "标题", "title": {"equals": title}}
    response = notion_helper.query(
        database_id=notion_helper.mindmap_database_id, filter=filter
    )
    if len(response["results"]) > 0:
        return response["results"][0]


def create_mindmap(title, icon):
    result = check_mindmap(title)
    if result:
        status = utils.get_property_value(result.get("properties").get("状态"))
        if status == "Done":
            return result.get("id")
        else:
            notion_helper.delete_block(result.get("id"))
    parent = {
        "database_id": notion_helper.mindmap_database_id,
        "type": "database_id",
    }
    properties = {
        "标题":{"title": [{"type": "text", "text": {"content": title}}]},
        "状态": {"status": {"name": "In progress"}},
    }

    mindmap_page_id = notion_helper.create_page(
        parent=parent,
        properties=properties,
        icon=icon,
    ).get("id")
    return mindmap_page_id

def update_mindmap(page_id):
    properties = {
        "状态": {"status": {"name": "Done"}},
    }

    notion_helper.update_page(
        page_id=page_id,
        properties=properties,
    )


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_trans_result(transId):
    payload = {
        "action": "getTransResult",
        "version": "1.0",
        "transId": transId,
    }
    url = "https://tw-efficiency.biz.aliyun.com/api/trans/getTransResult?c=tongyi-web"
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        response_data = response.json()
        user_dict = {}
        if response_data.get("data").get("tag").get("identify"):
            user_info = json.loads(response_data.get("data").get("tag").get("identify")).get("user_info")
            for key, value in user_info.items():
                user_dict[key] = value.get("name")
        children = []
        for i in json.loads(response_data.get("data").get("result")).get("pg"):
            content = ""
            name = ""
            uid = i.get("ui")
            avatar = None
            if uid in user_dict:
                name = user_dict.get(uid)
                avatar = get_author_avatar(name)
            else:
                name = f"发言人{uid}"
            if avatar is None:
                avatar = "https://www.notion.so/icons/user_gray.svg"
            title = f'{name} {utils.format_milliseconds(i.get("sc")[0].get("bt"))}'
            children.append(utils.get_heading(3, title))
            for j in i.get("sc"):
                content += j.get("tc")
            children.append(utils.get_callout(content, utils.get_icon(avatar)))
        return children
    else:
        print("请求失败：", response.status_code)
        return None


author_cache = {}


def get_author_avatar(author):
    if author in author_cache:
        return author_cache[author]
    filter = {"property": "标题", "title": {"equals": author}}
    r = notion_helper.query(database_id=notion_helper.author_database_id, filter=filter)
    if len(r.get("results")) > 0:
        avatar = r.get("results")[0].get("icon").get("external").get("url")
        author_cache[author] = avatar
        return avatar


if __name__ == "__main__":
    notion_helper = NotionHelper()
    headers["cookie"] = os.getenv("COOKIE").strip()
    filter = {
        "and": [
            {"property": "语音转文字状态", "status": {"does_not_equal": "Done"}},
            {"property": "语音转文字", "checkbox": {"equals": True}},
        ]
    }
    episodes = notion_helper.query_all_by_filter(
        notion_helper.episode_database_id, filter=filter
    )
    results = get_dir()
    results = {
        x.get("recordTitle"):x.get("genRecordId")
        for x in results
    }
    for episode in episodes:
        episode_properties = episode.get("properties")
        title = utils.get_property_value(episode_properties.get("标题"))
        if title not in results:
            title = emoji.replace_emoji(title, replace='')
            title = re.sub(r'\s+', ' ', title).strip()
        children = []
        if title in results:
            episode_page_id = episode.get("id")
            audio_url = utils.get_property_value(episode_properties.get("音频"))
            podcast = utils.get_property_value(episode_properties.get("Podcast"))
            podcast = utils.get_property_value(
                notion_helper.client.pages.retrieve(podcast[0].get("id"))
                .get("properties")
                .get("播客")
            )
            transId = results.get(title)
            cover = episode.get("cover").get("external").get("url")
            children.append(utils.get_heading(2, "音频"))
            player_url = f"https://notion-music.malinkang.com/player?url={urllib.parse.quote(audio_url)}&name={urllib.parse.quote(title)}&cover={urllib.parse.quote(cover)}&artist={urllib.parse.quote(podcast)}"
            children.append({"type": "embed", "embed": {"url": player_url}})
            info, mindmap = get_all_lab_info(transId)
            mindmap_page_id = None
            if mindmap:
                mindmap_page_id = create_mindmap(title, episode.get("icon"))
                insert_mindmap(mindmap_page_id, mindmap)
                update_mindmap(mindmap_page_id)
                mindmap_url = f"https://mindmap.malinkang.com/markmap/{mindmap_page_id.replace('-','')}?token={os.getenv('NOTION_TOKEN')}"
                children.append(utils.get_heading(2, "思维导图"))
                children.append({"type": "embed", "embed": {"url": mindmap_url}})
            if info:
                children.extend(info)
            trans = get_trans_result(transId)
            if trans:
                children.append(utils.get_heading(2, "语音转文字"))
                children.extend(trans)
            note = get_note(transId)
            if note:
                children.append(utils.get_heading(2, "笔记"))
                children.extend(note)
            for i in range(0, len(children) // 100 + 1):
                notion_helper.append_blocks(
                    block_id=episode_page_id, children=children[i * 100 : (i + 1) * 100]
                )
            properties = {"语音转文字状态": {"status": {"name": "Done"}}}
            if mindmap_page_id:
                properties["思维导图"] = {"relation": [{"id": mindmap_page_id}]}
            notion_helper.update_page(
                page_id=episode_page_id,
                properties=properties,
            )
        else:
            print(f"未搜索到《{title}》，请检查你是否已经转写成功")
